"""ETL снапшота: flatten → clean → normalize → SQLite. Повторная загрузка того же
файла заменяет его данные."""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from etl.clean import UNKNOWN, clean
from etl.flatten import flatten
from etl.canon import UNVERIFIED, Canonizer, Resolved
from etl.dictionary import Dictionary, load_dictionary
from etl.normalize import is_surname_only
from etl.variants import NOT_DISCIPLINE, classify

# Меняется при несовместимой правке схемы: стенд пересоздаёт БД, а снапшоты
# из data/snapshots перечитывает ensure_loaded на следующем запуске.
SCHEMA_VERSION = 2

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY, collected_at TEXT, source_url TEXT, file_name TEXT UNIQUE,
    groups_cnt INTEGER, cells_cnt INTEGER, lessons_cnt INTEGER, service_cnt INTEGER);
CREATE TABLE IF NOT EXISTS cells (
    id INTEGER PRIMARY KEY, snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    building TEXT, institute TEXT, study_form TEXT, group_name TEXT,
    day TEXT, day_idx INTEGER, time_from TEXT, time_to TEXT, duration_h REAL,
    week_type TEXT, subject_raw TEXT, is_service INTEGER, truncated INTEGER, lessons_in_cell INTEGER);
CREATE TABLE IF NOT EXISTS disciplines (
    id INTEGER PRIMARY KEY, snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    name TEXT, UNIQUE (snapshot_id, name));
CREATE TABLE IF NOT EXISTS discipline_aliases (
    snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    alias TEXT, discipline_id INTEGER REFERENCES disciplines(id) ON DELETE CASCADE,
    PRIMARY KEY (snapshot_id, alias));
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY, snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    full_name TEXT, surname TEXT, UNIQUE (snapshot_id, full_name));
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY, snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    building TEXT, name TEXT, UNIQUE (snapshot_id, building, name));
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY, cell_id INTEGER REFERENCES cells(id) ON DELETE CASCADE,
    snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    part_idx INTEGER, lesson_type TEXT, discipline_id INTEGER REFERENCES disciplines(id),
    subgroup INTEGER, building TEXT, week_factor REAL);
