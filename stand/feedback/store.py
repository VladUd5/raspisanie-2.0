"""Постоянная база data/feedback.db: сообщения пользователей об ошибках, графики учебного процесса и сессии.

В отличие от schedule.db эта база не пересобирается: схема меняется только пошаговыми
миграциями (PRAGMA user_version), данные не удаляются. Контакт не собираем — версия для
руководства открыта, персональные данные хранить нельзя. Адрес отправителя хранится только
солёным хэшем и только сутки — для ограничения частоты.
"""
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

KINDS = {"room": "не та аудитория", "time": "не то время или день", "teacher": "не тот преподаватель",
         "missing": "занятия нет / отменено", "other": "другое"}
STATUSES = {"new": "новое", "in_progress": "в работе", "fixed": "исправлено", "rejected": "отклонено"}
MAX_TEXT = 1000

MIGRATIONS = [
    """CREATE TABLE reports (
        id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
        page TEXT, group_name TEXT, teacher TEXT, room TEXT, lesson TEXT, lesson_date TEXT,
        snapshot_id INTEGER, status TEXT NOT NULL DEFAULT 'new', staff_note TEXT DEFAULT '',
        updated_at TEXT);
    CREATE TABLE report_log (report_id INTEGER REFERENCES reports(id), at TEXT, action TEXT, value TEXT);
    CREATE TABLE rate (ip_hash TEXT, at TEXT);
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE INDEX ix_reports_status ON reports(status);
    CREATE INDEX ix_rate_ip ON rate(ip_hash, at);""",
    # 2: графики учебного процесса (kug.py) и даты сессий — черновики распознавания и подтверждённые
    """CREATE TABLE kug_files (
        url TEXT PRIMARY KEY, title TEXT, program TEXT, form TEXT, code TEXT, code_manual INTEGER DEFAULT 0,
        courses TEXT, status TEXT, message TEXT, checked_at TEXT);
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY, file_url TEXT NOT NULL, course INTEGER NOT NULL, start_date TEXT NOT NULL,
        end_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', source TEXT NOT NULL DEFAULT 'auto',
        note TEXT DEFAULT '', updated_at TEXT);
    CREATE INDEX ix_sessions_file ON sessions(file_url, course);
    CREATE INDEX ix_kug_code ON kug_files(code, form);""",
    # 3: все периоды графика (теория, сессия, каникулы, практика) и версия файла на сайте (ETag/Last-Modified)
    """ALTER TABLE sessions ADD COLUMN kind TEXT NOT NULL DEFAULT 'session';
    ALTER TABLE kug_files ADD COLUMN version TEXT NOT NULL DEFAULT '';
    CREATE TABLE kug_holidays (file_url TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY (file_url, day));""",
]

FIELDS = ["kind", "text", "page", "group_name", "teacher", "room", "lesson", "lesson_date", "snapshot_id"]


def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {i}")
    return conn


def _local_now() -> datetime:
    """Время по часовому поясу сайта (в контейнере системное время — UTC)."""
    from semester import now
    return now()


def _now(at: datetime | None) -> str:
    return (at or _local_now()).isoformat(timespec="seconds")


def _salt(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'salt'").fetchone()
    if row:
        return row[0]
    salt = secrets.token_hex(16)
    with conn:
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('salt', ?)", (salt,))
    return conn.execute("SELECT value FROM meta WHERE key = 'salt'").fetchone()[0]


def add_report(conn: sqlite3.Connection, fields: dict, ip: str, per_hour: int = 5,
               at: datetime | None = None) -> int | None:
    """→ id сообщения или None, если с этого адреса за час уже было per_hour сообщений."""
    at = at or _local_now()
    ip_hash = hashlib.sha256((_salt(conn) + (ip or "")).encode()).hexdigest()
    hour_ago = (at - timedelta(hours=1)).isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM rate WHERE at < ?", ((at - timedelta(days=1)).isoformat(timespec="seconds"),))
        recent = conn.execute("SELECT COUNT(*) FROM rate WHERE ip_hash = ? AND at >= ?", (ip_hash, hour_ago)).fetchone()[0]
        if recent >= per_hour:
            return None
        conn.execute("INSERT INTO rate (ip_hash, at) VALUES (?, ?)", (ip_hash, _now(at)))
        row = {k: fields.get(k) for k in FIELDS}
        row["kind"] = row["kind"] if row["kind"] in KINDS else "other"
        row["text"] = (row["text"] or "").strip()[:MAX_TEXT]
        rid = conn.execute(
            f"INSERT INTO reports (created_at, {', '.join(FIELDS)}) VALUES (?{', ?' * len(FIELDS)})",
            (_now(at), *row.values())).lastrowid
        conn.execute("INSERT INTO report_log (report_id, at, action, value) VALUES (?, ?, 'created', '')",
                     (rid, _now(at)))
    return rid


def list_reports(conn: sqlite3.Connection, statuses: tuple[str, ...] = ()) -> list[dict]:
    sql = "SELECT * FROM reports"
    if statuses:
        sql += f" WHERE status IN ({', '.join('?' * len(statuses))})"
    return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC", statuses)]


def set_status(conn: sqlite3.Connection, report_id: int, status: str, note: str | None = None) -> None:
    if status not in STATUSES:
        raise ValueError(f"неизвестный статус {status}")
    at = _now(None)
    with conn:
        old = conn.execute("SELECT status, staff_note FROM reports WHERE id = ?", (report_id,)).fetchone()
        if old is None:
            return
        if old["status"] != status:
            conn.execute("UPDATE reports SET status = ?, updated_at = ? WHERE id = ?", (status, at, report_id))
            conn.execute("INSERT INTO report_log VALUES (?, ?, 'status', ?)", (report_id, at, status))
        if note is not None and note != old["staff_note"]:
            conn.execute("UPDATE reports SET staff_note = ?, updated_at = ? WHERE id = ?", (note, at, report_id))
            conn.execute("INSERT INTO report_log VALUES (?, ?, 'note', ?)", (report_id, at, note))


def log(conn: sqlite3.Connection, report_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT at, action, value FROM report_log WHERE report_id = ? ORDER BY at",
                                          (report_id,))]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {s: 0 for s in STATUSES}
    out.update({r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM reports GROUP BY status")})
    return out
