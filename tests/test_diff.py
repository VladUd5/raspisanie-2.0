from datetime import date

import pandas as pd

from etl.diff import compare, slots

TODAY = date(2026, 10, 13)


def frames(rows):
    """rows: (группа, дата, день, время, неделя, дисциплина, преподаватель, аудитория[, форма])."""
    les, tch, rms = [], [], []
    for i, r in enumerate(rows):
        group, d, day, time, week, disc, teacher, room, *form = r
        form = form[0] if form else ("Заочная" if d else "Очная")
        sw = ""
        if d:
            dd = date.fromisoformat(d)
            sw = date.fromordinal(dd.toordinal() - dd.weekday()).isoformat()
        les.append(dict(lesson_id=i, institute="И", study_form=form, group_name=group, date=d, day_idx=day,
                        time_from=time, week_type=week, subgroup=None, session_week=sw,
                        lesson_type="лекция", discipline=disc))
        tch.append(dict(lesson_id=i, teacher=teacher))
        rms.append(dict(lesson_id=i, room_building="УК1", room=room))
    return slots(pd.DataFrame(les), pd.DataFrame(tch), pd.DataFrame(rms))


BASE = [("Г-1", "", 0, "08:30", "both", "Физика", "Рыжова", "101"),
        ("Г-1", "", 0, "10:10", "both", "Химия", "Иванов", "102"),
        ("Г-1", "", 1, "08:30", "numerator", "Право", "Петров", "103"),
        ("Г-2", "", 2, "08:30", "both", "Физика", "Рыжова", "101")]


def kinds(df):
    return sorted(df["kind"])


def test_same_schedule_no_changes():
    assert compare(frames(BASE), frames(BASE), TODAY).empty


def test_changed_room_shows_before_after():
    new = [BASE[0][:7] + ("201",)] + BASE[1:]
    out = compare(frames(BASE), frames(new), TODAY, major_ratio=1)
    assert kinds(out) == ["changed"]
    r = out.iloc[0]
    assert "101" in r.before and "201" in r.after and r.rooms == "УК1 101, УК1 201"


def test_added_removed_moved():
    new = [BASE[0], ("Г-1", "", 3, "13:40", "both", "Химия", "Иванов", "102"), BASE[2],
           ("Г-2", "", 4, "08:30", "both", "Биология", "Сидоров", "104")]
    out = compare(frames(BASE), frames(new), TODAY, major_ratio=1)
    assert kinds(out) == ["added", "moved", "removed"]
    moved = out[out.kind == "moved"].iloc[0]
    assert moved.before.startswith("пн 10:10") and moved.after.startswith("чт 13:40")


def test_major_update_replaces_rows_per_form():
    new = [r[:5] + ("Новая " + r[5],) + r[6:] for r in BASE]
    out = compare(frames(BASE), frames(new), TODAY, major_ratio=0.3)
    assert kinds(out) == ["major_update"]
    assert "Очная" in out.iloc[0].after


ZAO = [("З-1", "2026-10-12", 0, "08:30", "both", "Физика", "Рыжова", "101"),
       ("З-1", "2026-10-14", 2, "08:30", "both", "Химия", "Иванов", "102"),
       ("З-1", "2026-10-15", 3, "08:30", "both", "Право", "Петров", "103")]


def test_new_session_week_is_publication_not_additions():
    new = ZAO + [("З-1", "2026-10-19", 0, "08:30", "both", "Физика", "Рыжова", "101")]
    out = compare(frames(ZAO), frames(new), TODAY)
    assert kinds(out) == ["week_published"]
    assert out.iloc[0].session_week == "2026-10-19"


def test_past_dates_are_history():
    new = [ZAO[0][:7] + ("999",)] + ZAO[1:]          # 12.10 уже прошло
    assert compare(frames(ZAO), frames(new), TODAY).empty
    new = ZAO[:1] + [ZAO[1][:7] + ("999",)] + ZAO[2:]   # 14.10 — ещё впереди
    assert kinds(compare(frames(ZAO), frames(new), TODAY, major_ratio=1)) == ["changed"]


def test_future_week_removed_but_past_week_silent():
    nxt = [("З-1", "2026-10-19", 0, "08:30", "both", "Физика", "Рыжова", "101")]
    out = compare(frames(ZAO + nxt), frames(ZAO), TODAY)
    assert kinds(out) == ["week_removed"]
    old_week = [("З-1", "2026-10-05", 0, "08:30", "both", "Физика", "Рыжова", "101")]
    assert compare(frames(old_week + ZAO), frames(ZAO), TODAY).empty


def test_empty_sides():
    assert kinds(compare(frames([]), frames(BASE), TODAY, major_ratio=10)) == ["added"] * 4


def test_week_split_of_merged_pair_is_not_a_change():
    # старый разбор: одна пара «каждую неделю» с двумя вариантами; новый — верхняя и нижняя отдельно
    old = BASE + [("Г-1", "", 4, "12:00", "both", "Земледелие", "Полетаев", "603"),
                  ("Г-1", "", 4, "12:00", "both", "Агрохимия", "Губов", "603")]
    new = BASE + [("Г-1", "", 4, "12:00", "numerator", "Земледелие", "Полетаев", "603"),
                  ("Г-1", "", 4, "12:00", "denominator", "Агрохимия", "Губов", "603")]
    assert compare(frames(old), frames(new), TODAY, major_ratio=1).empty


def test_week_split_with_new_content_is_still_a_change():
    old = BASE + [("Г-1", "", 4, "12:00", "both", "Земледелие", "Полетаев", "603")]
    new = BASE + [("Г-1", "", 4, "12:00", "numerator", "Генетика", "Степанова", "905")]
    out = compare(frames(old), frames(new), TODAY, major_ratio=1)
    assert kinds(out) == ["added", "removed"]