CREATE TABLE IF NOT EXISTS lesson_teachers (
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS lesson_rooms (
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS quality (
    lesson_id INTEGER PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
    has_type INTEGER, has_discipline INTEGER, has_teacher INTEGER, has_room INTEGER,
    discipline_fuzzy INTEGER, teacher_surname_only INTEGER, split_cell INTEGER,
    suspicious_group INTEGER, truncated INTEGER, needs_review INTEGER, unverified_name INTEGER);
CREATE TABLE IF NOT EXISTS spellings (
    snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    kind TEXT, spelling TEXT, canonical TEXT, source TEXT, confidence TEXT,
    error_kinds TEXT, note TEXT, lessons INTEGER, score REAL);
CREATE TABLE IF NOT EXISTS rule_audit (
    snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    kind TEXT, tp INTEGER, fp INTEGER, fn INTEGER);
CREATE INDEX IF NOT EXISTS ix_spellings_snapshot ON spellings(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_lessons_snapshot ON lessons(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_cells_snapshot ON cells(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_lesson_teachers_lesson ON lesson_teachers(lesson_id);
CREATE INDEX IF NOT EXISTS ix_lesson_rooms_lesson ON lesson_rooms(lesson_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        conn.execute("PRAGMA foreign_keys = OFF")
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def suspicious_group(name: str) -> bool:
    """Обрывки имён групп: апстрим режет заголовок по пробелу («1 бэ» → «1», «бэ»;
    «Б-ЛА -101» → «-101»; двойной пробел → «»)."""
    name = (name or "").strip()
    return not re.search(r"\d", name) or len(name) < 3 or name.startswith("-")


def read_snapshot(path: Path) -> dict:
    """Снапшот — обёртка {collected_at, source_url, buildings}; голый список
    корпусов (прямой ответ парсера) тоже принимается."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list) or data is None:
        stamp = datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds")
        return {"collected_at": stamp, "source_url": "", "buildings": data or []}
    return {"collected_at": data.get("collected_at", ""), "source_url": data.get("source_url", ""),
            "buildings": data.get("buildings") or []}


def load_snapshot(conn: sqlite3.Connection, path: Path, dictionary: Dictionary | None = None) -> int:
    path = Path(path)
    dictionary = load_dictionary() if dictionary is None else dictionary
    snap = read_snapshot(path)
    cells = flatten(snap["buildings"])
    parsed = [clean(c.subject_raw) for c in cells]
    canon = Canonizer(dictionary, [l for p in parsed for l in p.lessons])
    fuzzy_aliases = {m.alias for m in canon.disc_merges}    # склеено правилом с score < 100, не словарём
    tally: dict[tuple[str, str, str], list] = {}           # (вид, написание, канон) → [Resolved, занятий]

    def note(kind: str, spelling: str, r: Resolved, canonical: str) -> None:
        key = (kind, spelling, canonical)
        if key in tally:
            tally[key][1] += 1
        else:
            tally[key] = [r, 1]

    with conn:
        conn.execute("DELETE FROM snapshots WHERE file_name = ?", (path.name,))
        snap_id = conn.execute(
            "INSERT INTO snapshots (collected_at, source_url, file_name, groups_cnt, cells_cnt,"
            " lessons_cnt, service_cnt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (snap["collected_at"], snap["source_url"], path.name,
             len({(c.building, c.institute, c.study_form, canon.group(c.group_name).canonical) for c in cells}),
             len(cells), sum(len(p.lessons) for p in parsed), sum(p.is_service for p in parsed)),
        ).lastrowid

        ids: dict[tuple, int] = {}

        def get_id(table: str, key: tuple, insert_sql: str, values: tuple) -> int:
            if (table, key) not in ids:
                ids[(table, key)] = conn.execute(insert_sql, values).lastrowid
            return ids[(table, key)]

        def discipline_id(alias: str, canonical: str) -> int:
            did = get_id("d", (canonical,), "INSERT INTO disciplines (snapshot_id, name) VALUES (?, ?)",
                         (snap_id, canonical))
            if ("a", (alias,)) not in ids:
                conn.execute("INSERT INTO discipline_aliases (snapshot_id, alias, discipline_id) VALUES (?, ?, ?)",
                             (snap_id, alias, did))
                ids[("a", (alias,))] = did
            return did

        for cell, p in zip(cells, parsed):
            group = canon.group(cell.group_name)
            cell_id = conn.execute(
                "INSERT INTO cells (snapshot_id, building, institute, study_form, group_name, day, day_idx,"
                " time_from, time_to, duration_h, week_type, subject_raw, is_service, truncated, lessons_in_cell)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snap_id, cell.building, cell.institute, cell.study_form, group.canonical, cell.day,
                 cell.day_idx, cell.time_from, cell.time_to, cell.duration_h, cell.week_type,
                 cell.subject_raw, int(p.is_service), int(p.truncated), len(p.lessons)),
            ).lastrowid
            n = len(p.lessons)
            base = 1.0 if cell.week_type == "both" else 0.5
            for part_idx, lesson in enumerate(p.lessons):
                note("group", cell.group_name, group, group.canonical)
                lt = canon.lesson_type(lesson.type_raw, lesson.lesson_type)
                if lesson.type_raw:
                    note("lesson_type", lesson.type_raw, lt, lt.canonical)
                d = canon.discipline(lesson.discipline) if lesson.discipline else None
                if d:
                    note("discipline", lesson.discipline, d, d.canonical or NOT_DISCIPLINE)
                disc = d.canonical if d else None
                building = lesson.building or cell.building
                lesson_id = conn.execute(
                    "INSERT INTO lessons (cell_id, snapshot_id, part_idx, lesson_type, discipline_id, subgroup,"
                    " building, week_factor) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (cell_id, snap_id, part_idx, lt.canonical,
                     discipline_id(lesson.discipline, disc) if disc else None,
                     lesson.subgroup, building, base / n),
                ).lastrowid
                resolved = [(t, canon.teacher(t, disc)) for t in lesson.teachers]
                for t, r in resolved:
                    note("teacher", t, r, r.canonical)
                canon_teachers = list(dict.fromkeys(r.canonical for _, r in resolved))
                for t in canon_teachers:
                    tid = get_id("t", (t,), "INSERT INTO teachers (snapshot_id, full_name, surname) VALUES (?, ?, ?)",
                                 (snap_id, t, t.split()[0]))
                    conn.execute("INSERT INTO lesson_teachers (lesson_id, teacher_id) VALUES (?, ?)", (lesson_id, tid))
                rooms = []
                for room, raw in zip(lesson.rooms, lesson.rooms_raw):
                    b, r_name, res = canon.room(building, room, raw)
                    note("room", f"{building}|{raw}", res, f"{b}|{r_name}")
                    rooms.append((b, r_name))
                for b, r_name in dict.fromkeys(rooms):
                    rid = get_id("r", (b, r_name), "INSERT INTO rooms (snapshot_id, building, name) VALUES (?, ?, ?)",
                                 (snap_id, b, r_name))
                    conn.execute("INSERT INTO lesson_rooms (lesson_id, room_id) VALUES (?, ?)", (lesson_id, rid))
                flags = {
                    "has_type": lt.canonical != UNKNOWN,
                    "has_discipline": bool(disc),
                    "has_teacher": bool(lesson.teachers),
                    "has_room": bool(lesson.rooms),
                    "discipline_fuzzy": lesson.discipline in fuzzy_aliases,
                    "teacher_surname_only": any(is_surname_only(t) for t in canon_teachers),
                    "split_cell": n > 1,
                    "suspicious_group": suspicious_group(group.canonical),
                    "truncated": p.truncated,
                }
                flags["needs_review"] = (not (flags["has_discipline"] and flags["has_teacher"] and flags["has_room"])
                                         or flags["suspicious_group"] or flags["truncated"])
                flags["unverified_name"] = ((bool(d) and d.source in UNVERIFIED)
                                            or any(r.source in UNVERIFIED for _, r in resolved))
                conn.execute(
                    f"INSERT INTO quality (lesson_id, {', '.join(flags)}) VALUES (?{', ?' * len(flags)})",
                    (lesson_id, *map(int, flags.values())),
                )
        scores = {(m.kind, m.alias): m.score for m in [*canon.disc_merges, *canon.teacher_merges]}
        rows = []
        for (kind, spelling, canonical), (r, uses) in tally.items():
            shown = spelling.split("|", 1)[1] if kind == "room" else spelling
            target = canonical.split("|", 1)[1] if kind == "room" else canonical
            kinds = [r.kind] if r.kind else classify(kind, shown, target)
            rows.append((snap_id, kind, spelling, canonical, r.source, r.confidence, ", ".join(kinds),
                         r.note, uses, scores.get((kind, spelling))))
        conn.executemany("INSERT INTO spellings (snapshot_id, kind, spelling, canonical, source, confidence,"
                         " error_kinds, note, lessons, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany("INSERT INTO rule_audit (snapshot_id, kind, tp, fp, fn) VALUES (?, ?, ?, ?, ?)",
                         [(snap_id, kind, a.tp, a.fp, a.fn) for kind, a in canon.audit().items()])
    return snap_id


def ensure_loaded(conn: sqlite3.Connection, snapshots_dir: Path) -> tuple[list[int], list[tuple[str, str]]]:
    """Загружает снапшоты из папки, которых ещё нет в БД.

    Возвращает id загруженных и список (файл, ошибка) для файлов, которые
    прочитать не удалось: битый снапшот не должен ронять стенд.
    """
    known = {row[0] for row in conn.execute("SELECT file_name FROM snapshots")}
    loaded, errors = [], []
    for p in sorted(Path(snapshots_dir).glob("*.json")):
        if p.name in known:
            continue
        try:
            loaded.append(load_snapshot(conn, p))
        except (ValueError, OSError, AttributeError, TypeError) as e:
            errors.append((p.name, str(e)))
    return loaded, errors
