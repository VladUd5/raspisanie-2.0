"""Неделя занятий для группы, преподавателя или аудитории.

Очники и очно-заочники: занятия повторяются каждую неделю; на конкретной неделе остаются общие
и занятия её типа (верхняя/нижняя — по дате начала семестра). Вне семестра показываются обе
недели с пометками. Заочники: занятия с датами — из своей недели сессии; занятия заочников без
даты (файлы без дат) — отдельным списком «без даты».

Для страницы неделя раскладывается в сетку: строки — пары (время начала), столбцы — дни.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from labels import DAYS, PAIRS, SHORT_DAYS
from semester import monday, now, semester_for, week_type_on

WEEK_MARK = {"numerator": "верхняя неделя", "denominator": "нижняя неделя"}
TYPE_SHORT = {"лекция": "ЛЕК", "практика": "ПР", "лабораторная": "ЛАБ", "семинар": "СЕМ", "консультация": "КОНС",
              "зачёт": "ЗАЧЁТ", "экзамен": "ЭКЗАМЕН", "не определён": "ЗАН"}
TYPE_TITLE = {"не определён": "Занятие", "": "Занятие"}
COLORS = 10                                   # цветов для дисциплин в style.css: .c0 … .c9
# Формы обучения: код для адреса (?form=), короткая пометка на карточке, порядок в переключателе.
FORMS = {"Очная": ("och", "очн."), "Очно-заочная": ("ochzaoch", "оч.-заочн."), "Заочная": ("zaoch", "заочн.")}
FORM_BY_CODE = {code: name for name, (code, _) in FORMS.items()}


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
    forms: tuple = ()             # формы обучения групп занятия («Очная», «Заочная»…)

    @property
    def type_short(self) -> str:
        return TYPE_SHORT.get(self.lesson_type, (self.lesson_type or "")[:4].upper())

    @property
    def type_title(self) -> str:
        return TYPE_TITLE.get(self.lesson_type, (self.lesson_type or "").capitalize())

    @property
    def pair(self) -> int | None:
        return PAIRS.get(self.time_from)

    @property
    def form_marks(self) -> list[str]:
        """Пометки форм, кроме очной: «заочн.», «оч.-заочн.»."""
        return [FORMS[f][1] for f in FORMS if f in self.forms and f != "Очная"]


@dataclass
class Day:
    date: date
    name: str
    is_today: bool
    lessons: list[Lesson] = field(default_factory=list)

    @property
    def short(self) -> str:
        return SHORT_DAYS[self.date.weekday()]


@dataclass
class Row:
    """Строка сетки: одно время начала, по списку занятий на каждый день."""
    time_from: str
    time_to: str
    cells: list[list[Lesson]]

    @property
    def pair(self) -> int | None:
        return PAIRS.get(self.time_from)


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
    def title(self) -> str:
        """«12 – 17 октября» или «28 сентября – 3 октября»."""
        end = self.monday + timedelta(days=5)
        if end.month == self.monday.month:
            return f"{self.monday.day} – {end.day} {MONTHS[end.month - 1]}"
        return f"{self.monday.day} {MONTHS[self.monday.month - 1]} – {end.day} {MONTHS[end.month - 1]}"

    @property
    def number(self) -> int | None:
        """Номер недели семестра (с 1) или None вне семестра."""
        sem = semester_for(self.monday) or semester_for(self.monday + timedelta(days=5))
        if sem is None:
            return None
        return (self.monday - monday(sem[0])).days // 7 + 1

    @property
    def empty(self) -> bool:
        return not any(d.lessons for d in self.days) and not self.undated

    @property
    def rows(self) -> list[Row]:
        times: dict[str, str] = {}
        for d in self.days:
            for les in d.lessons:
                if les.time_to and les.time_to > times.get(les.time_from, ""):
                    times[les.time_from] = les.time_to
                times.setdefault(les.time_from, "")
        out = []
        for t in sorted(times):
            out.append(Row(t, times[t], [[x for x in d.lessons if x.time_from == t] for d in self.days]))
        return out


MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]


def select(items: pd.DataFrame, kind: str, key) -> pd.DataFrame:
    if kind == "group":
        return items[items["group_name"] == key]
    if kind == "teacher":
        return items[[key in t for t in items["teachers"]]]
    return items[[key in r for r in items["rooms"]]]


def forms_of(rows: pd.DataFrame) -> list[str]:
    """Формы обучения в строках — в порядке FORMS."""
    present = set(rows["study_form"])
    return [f for f in FORMS if f in present] + sorted(present - set(FORMS))


def colors(rows: pd.DataFrame) -> dict[str, int]:
    """Цвет дисциплины: номер по алфавиту среди дисциплин страницы — один и тот же на всех неделях."""
    return {d: i % COLORS for i, d in enumerate(sorted(set(rows["discipline"])))}


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


def build(items: pd.DataFrame, rows: pd.DataFrame, m: date, changes: pd.DataFrame, at: datetime | None = None,
          who: tuple | None = None) -> Week:
    """who — (kind, key) страницы: отмены у преподавателя и аудитории — только их собственные."""
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
    for c in _cancelled(changes, rows, m, who):
        lessons_by_day.setdefault(c.date and date.fromisoformat(c.date), []).append(c)
    for day in days:
        lessons = lessons_by_day.get(day.date, [])
        for les in lessons:
            les.date = day.date.isoformat()
            les.is_now = (day.is_today and not les.cancelled and les.time_from <= at.strftime("%H:%M") < les.time_to)
            les.change = les.change or _change_for(changes, les, day.date)
        day.lessons = sorted(_fold(lessons), key=lambda x: (x.time_from, x.subgroup, x.cancelled))

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


@dataclass
class Upcoming:
    state: str            # now — идёт; next — следующая сегодня; later — в другой день этой недели; done — на неделе всё
    lesson: Lesson | None
    day: Day | None
    minutes: int = 0      # now: до конца; next: до начала
    progress: int = 0     # now: сколько процентов пары прошло
    left_today: int = 0   # сколько ещё занятий сегодня после этого


def upcoming(week: Week, at: datetime | None = None) -> Upcoming | None:
    """Карточка «Сейчас»: только для текущей недели."""
    at = at or now()
    hm = at.strftime("%H:%M")
    if not week.monday <= at.date() <= week.monday + timedelta(days=6):
        return None
    future = [(d, les) for d in week.days for les in d.lessons if not les.cancelled
              and (d.date > at.date() or (d.date == at.date() and les.time_to > hm))]
    if not future:
        return Upcoming("done", None, None) if any(d.lessons for d in week.days) else None
    d, les = future[0]
    today_left = len({x.time_from for dd, x in future if dd.date == at.date()})
    if les.is_now:
        end, start = _at(at, les.time_to), _at(at, les.time_from)
        total = max((end - start).total_seconds(), 1)
        return Upcoming("now", les, d, _mins(end - at), int(100 * (at - start).total_seconds() / total), today_left - 1)
    if d.date == at.date():
        return Upcoming("next", les, d, _mins(_at(at, les.time_from) - at), 0, today_left - 1)
    return Upcoming("later", les, d)


def _at(at: datetime, hm: str) -> datetime:
    h, m = map(int, hm.split(":"))
    return at.replace(hour=h, minute=m, second=0, microsecond=0)


def _mins(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 60))


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
            if r.study_form not in les.forms:
                les.forms = les.forms + (r.study_form,)
            continue
        les = Lesson(r.time_from, r.time_to, r.lesson_type, r.discipline, r.teachers, r.rooms, (r.group_name,),
                     int(r.subgroup), mark, day_idx=int(r.day_idx), forms=(r.study_form,))
        seen[key] = les
        out.setdefault(d, []).append(les)
    return out


def day_name(idx: int) -> str:
    return DAYS[idx] if 0 <= idx < len(DAYS) else ""


_SLOT = re.compile(r"\s*\[[^\]]*\]")


def content(text: str) -> list[str]:
    """Из «пт 12:00 [верх.]: лекция X · Y ║ лекция Z» — варианты содержимого: ["лекция X · Y", "лекция Z"]."""
    body = (text or "").split(": ", 1)[-1]
    return [x.strip() for x in body.split("║") if x.strip()]


def _slot(text: str) -> str:
    """«пт 12:00 [верх.]» → «пт 12:00»: слот без пометки недели."""
    return _SLOT.sub("", (text or "").split(": ", 1)[0]).strip()


def _fold(lessons: list[Lesson]) -> list[Lesson]:
    """Отмена и новое занятие в том же слоте — одна «замена». Если новое занятие было одним из
    вариантов отменённой строки (так старый разбор склеивал верхнюю и нижнюю неделю) или занятие
    лишь получило пометку недели — для студента ничего не поменялось, пометку не показываем."""
    out = []
    for les in lessons:
        ch = les.change
        if ch and ch["kind"] == "moved" and _slot(ch["before"]) == _slot(ch["after"]) \
                and content(ch["before"]) == content(ch["after"]):
            les.change = None
    for c in [x for x in lessons if x.cancelled]:
        same = [x for x in lessons if not x.cancelled and x.time_from == c.time_from and x.subgroup == c.subgroup]
        added = [x for x in same if x.change and x.change["kind"] == "added"]
        if not added:
            continue
        was = content(c.change["before"])
        for a in added:
            if set(content(a.change["after"])) <= set(was):
                a.change = None
            else:
                a.change = {"kind": "replaced", "before": "; ".join(was), "after": a.change["after"],
                            "day": a.change["day"]}
        c.change = None                                    # отмена поглощена — строку убираем
    for les in lessons:
        if les.cancelled and les.change is None:
            continue
        out.append(les)
    return out


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


def _parse(desc: str) -> tuple[str, str]:
    """«лекция Агрохимия · Губов В.И. · УК1 603» → ("лекция", "Агрохимия")."""
    head = desc.split(" · ", 1)[0].strip()
    for t in sorted(TYPE_SHORT, key=len, reverse=True):
        if head.startswith(t + " "):
            return t, head[len(t) + 1:].strip(" —")
    return "", head.strip(" —")


def _cancelled(changes: pd.DataFrame, rows: pd.DataFrame, m: date, who: tuple | None = None) -> list[Lesson]:
    """Отменённые за последние дни занятия этой недели — зачёркнутыми строками."""
    if changes is None or changes.empty:
        return []
    groups = set(rows["group_name"])
    c = changes[(changes["kind"] == "removed") & changes["group_name"].isin(groups)]
    if who and who[0] == "teacher":
        c = c[[who[1] in t.split(", ") for t in c["teachers"]]]
    elif who and who[0] == "room":
        c = c[[f"{who[1][0]} {who[1][1]}" in r.split(", ") for r in c["rooms"]]]
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
        parsed = [_parse(x) for x in content(r.before)]
        types = {t for t, _ in parsed}
        les = Lesson(r.time_from, "", types.pop() if len(types) == 1 else "",
                     "; ".join(dict.fromkeys(x for _, x in parsed if x)), (), (), (r.group_name,),
                     int(r.subgroup or 0), date=d.isoformat(), cancelled=True,
                     forms=(r.study_form,) if getattr(r, "study_form", "") else ())
        les.change = {"kind": "removed", "before": r.before, "after": "", "day": r.day}
        out.append(les)
    return out
