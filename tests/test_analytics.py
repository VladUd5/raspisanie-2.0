import pandas as pd
import pytest

from analytics import queries as q
from etl.dictionary import Dictionary
from etl.load import connect, load_snapshot


@pytest.fixture
def frames(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    sid = load_snapshot(conn, mini_snapshot_path, dictionary=Dictionary.empty())
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
    # Пн 10:10: Б-БИ-101 каждую неделю + Б-Э-101 по нижней неделе («Иностанный» склеен).
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
    assert "[верх.]" in grid.loc["10:10", "понедельник"] and "[нижн.]" in grid.loc["10:10", "понедельник"]
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


SP = pd.DataFrame([
    ("teacher", "Торопова В.В.", "Торопова В.В.", "словарь", "h", "", "", 7, None),
    ("teacher", "Тороппова В.В.", "Торопова В.В.", "словарь", "h", "опечатка", "", 2, None),
    ("teacher", "Торопова", "Торопова В.В.", "словарь?", "l", "нет инициалов", "", 6, None),
    ("teacher", "Иванов И.И.", "Иванов И.И.", "как есть", "", "", "", 3, None),
    ("room", "УК3|С-305 а", "УК3|С-305а", "разбор", "", "пробел", "", 2, None),
    ("room", "УК3|С-305а", "УК3|С-305а", "разбор", "", "", "", 20, None),
], columns=["kind", "spelling", "canonical", "source", "confidence", "error_kinds", "note", "uses", "score"])


def test_error_summary():
    s = q.error_summary(SP, "teacher")
    assert list(s["error_kind"]) == ["нет инициалов", "опечатка"]
    assert list(s["uses"]) == [6, 2]


def test_spelling_cards_hide_singles_and_sort_by_weight():
    cards = q.spelling_cards(SP, "teacher")
    assert set(cards["canonical"]) == {"Торопова В.В."}
    assert list(cards["spelling"]) == ["Торопова В.В.", "Торопова", "Тороппова В.В."]
    assert cards["weight"].iloc[0] == 8
    assert set(q.spelling_cards(SP, "teacher", singles=True)["canonical"]) == {"Торопова В.В.", "Иванов И.И."}


def test_spelling_cards_filters_keep_whole_cards():
    cards = q.spelling_cards(SP, "teacher", error_kinds=("опечатка",))
    assert len(cards) == 3                        # карточка целиком, а не одна строка
    assert q.spelling_cards(SP, "teacher", sources=("правило",)).empty
    assert len(q.spelling_cards(SP, "teacher", query="ТОРОПП")) == 3


def test_spelling_cards_rooms_show_without_building():
    cards = q.spelling_cards(SP, "room")
    assert set(cards["shown"]) == {"С-305 а", "С-305а"} and set(cards["target"]) == {"С-305а"}


def test_spelling_cards_empty_frame():
    assert q.spelling_cards(SP.iloc[0:0], "group").empty


def test_single_corrected_spelling_is_a_card_by_default():
    # единственное написание, отличающееся от канона, — настоящее исправление, его нельзя прятать
    sp = pd.concat([SP, pd.DataFrame([("group", "ВТ -404", "ВТ-404", "правило", "", "пробел", "", 4, None),
                                      ("group", "Б-Э-101", "Б-Э-101", "как есть", "", "", "", 9, None)],
                                     columns=SP.columns)])
    cards = q.spelling_cards(sp, "group")
    assert list(cards["spelling"]) == ["ВТ -404"]


def test_rank_both_directions():
    df = pd.DataFrame({"name": ["в", "а", "б", "г"], "hours": [3.0, 1.0, 1.0, 5.0]})
    assert list(q.rank(df, "hours", "name")["name"]) == ["г", "в", "а", "б"]
    assert list(q.rank(df, "hours", "name", ascending=True)["name"]) == ["а", "б", "в", "г"]


def test_group_load_counts_pairs_per_week(frames):
    lessons, *_ = frames
    load = q.group_load(q.apply_filters(lessons, q.Filters()))
    pairs = dict(zip(load["group_name"], load["pairs"]))
    # верхняя + нижняя неделя в одном слоте = 1 пара; разрезанная ячейка = 0.5 + 0.5
    assert pairs == {"Б-Э-101": 4.0, "Б-БИ-101": 2.0, "бэ": 2.0}
    assert list(load.columns[:3]) == ["group_name", "institute", "study_form"]


def test_group_load_parallel_subgroups_are_one_pair():
    base = dict(institute="И", study_form="Очная", group_name="Г-101", day_idx=0, time_from="08:30",
                week_type="both", duration_h=1.5, per_week=1.0, hours=1.5)
    df = pd.DataFrame([{**base, "lesson_type": "лабораторная", "discipline": "Химия", "subgroup": 1},
                       {**base, "lesson_type": "лабораторная", "discipline": "Физика", "subgroup": 2}])
    assert q.group_load(df)["pairs"].tolist() == [1.0]


def test_group_options_put_broken_names_last():
    assert q.group_options(["Б-Э-101", "", "-101", "Б-А-301"]) == ["Б-А-301", "Б-Э-101", "-101", ""]


def test_distribution_bins_and_stats():
    bins, stats = q.distribution(pd.Series([0.75, 0.75, 1.5, 3.0, 4.5]), step=1.5)
    assert bins["count"].tolist() == [2, 1, 1, 1]
    assert bins["label"].tolist() == ["0–1.5", "1.5–3", "3–4.5", "4.5–6"]
    assert stats["count"] == 5 and stats["median"] == 1.5 and stats["min"] == 0.75 and stats["max"] == 4.5
    assert round(stats["mean"], 2) == 2.1


def test_distribution_empty():
    bins, stats = q.distribution(pd.Series([], dtype=float), step=1.0)
    assert bins.empty and stats == {}


def test_peak_hours_counts_groups_per_slot(frames):
    lessons, *_ = frames
    p = q.peak_hours(q.apply_filters(lessons, q.Filters()))
    assert list(p.index) == ["понедельник", "вторник", "среда"] and list(p.columns) == ["08:30", "10:10"]
    # верхняя + нижняя неделя у одной группы — одна пара; поточная лекция — по паре у каждой группы
    assert p.loc["понедельник"].tolist() == [2.0, 2.0]
    assert p.loc["вторник"].tolist() == [1.0, 1.0]
    assert p.loc["среда"].tolist() == [1.0, 1.0]


def test_room_fund_occupancy_by_building(frames):
    lessons, _, rooms, *_ = frames
    occ = q.room_fund_occupancy(q.apply_filters(lessons, q.Filters()), rooms)
    by = occ.set_index("building")
    assert by.loc["УК1", "rooms"] == 2 and by.loc["УК1", "slots"] == 6
    assert by.loc["УК1", "busy"] == 3.5 and round(by.loc["УК1", "occupancy"], 1) == 29.2
    assert round(by.loc["УК2", "occupancy"], 1) == 16.7
    assert round(by.loc["Прилегающие здания", "occupancy"], 1) == 16.7


def test_free_rooms_grid(frames):
    lessons, _, rooms, *_ = frames
    free = q.free_rooms(q.apply_filters(lessons, q.Filters()), rooms, "УК1")
    assert free.loc["понедельник"].tolist() == [1.0, 0.5]   # 422 занята; 422 — по числителю, 314 — вся пара
    assert free.loc["вторник"].tolist() == [1.0, 2.0]
    assert free.loc["среда"].tolist() == [2.0, 2.0]


def test_session_week_filter():
    """Неделя сессии отбирает датированные занятия заочки; недатированные заочные (неизвестная
    неделя) скрыты, другие формы обучения не затронуты."""
    lessons = pd.DataFrame({"cell_building": ["УК1"] * 4, "institute": ["И"] * 4,
                            "study_form": ["Заочная", "Заочная", "Заочная", "Очная"],
                            "group_name": ["А", "А", "А", "Б"], "day": ["понедельник"] * 4, "week_type": ["both"] * 4,
                            "lesson_type": ["лекция"] * 4, "duration_h": [1.5] * 4, "week_factor": [1.0] * 4,
                            "session_week": ["2026-09-28", "2026-10-05", "", ""]})
    out = q.apply_filters(lessons, q.Filters(session_weeks=("2026-10-05",)))
    assert list(zip(out["study_form"], out["session_week"])) == [("Заочная", "2026-10-05"), ("Очная", "")]
    assert len(q.apply_filters(lessons, q.Filters())) == 4
