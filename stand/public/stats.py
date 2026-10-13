"""Короткая аналитика для страниц группы, преподавателя, аудитории и дисциплины.

Считается по расписанию: еженедельные занятия раскладываются на даты семестра (верхняя/нижняя
неделя), занятия заочников — по своим датам (каждое — по версии, актуальной на его дату).
Час — академический: пара 90 минут = 2 часа. Поток для нескольких групп — одно занятие, а у
группы, преподавателя и аудитории одно время в один день считается один раз (подгруппы
и пары-варианты в одной клетке не удваивают нагрузку).
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from labels import PAIRS, SHORT_DAYS
from public import week
from semester import semester_for

MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
          "Ноябрь", "Декабрь"]
TYPE_LABEL = {"lec": "Лекции", "pr": "Практики", "lab": "Лабораторные", "exam": "Зачёты и экзамены", "oth": "Другое"}
TYPE_SHORT = {"lec": "Лек.", "pr": "Пр.", "lab": "Лаб.", "exam": "Зач.", "oth": "Зан."}
SLOTS_PER_DAY = len(PAIRS)


@dataclass
class Part:
    key: str
    label: str
    hours: int
    pct: int


@dataclass
class Row:
    title: str
    types: list[str]                 # ключи типов: lec, pr, lab, exam, oth
    people: list[str]                # преподаватели или группы — смотря по странице
    done: int
    total: int
    url: str = ""


@dataclass
class Stats:
    semester: tuple[date, date] | None
    week_hours: int = 0
    week_pairs: int = 0
    month: list[tuple[str, int, bool]] = field(default_factory=list)   # (месяц, часы, текущий)
    total: int = 0
    done: int = 0
    by_type: list[Part] = field(default_factory=list)
    by_form: list[Part] = field(default_factory=list)
    by_day: list[tuple[str, int]] = field(default_factory=list)        # (день, пар на текущей неделе)
    rows: list[Row] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    occupancy: int | None = None                                       # аудитория: % занятых пар недели
    heat: list[list[bool]] = field(default_factory=list)               # аудитория: [пара][день]

    @property
    def left(self) -> int:
        return self.total - self.done

    @property
    def current_month(self) -> tuple[str, int] | None:
        return next(((n, h) for n, h, cur in self.month if cur), None)

    @property
    def month_max(self) -> int:
        return max([h for _, h, _ in self.month] or [0]) or 1

    @property
    def day_max(self) -> int:
        return max([n for _, n in self.by_day] or [0]) or 1

    @property
    def busiest_month(self) -> str:
        return max(self.month, key=lambda x: x[1])[0] if self.month and any(h for _, h, _ in self.month) else ""


def _hours(les: week.Lesson) -> int:
    """Академические часы занятия: 45 минут — час; без конца пары — 2."""
    try:
        h1, m1 = map(int, les.time_from.split(":"))
        h2, m2 = map(int, les.time_to.split(":"))
        return max(1, round(((h2 * 60 + m2) - (h1 * 60 + m1)) / 45))
    except ValueError:
        return 2


def _parts(counter: Counter, labels: dict | None = None) -> list[Part]:
    total = sum(counter.values()) or 1
    return [Part(k, (labels or {}).get(k, k), v, round(100 * v / total)) for k, v in counter.most_common() if v]


def _unique_slots(occ: list[tuple[date, week.Lesson]]) -> list[tuple[date, week.Lesson]]:
    """Одно время в один день — одно занятие (подгруппы и варианты не удваивают часы)."""
    seen, out = set(), []
    for d, les in sorted(occ, key=lambda x: (x[0], x[1].time_from, x[1].subgroup)):
        if (d, les.time_from) in seen:
            continue
        seen.add((d, les.time_from))
        out.append((d, les))
    return out


def compute(items: pd.DataFrame, rows: pd.DataFrame, kind: str, today: date, current_week: week.Week,
            urls: dict) -> Stats:
    """urls: {"group": f, "teacher": f, "discipline": f} — адреса для таблицы."""
    sem = semester_for(today)
    st = Stats(sem)
    # эта неделя — по уже построенной сетке страницы
    wk = [les for d in current_week.days for les in d.lessons if not les.cancelled]
    wk_slots = {(d.date, les.time_from) for d in current_week.days for les in d.lessons if not les.cancelled}
    st.week_pairs = len(wk_slots)
    st.week_hours = sum(_hours(les) for d in current_week.days for les in _dedupe_day(d.lessons))
    st.by_day = [(SHORT_DAYS[i].capitalize(), len({l.time_from for l in d.lessons if not l.cancelled}))
                 for i, d in enumerate(current_week.days)]
    if kind == "room":
        times = sorted(PAIRS, key=PAIRS.get)
        st.heat = [[any(l.time_from == t and not l.cancelled for l in d.lessons) for d in current_week.days]
                   for t in times]
        st.occupancy = round(100 * len(wk_slots) / (SLOTS_PER_DAY * 6)) if wk_slots else 0
    st.counts = {
        "groups": len({g for les in wk for g in les.groups}) or rows["group_name"].nunique(),
        "teachers": len({t for ts in rows["teachers"] for t in ts}),
        "disciplines": rows["discipline"].replace("", pd.NA).dropna().nunique(),
        "rooms": len({r for rs in rows["rooms"] for r in rs}),
    }
    if sem is None:
        return st

    occ = week.expand(items, rows, sem[0], sem[1])
    slots = occ if kind == "discipline" else _unique_slots(occ)
    months: Counter = Counter()
    types: Counter = Counter()
    forms: Counter = Counter()
    for d, les in slots:
        h = _hours(les)
        months[(d.year, d.month)] += h
        types[les.type_class] += h
        for f in les.forms or ("",):
            forms[f] += h / max(1, len(les.forms))
        st.total += h
        if d < today:
            st.done += h
    m = date(sem[0].year, sem[0].month, 1)
    while m <= sem[1]:
        st.month.append((MONTHS[m.month - 1], months[(m.year, m.month)], (m.year, m.month) == (today.year, today.month)))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    st.by_type = _parts(types, TYPE_LABEL)
    st.by_form = _parts(Counter({k: round(v) for k, v in forms.items() if k}))
    st.rows = _table(slots, kind, today, urls)
    return st


def _dedupe_day(lessons: list[week.Lesson]) -> list[week.Lesson]:
    seen, out = set(), []
    for les in lessons:
        if les.cancelled or les.time_from in seen:
            continue
        seen.add(les.time_from)
        out.append(les)
    return out


def _table(slots: list[tuple[date, week.Lesson]], kind: str, today: date, urls: dict) -> list[Row]:
    """Группа и аудитория — по дисциплинам (кто ведёт); преподаватель — по дисциплинам (у каких групп);
    дисциплина — по группам (кто ведёт)."""
    acc: dict = defaultdict(lambda: {"types": set(), "people": Counter(), "done": 0, "total": 0})
    for d, les in slots:
        h = _hours(les)
        keys = list(les.groups) if kind == "discipline" else [les.discipline or "Занятие"]
        for k in keys:
            a = acc[k]
            a["types"].add(les.type_class)
            for p in (les.groups if kind == "teacher" else les.teachers):
                a["people"][p] += h
            a["total"] += h
            if d < today:
                a["done"] += h
    order = ["lec", "pr", "lab", "exam", "oth"]
    out = []
    for k, a in sorted(acc.items(), key=lambda x: -x[1]["total"]):
        link = urls["group"](k) if kind == "discipline" else urls["discipline"](k)
        out.append(Row(k, sorted(a["types"], key=order.index), [p for p, _ in a["people"].most_common()],
                       a["done"], a["total"], link))
    return out
