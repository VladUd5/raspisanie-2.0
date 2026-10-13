"""Раскладка недели для студенческой страницы: замены, карточка «Сейчас», отмены у преподавателя."""
from datetime import date, datetime, timedelta

import pandas as pd

from public import week
from public.week import Day, Lesson, Week, _fold, upcoming
from semester import tz

MON = date(2026, 10, 12)


def les(t_from, t_to, disc, change=None, cancelled=False, d=MON):
    x = Lesson(t_from, t_to, "лекция", disc, ("Иванов И.И.",), (("УК1", "101"),), ("Г-1",), 0,
               date=d.isoformat(), cancelled=cancelled)
    x.change = change
    return x


def ch(kind, before="", after=""):
    return {"kind": kind, "before": before, "after": after, "day": "2026-10-09"}


def test_cancelled_plus_added_in_same_slot_is_one_replacement():
    old = les("12:00", "", "Химия", ch("removed", before="пн 12:00: лекция Химия · Иванов И.И. · УК1 101"), True)
    new = les("12:00", "13:30", "Физика", ch("added", after="пн 12:00: лекция Физика · Петров П.П. · УК1 101"))
    out = _fold([old, new])
    assert out == [new] and new.change["kind"] == "replaced" and "Химия" in new.change["before"]


def test_split_of_merged_variants_is_not_shown_as_change():
    old = les("10:10", "", "", ch("removed", before="пн 10:10: лекция А · И ║ лекция Б · П"), True)
    new = les("10:10", "11:40", "А", ch("added", after="пн 10:10 [верх.]: лекция А · И"))
    assert _fold([old, new]) == [new] and new.change is None


def test_only_week_mark_added_is_not_a_move():
    x = les("08:30", "10:00", "ОФП", ch("moved", before="ср 08:30: занятие ОФП", after="ср 08:30 [верх.]: занятие ОФП"))
    assert _fold([x]) == [x] and x.change is None


def _week(lessons_by_day):
    days = [Day(MON + timedelta(days=i), "д", False, lessons_by_day.get(i, [])) for i in range(6)]
    return Week(MON, "numerator", days, [], None, None, False)


def test_upcoming_now_next_later_done():
    a = les("10:10", "11:40", "Агрохимия")
    b = les("12:00", "13:30", "Овощеводство")
    c = les("08:30", "10:00", "Земледелие", d=MON + timedelta(days=2))
    w = _week({0: [a, b], 2: [c]})
    at = datetime(2026, 10, 12, 10, 52, tzinfo=tz())
    a.is_now = True
    u = upcoming(w, at)
    assert u.state == "now" and u.lesson is a and u.minutes == 48 and u.left_today == 1 and 40 < u.progress < 50
    a.is_now = False
    u = upcoming(w, datetime(2026, 10, 12, 11, 45, tzinfo=tz()))
    assert u.state == "next" and u.lesson is b and u.minutes == 15 and u.left_today == 0
    u = upcoming(w, datetime(2026, 10, 12, 14, 0, tzinfo=tz()))
    assert u.state == "later" and u.lesson is c
    assert upcoming(w, datetime(2026, 10, 14, 12, 0, tzinfo=tz())).state == "done"
    assert upcoming(w, datetime(2026, 10, 20, 9, 0, tzinfo=tz())) is None          # другая неделя


def test_rows_follow_pairs_and_week_title():
    w = _week({0: [les("10:10", "11:40", "А")], 3: [les("08:30", "10:00", "Б", d=MON + timedelta(days=3))]})
    assert [(r.pair, r.time_from) for r in w.rows] == [(1, "08:30"), (2, "10:10")]
    assert [len(c) for c in w.rows[0].cells] == [0, 0, 0, 1, 0, 0]
    assert w.title == "12 – 17 октября"


def test_teacher_page_shows_only_own_cancellations():
    changes = pd.DataFrame([
        dict(kind="removed", group_name="Г-1", date="", day_idx=0, time_from="12:00", week_type="both", subgroup=0,
             before="пн 12:00: лекция Химия · Иванов И.И. · УК1 101", after="", teachers="Иванов И.И.",
             rooms="УК1 101", day="2026-10-09"),
        dict(kind="removed", group_name="Г-1", date="", day_idx=1, time_from="12:00", week_type="both", subgroup=0,
             before="вт 12:00: лекция Право · Петров П.П. · УК1 102", after="", teachers="Петров П.П.",
             rooms="УК1 102", day="2026-10-09")])
    rows = pd.DataFrame({"group_name": ["Г-1"]})
    mine = week._cancelled(changes, rows, MON, ("teacher", "Иванов И.И."))
    assert [x.discipline for x in mine] == ["Химия"] and mine[0].lesson_type == "лекция"
    assert len(week._cancelled(changes, rows, MON, ("room", ("УК1", "102")))) == 1
    assert len(week._cancelled(changes, rows, MON)) == 2
