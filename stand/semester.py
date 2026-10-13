"""Календарь семестра. Семестр всегда начинается с верхней недели (в JSON парсера —
numerator), дальше верхняя и нижняя чередуются до конца семестра. Неделя — с понедельника:
если семестр начался в среду, эта неделя всё равно верхняя.

Даты задаются в окружении: «MM-DD» — каждый год, «YYYY-MM-DD» — один раз. Осень по умолчанию
1 сентября – 31 декабря; весна задаётся руками (SPRING_START), конец по умолчанию 30 июня.
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


def semesters(year: int) -> list[tuple[date, date]]:
    """Семестры, которые могут пересекаться с годом year (весна этого года, осень этого года)."""
    out = []
    autumn = (_resolve(env_date("AUTUMN_START") or "09-01", year), _resolve(env_date("AUTUMN_END") or "12-31", year))
    spring_start = _resolve(env_date("SPRING_START"), year)
    if spring_start and spring_start.year == year:
        out.append((spring_start, _resolve(env_date("SPRING_END") or "06-30", year)))
    if autumn[0] and autumn[1] and autumn[0].year == year:
        out.append(autumn)
    return [(s, e) for s, e in out if s and e and s <= e]


def semester_for(d: date) -> tuple[date, date] | None:
    for start, end in semesters(d.year):
        if start <= d <= end:
            return start, end
    return None


def week_type_on(d: date) -> str | None:
    """Верхняя или нижняя неделя на дату; None — вне семестра."""
    sem = semester_for(d)
    if sem is None:
        return None
    weeks = (monday(d) - monday(sem[0])).days // 7
    return UPPER if weeks % 2 == 0 else LOWER
