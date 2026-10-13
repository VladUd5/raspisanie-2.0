"""Неделя занятий для группы, преподавателя или аудитории.

Очники и очно-заочники: занятия повторяются каждую неделю; на конкретной неделе остаются общие
и занятия её типа (верхняя/нижняя — по дате начала семестра). Вне семестра показываются обе
недели с пометками. Заочники: занятия с датами — из своей недели сессии; занятия заочников без
даты (файлы без дат) — отдельным списком «без даты».
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from labels import DAYS
from semester import monday, now, week_type_on

WEEK_MARK = {"numerator": "верхняя неделя", "denominator": "нижняя неделя"}
TYPE_SHORT = {"лекция": "ЛЕК", "практика": "ПР", "лабораторная": "ЛАБ", "семинар": "СЕМ", "консультация": "КОНС",
              "зачёт": "ЗАЧЁТ", "экзамен": "ЭКЗАМЕН", "не определён": "ЗАН"}


@dataclass
class Lesson:
    time_from: str
    time_to: str
    lesson_type: str
    discipline: str
    teachers: tuple
    rooms: tuple
    groups: tuple
    subgroup: int
    week_mark: str = ""           # «верхняя неделя» — только когда неделя не определена (вне семестра)
    date: str = ""
    is_now: bool = False
    change: dict | None = None    # {"kind", "before", "after", "day"}
    cancelled: bool = False
    day_idx: int = 0              # для занятий без даты — день недели

    @property
    def type_short(self) -> str:
        return TYPE_SHORT.get(self.lesson_type, (self.lesson_type or "")[:4].upper())


@dataclass
class Day:
    date: date
    name: str
    is_today: bool
    lessons: list[Lesson] = field(default_factory=list)


@dataclass
class Week:
    monday: date
    week_type: str | None                     # numerator / denominator / None (вне семестра)
    days: list[Day]
    undated: list[Lesson]                     # заочники без даты
    prev: date | None
    next: date | None
    dated_only: bool                          # только заочное расписание (листаем недели сессии)

    @property
    def label(self) -> str:
        end = self.monday + timedelta(days=5)
        return f"{self.monday:%d.%m}–{end:%d.%m}"

    @property
    def empty(self) -> bool:
        return not any(d.lessons for d in self.days) and not self.undated


def select(items: pd.DataFrame, kind: str, key) -> pd.DataFrame:
    if kind == "group":
        return items[items["group_name"] == key]
    if kind == "teacher":
        return items[[key in t for t in items["teachers"]]]
    return items[[key in r for r in items["rooms"]]]


def default_monday(rows: pd.DataFrame, today: date) -> date:
    """Текущая неделя (в воскресенье — следующая). Если занятия только с датами и на этой неделе их
    нет — ближайшая следующая неделя сессии, иначе последняя прошедшая."""
    m = monday(today + timedelta(days=1) if today.weekday() == 6 else today)
    weeks = sorted({date.fromisoformat(w) for w in rows["session_week"] if w})
    if (rows["date"] == "").any() or not weeks or m in weeks:
        return m
    future = [w for w in weeks if w > m]
    return future[0] if future else weeks[-1]


def _dated_groups(items: pd.DataFrame) -> set[tuple]:
    d = items[items["date"] != ""]
    return set(zip(d["institute"], d["study_form"], d["group_name"]))


def build(items: pd.DataFrame, rows: pd.DataFrame, m: date, changes: pd.DataFrame, at: datetime | None = None) -> Week:
    at = at or now()
    today = at.date()
    dated_groups = _dated_groups(items)
    in_zao = [(i, f, g) in dated_groups for i, f, g in zip(rows["institute"], rows["study_form"], rows["group_name"])]
    rows = rows.assign(_zao=in_zao)
    weekly = rows[(rows["date"] == "") & ~rows["_zao"]]
    undated = rows[(rows["date"] == "") & rows["_zao"]]
    dated = rows[rows["session_week"] == m.isoformat()]

    wt = week_type_on(m) or week_type_on(m + timedelta(days=5))
    days = [Day(m + timedelta(days=i), DAYS[i], m + timedelta(days=i) == today) for i in range(6)]
    picked = []
    for r in weekly.itertuples():
        if not 0 <= r.day_idx < 6:
            continue
        d = m + timedelta(days=r.day_idx)
        dwt = week_type_on(d)
        if dwt is None and wt is not None:
            continue                      # день до начала / после конца семестра
        if dwt is not None and r.week_type not in ("both", dwt):
            continue
        picked.append((d, r, "" if dwt is not None else WEEK_MARK.get(r.week_type, "")))
    for r in dated.itertuples():
        picked.append((date.fromisoformat(r.date), r, ""))

    lessons_by_day: dict[date, list[Lesson]] = {d.date: [] for d in days}
    for d, part in _merge(picked).items():
        if d in lessons_by_day:
            lessons_by_day[d].extend(part)
    for c in _cancelled(changes, rows, m):
        lessons_by_day.setdefault(c.date and date.fromisoformat(c.date), []).append(c)
    for day in days:
        day.lessons = sorted(lessons_by_day.get(day.date, []), key=lambda x: (x.time_from, x.subgroup, x.cancelled))
        for les in day.lessons:
            les.date = day.date.isoformat()
            les.is_now = (day.is_today and not les.cancelled and les.time_from <= at.strftime("%H:%M") < les.time_to)
            les.change = les.change or _change_for(changes, les, day.date)

    undated_lessons = [l for _, part in sorted(_merge([(None, r, "") for r in undated.itertuples()]).items(),
                                               key=lambda x: str(x[0])) for l in part]
    undated_lessons.sort(key=lambda x: (x.day_idx, x.time_from))

    dated_only = weekly.empty and not dated.empty or (weekly.empty and undated.empty)
    weeks = sorted({date.fromisoformat(w) for w in rows["session_week"] if w})
    if weekly.empty and weeks:
        prev = max([w for w in weeks if w < m], default=None)
        nxt = min([w for w in weeks if w > m], default=None)
    else:
        prev, nxt = m - timedelta(days=7), m + timedelta(days=7)
    return Week(m, wt, days, undated_lessons, prev, nxt, dated_only)


def _merge(picked: list[tuple]) -> dict:
    """Поток для нескольких групп — одно занятие со списком групп."""
    out: dict = {}
    seen: dict = {}
    for d, r, mark in picked:
        key = (d, r.time_from, r.week_type if mark else "", r.lesson_type, r.discipline, r.teachers, r.rooms, r.subgroup)
        if key in seen:
            les = seen[key]
            if r.group_name not in les.groups:
                les.groups = tuple(sorted(les.groups + (r.group_name,)))
            continue
        les = Lesson(r.time_from, r.time_to, r.lesson_type, r.discipline, r.teachers, r.rooms, (r.group_name,),
                     int(r.subgroup), mark, day_idx=int(r.day_idx))
        seen[key] = les
        out.setdefault(d, []).append(les)
    return out


def day_name(idx: int) -> str:
    return DAYS[idx] if 0 <= idx < len(DAYS) else ""


def _change_for(changes: pd.DataFrame, les: Lesson, d: date) -> dict | None:
    if changes is None or changes.empty or les.cancelled:
        return None
    c = changes[changes["kind"].isin(["changed", "moved", "added"]) & changes["group_name"].isin(les.groups)
                & (changes["time_from"] == les.time_from)]
    c = c[(c["date"] == d.isoformat()) | ((c["date"] == "") & (c["day_idx"] == d.weekday()))]
    if c.empty:
        return None
    r = c.iloc[0]
    return {"kind": r["kind"], "before": r["before"], "after": r["after"], "day": r["day"]}


def _cancelled(changes: pd.DataFrame, rows: pd.DataFrame, m: date) -> list[Lesson]:
    """Отменённые за последние дни занятия этой недели — зачёркнутыми строками."""
    if changes is None or changes.empty:
        return []
    groups = set(rows["group_name"])
    c = changes[(changes["kind"] == "removed") & changes["group_name"].isin(groups)]
    out = []
    for r in c.itertuples():
        if r.date:
            d = date.fromisoformat(r.date)
            if monday(d) != m:
                continue
        else:
            if not 0 <= r.day_idx < 6:
                continue
            d = m + timedelta(days=int(r.day_idx))
            dwt = week_type_on(d)
            if dwt is not None and r.week_type not in ("both", dwt):
                continue
        les = Lesson(r.time_from, "", "", r.before.split(": ", 1)[-1], (), (), (r.group_name,), int(r.subgroup or 0),
                     date=d.isoformat(), cancelled=True)
        les.change = {"kind": "removed", "before": r.before, "after": "", "day": r.day}
        out.append(les)
    return out
