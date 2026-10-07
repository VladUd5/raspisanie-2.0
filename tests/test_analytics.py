import pytest

from analytics import queries as q
from etl.load import connect, load_snapshot


@pytest.fixture
def frames(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    sid = load_snapshot(conn, mini_snapshot_path)
    return q.lessons_frame(conn, sid), q.teachers_frame(conn, sid), q.rooms_frame(conn, sid), conn, sid


def _load(frames, **filters):
    lessons, teachers, rooms, *_ = frames
    return q.teacher_load(q.apply_filters(lessons, q.Filters(**filters)), teachers, rooms).set_index("teacher")


def test_stream_lecture_counted_once_and_numerator_is_half(frames):
    # лекция на 2 группы = 1.5 ч один раз; практика по числителю = 0.75 ч
    assert _load(frames).loc["Шалаева Н.В.", "hours"] == pytest.approx(2.25)


def test_full_weeks_switch(frames):
    assert _load(frames, full_weeks=True).loc["Шалаева Н.В.", "hours"] == pytest.approx(3.0)


def test_split_cell_counts_one_over_n(frames):
    # ячейка «лек. … пр.з. …» разрезана на 2 занятия: каждое 1.5 × 1/2
    assert _load(frames).loc["Аленичева Н.В.", "hours"] == pytest.approx(1.5)
    # «полной парой» каждый кусок = 1, но слот у преподавателя занят не больше одной пары
    assert _load(frames, full_weeks=True).loc["Аленичева Н.В.", "hours"] == pytest.approx(1.5)


def test_service_cells_are_not_load(frames):
    lessons, *_ = frames
    assert not lessons["subject_raw"].str.contains("переход").any()


def test_teacher_counts_groups_across_institutes(frames):
    assert _load(frames).loc["Шалаева Н.В.", "groups"] == 2


def test_same_room_number_in_two_buildings_is_two_rooms(frames):
    lessons, _, rooms, *_ = frames
    load = q.room_load(q.apply_filters(lessons, q.Filters()), rooms).set_index("room_label")
    assert load.loc["УК1 · 422", "hours"] == pytest.approx(2.25)
    assert load.loc["УК2 · 422", "hours"] == pytest.approx(1.5)


def test_room_scope(frames):
    lessons, _, rooms, *_ = frames
    f = q.apply_filters(lessons, q.Filters())
    assert set(q.room_load(f, rooms, "adjacent")["room_label"]) == {"Прилегающие здания · Физ. зал"}
    assert "Прилегающие здания · Физ. зал" not in set(q.room_load(f, rooms, "main")["room_label"])


def test_room_discipline_matrix(frames):
    lessons, _, rooms, *_ = frames
    m = q.room_discipline_matrix(q.apply_filters(lessons, q.Filters()), rooms)
    assert m.loc["УК1 · 422", "История России"] == pytest.approx(2.25)
    # Пн 10:10: Б-БИ-101 каждую неделю + Б-Э-101 по знаменателю («Иностанный» склеен).
    # 1.0 + 0.5 > одной пары в слоте → срезается до 1 пары = 1.5 ч
    assert m.loc["УК1 · 314", "Иностранный язык"] == pytest.approx(1.5)


def _synthetic(rows):
    """Минимальные кадры для проверки наложений: одна строка — одно занятие."""
    import pandas as pd
    base = dict(cell_building="УК1", institute="И", study_form="Очная", day="понедельник", day_idx=0,
                time_from="08:30", duration_h=1.5, week_type="both", week_factor=1.0, lesson_type="лекция")
    lessons = pd.DataFrame([{**base, "lesson_id": i, "cell_id": i, "group_name": g, "discipline": d}
                            for i, (g, d, _) in enumerate(rows)])
    teachers = pd.DataFrame([{"lesson_id": i, "teacher": t} for i, (_, _, t) in enumerate(rows)])
    rooms = pd.DataFrame([{"lesson_id": i, "room_building": "УК1", "room": "101"} for i in range(len(rows))])
    return q.apply_filters(lessons, q.Filters()), teachers, rooms


def test_slot_overlap_is_capped_at_one_pair():
    # три разных занятия у одного преподавателя в одном слоте — ошибка данных,
    # но загруженность слота не может быть больше одной пары
    lessons, teachers, rooms = _synthetic([("Г1", "А", "Иванов И.И."), ("Г2", "Б", "Иванов И.И."),
                                           ("Г3", "В", "Иванов И.И.")])
    load = q.teacher_load(lessons, teachers, rooms).set_index("teacher")
    assert load.loc["Иванов И.И.", "hours"] == pytest.approx(1.5)
    assert load.loc["Иванов И.И.", "lessons"] == pytest.approx(1.0)
    assert q.room_load(lessons, rooms)["hours"].iloc[0] == pytest.approx(1.5)
    assert q.room_discipline_matrix(lessons, rooms).sum().sum() == pytest.approx(1.5)


def test_teacher_conflicts_listed():
    lessons, teachers, _ = _synthetic([("Г1", "А", "Иванов И.И."), ("Г2", "Б", "Иванов И.И."),
                                       ("Г3", "А", "Петров П.П.")])
    conflicts = q.teacher_conflicts(lessons, teachers)
    assert conflicts[["teacher", "events", "disciplines"]].values.tolist() == [["Иванов И.И.", 2, "А, Б"]]


def test_split_cell_is_not_a_conflict(frames):
    lessons, teachers, *_ = frames
    conflicts = q.teacher_conflicts(q.apply_filters(lessons, q.Filters()), teachers)
    assert "Аленичева Н.В." not in set(conflicts["teacher"])


def test_filters(frames):
    lessons, *_ = frames
    f = q.apply_filters(lessons, q.Filters(institutes=("Институт инженерии и робототехники",)))
    assert set(f["group_name"]) == {"бэ"}
    f = q.apply_filters(lessons, q.Filters(week_types=("numerator",)))
    assert len(f) == 1


def test_teacher_heatmap_and_schedule(frames):
    lessons, teachers, rooms, *_ = frames
    f = q.apply_filters(lessons, q.Filters())
    hm = q.teacher_heatmap(f, teachers, "Шалаева Н.В.")
    assert hm.loc["понедельник", "08:30"] == pytest.approx(1.5)
    sched = q.teacher_schedule(f, teachers, rooms, "Шалаева Н.В.")
    assert sched.iloc[0]["groups"] == "Б-БИ-101, Б-Э-101"


def test_discipline_summary(frames):
    lessons, teachers, *_ = frames
    s = q.discipline_summary(q.apply_filters(lessons, q.Filters()), teachers).set_index("discipline")
    assert s.loc["История России", "hours"] == pytest.approx(2.25)
    assert s.loc["История России", "groups"] == 2


def test_group_grid_and_daily_load(frames):
    lessons, teachers, rooms, *_ = frames
    f = q.apply_filters(lessons, q.Filters())
    grid = q.group_grid(f, teachers, rooms, "Б-Э-101")
    assert "[числ.]" in grid.loc["10:10", "понедельник"] and "[знам.]" in grid.loc["10:10", "понедельник"]
    daily = q.group_daily_load(f, "Б-Э-101").set_index("day")
    assert daily.loc["понедельник", "hours"] == pytest.approx(3.0)


def test_quality_shares_and_overview(frames):
    lessons, teachers, rooms, conn, sid = frames
    shares = q.quality_shares(q.cells_quality_frame(conn, sid)).set_index("field")
    assert shares.loc["ячейка разрезана", "share"] == pytest.approx(20.0)
    counts = q.overview_counts(lessons, teachers, rooms)
    assert counts["groups"] == 3 and counts["lessons"] == 10
    assert len(q.service_cells(conn, sid)) == 1


def test_snapshots_sorted_by_real_time_across_timezones(tmp_path, mini_snapshot_path):
    import json
    from etl.load import connect, load_snapshot
    conn = connect(tmp_path / "t.db")
    data = json.loads(mini_snapshot_path.read_text())
    for name, stamp in [("a.json", "2026-10-07T12:00:00+03:00"), ("b.json", "2026-10-07T09:30:00+00:00")]:
        p = tmp_path / name
        p.write_text(json.dumps({**data, "collected_at": stamp}, ensure_ascii=False))
        load_snapshot(conn, p)
    # 09:30 UTC = 12:30 МСК — позже, чем 12:00 МСК
    assert q.snapshots(conn)["file_name"].tolist() == ["b.json", "a.json"]
