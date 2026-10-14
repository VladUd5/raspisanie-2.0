"""Учебный календарь из графиков учебного процесса (kug.py) и производственного календаря.

- Праздники: нерабочие праздничные дни РФ (ст. 112 ТК) и перенос выходного, совпавшего с праздником,
  на следующий понедельник (кроме январских); плюс дни, отмеченные «=» в графиках вуза хотя бы в
  MIN_VOTES файлах (так попадают переносы январских праздников по постановлению правительства);
  HOLIDAYS_EXTRA / WORKDAYS_EXTRA в .env — ручная правка («2027-01-02,2027-05-10»).
- Периоды курса (теория, сессия, каникулы, практика) — только подтверждённые учебным отделом.
- Семестры по графикам очной и очно-заочной форм (у заочников «пусто» в графике — самостоятельная
  работа, а не пары): от самого раннего начала теории до самого позднего окончания, которые
  встретились хотя бы у MIN_VOTES курсов (черновики тоже голосуют — ошибка одного скана тонет в
  большинстве). Границы нарочно с запасом: точные даты группы дают её подтверждённые периоды, а
  общие не должны прятать настоящие пары. semester.py берёт их, когда даты не заданы в .env.

Данные читаются из feedback.db и держатся в памяти, пока файл базы не изменится.
"""
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from config import env_date, feedback_db_path

MIN_VOTES = 5
FIXED = [(1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8), (2, 23), (3, 8), (5, 1), (5, 9),
         (6, 12), (11, 4)]
HOLIDAY_NAMES = {(1, 7): "Рождество Христово", (2, 23): "День защитника Отечества",
                 (3, 8): "Международный женский день", (5, 1): "Праздник Весны и Труда", (5, 9): "День Победы",
                 (6, 12): "День России", (11, 4): "День народного единства"}


@dataclass
class Calendar:
    votes: set = field(default_factory=set)                      # дни «=» с MIN_VOTES голосами
    periods: dict = field(default_factory=dict)                  # (код, форма, курс) → [(вид, начало, конец)]
    semesters: list = field(default_factory=list)                # [(начало, конец)] по графикам
    _by_group: dict = field(default_factory=dict)

    def holiday(self, d: date) -> str:
        """Название праздника или «» — рабочий (учебный) день."""
        if d.isoformat() in _env_days("WORKDAYS_EXTRA"):
            return ""
        if (d.month, d.day) in FIXED:
            return HOLIDAY_NAMES.get((d.month, d.day), "Новогодние каникулы")
        if d in self.votes or d.isoformat() in _env_days("HOLIDAYS_EXTRA"):
            return "Нерабочий праздничный день"
        if d.weekday() == 0:                                     # перенос с субботы/воскресенья (кроме января)
            for back in (1, 2):
                p = d - timedelta(days=back)
                if p.month != 1 and (p.month, p.day) in FIXED:
                    return "Выходной за " + HOLIDAY_NAMES.get((p.month, p.day), "праздник").lower()
        return ""

    def kind_on(self, group: str, form: str, d: date) -> str:
        """Вид дня у группы по подтверждённому графику: theory, session, vacation, practice; «» — неизвестно."""
        key = (group, form)
        if key not in self._by_group:
            self._by_group[key] = self._periods_of(group, form)
        for kind, a, b in self._by_group[key]:
            if a <= d <= b:
                return kind
        return ""

    def periods_of(self, group: str, form: str) -> list[tuple[str, date, date]]:
        key = (group, form)
        if key not in self._by_group:
            self._by_group[key] = self._periods_of(group, form)
        return self._by_group[key]

    def _periods_of(self, group: str, form: str) -> list:
        from kug import group_key
        k = group_key(group)
        return self.periods.get((k[0], form, k[1]), []) if k else []


def _env_days(name: str) -> set[str]:
    return {x.strip() for x in env_date(name).split(",") if x.strip()}


def build(conn: sqlite3.Connection) -> Calendar:
    from kug import all_periods
    cal = Calendar()
    n_files = conn.execute("SELECT COUNT(*) FROM kug_files WHERE status IN ('ok', 'empty')").fetchone()[0]
    need = max(MIN_VOTES, n_files // 10)
    cal.votes = {date.fromisoformat(d) for d, n in
                 conn.execute("SELECT day, COUNT(*) FROM kug_holidays GROUP BY day").fetchall() if n >= need}
    cal.periods = all_periods(conn, confirmed_only=True)
    cal.semesters = _semesters(all_periods(conn, confirmed_only=False))
    return cal


WEEKLY_FORMS = ("Очная", "Очно-заочная")


def _semesters(periods: dict) -> list[tuple[date, date]]:
    """Осенний и весенний семестры по курсам очной и очно-заочной форм: (начало, конец) теории."""
    out = []
    for autumn in (True, False):
        starts, ends = Counter(), Counter()
        for (_code, form, _course), ps in periods.items():
            if form not in WEEKLY_FORMS:
                continue
            pick = [(a, b) for k, a, b in ps if k == "theory" and (a.month >= 8) == autumn]
            if pick:
                starts[pick[0][0]] += 1
                ends[pick[0][1]] += 1
        s = [d for d, n in starts.items() if n >= MIN_VOTES]
        e = [d for d, n in ends.items() if n >= MIN_VOTES]
        if s and e and min(s) <= max(e):
            out.append((min(s), max(e)))
    return sorted(out)


TTL_S = 60
_lock = threading.Lock()
_cache: dict = {"mtime": None, "cal": Calendar(), "at": 0.0}


def reset() -> None:
    _cache.update(mtime=None, cal=Calendar(), at=0.0)


def calendar() -> Calendar:
    """Календарь из feedback.db; перечитывается, когда файл базы изменился и не реже раза в минуту
    (две записи подряд могут не изменить отметку времени файла). Нет базы — пустой."""
    path = feedback_db_path()
    try:
        st = path.stat()
    except OSError:
        return Calendar()
    mtime = (st.st_mtime_ns, st.st_size, path)
    with _lock:
        if _cache["mtime"] != mtime or time.monotonic() - _cache["at"] > TTL_S:
            _cache["at"] = time.monotonic()
            from feedback import store
            try:
                conn = store.connect(path)
                try:
                    _cache["cal"] = build(conn)
                finally:
                    conn.close()
            except sqlite3.Error:
                _cache["cal"] = Calendar()
            _cache["mtime"] = mtime
        return _cache["cal"]
