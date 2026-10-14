"""Календарь семестра.

Откуда даты: заданные в окружении («MM-DD» — каждый год, «YYYY-MM-DD» — один раз) → по графикам
учебного процесса (academic.py: начало и конец теоретического обучения по большинству графиков) →
по умолчанию осень 1 сентября – 31 декабря (весны по умолчанию нет).

Верхняя и нижняя недели (в JSON парсера — numerator/denominator) чередуются, неделя — с
понедельника. Как в графиках вуза (строка «В/Н»), отсчёт идёт от недели 1 сентября и не
прерывается зимой: неделя 1 сентября — верхняя. Если же семестр задан в окружении, он сам
начинается с верхней недели (как было до графиков).
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import env_date, tz_name

UPPER, LOWER = "numerator", "denominator"


def tz() -> ZoneInfo:
    return ZoneInfo(tz_name())


def now() -> datetime:
    return datetime.now(tz())


def today() -> date:
    return now().date()


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _resolve(value: str, year: int) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value) if len(value) == 10 else date.fromisoformat(f"{year}-{value}")
    except ValueError:
        return None


def _graph_semesters() -> list[tuple[date, date]]:
    try:
        import academic
        return academic.calendar().semesters
    except Exception:                                       # noqa: BLE001 — без графиков работают .env и умолчания
        return []


def _semesters(year: int) -> list[tuple[date, date, bool]]:
    """Семестры, начинающиеся в году year: (начало, конец, задан в окружении)."""
    graph = [(a, b) for a, b in _graph_semesters() if a.year == year]
    g_spring = next(((a, b) for a, b in graph if a.month < 8), None)
    g_autumn = next(((a, b) for a, b in graph if a.month >= 8), None)
    out = []
    if env_date("SPRING_START"):
        spring_start = _resolve(env_date("SPRING_START"), year)
        if spring_start and spring_start.year == year:
            out.append((spring_start, _resolve(env_date("SPRING_END") or "06-30", year), True))
    elif g_spring:
        end = _resolve(env_date("SPRING_END"), year) if env_date("SPRING_END") else g_spring[1]
        out.append((g_spring[0], end, False))
    if env_date("AUTUMN_START") or env_date("AUTUMN_END") or not g_autumn:
        a = _resolve(env_date("AUTUMN_START") or "09-01", year)
        b = _resolve(env_date("AUTUMN_END") or "12-31", year)
        out.append((a, b, bool(env_date("AUTUMN_START"))))
    else:
        out.append((g_autumn[0], g_autumn[1], False))
    return [(s, e, env) for s, e, env in out if s and e and s <= e]


def semesters(year: int) -> list[tuple[date, date]]:
    """Семестры, начинающиеся в году year (весна этого года, осень этого года)."""
    return [(s, e) for s, e, _ in _semesters(year)]


def _semester(d: date) -> tuple[date, date, bool] | None:
    for year in (d.year, d.year - 1):                       # осень по графику кончается в январе
        for start, end, env in _semesters(year):
            if start <= d <= end:
                return start, end, env
    return None


def semester_for(d: date) -> tuple[date, date] | None:
    sem = _semester(d)
    return (sem[0], sem[1]) if sem else None


def week_type_on(d: date) -> str | None:
    """Верхняя или нижняя неделя на дату; None — вне семестра."""
    sem = _semester(d)
    if sem is None:
        return None
    start, _end, env = sem
    anchor = start if env else date(start.year if start.month >= 8 else start.year - 1, 9, 1)
    weeks = (monday(d) - monday(anchor)).days // 7
    return UPPER if weeks % 2 == 0 else LOWER
