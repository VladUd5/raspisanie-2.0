from etl.flatten import drop_superseded, flatten


def test_every_lesson_becomes_a_cell(mini_buildings):
    assert len(flatten(mini_buildings)) == 10


def test_hierarchy_is_labelled(mini_buildings):
    cell = flatten(mini_buildings)[0]
    assert (cell.building, cell.institute, cell.study_form, cell.group_name) == (
        "УК1", "Институт агробизнеса", "Очная", "Б-Э-101")


def test_day_time_and_week(mini_buildings):
    cells = flatten(mini_buildings)
    assert (cells[0].day, cells[0].day_idx, cells[0].duration_h, cells[0].week_type) == ("понедельник", 0, 1.5, "both")
    assert [c.week_type for c in cells[1:3]] == ["numerator", "denominator"]


def test_missing_lists_are_tolerated():
    assert flatten(None) == []
    assert flatten([{"name": "uk1", "institutes": None}]) == []
    assert flatten([{"name": "uk1", "institutes": [{"name": "x", "forms": [{"name": "y", "groups": [
        {"name": "g", "schedule": {}}]}]}]}]) == []


def _zaoch(groups):
    return [{"name": "uk1", "institutes": [{"name": "institut-genetiki-i-agronomii", "forms": [
        {"name": "zaochnaya-forma-obucheniya", "groups": groups}]}]}]


def _group(name, source, dates):
    return {"name": name, "source": source, "schedule": {"days": [
        {"name": day, "date": date, "lessons": [{"time_from": "08:30", "time_to": "10:00", "subject": f"лек. X {source}"}]}
        for day, date in dates]}}


def test_date_and_source_reach_the_cell():
    cell = flatten(_zaoch([_group("Б-А-51", "1790000000_Б-А-51.pdf", [("вторник", "2026-09-29")])]))[0]
    assert (cell.date, cell.session_week, cell.source) == ("2026-09-29", "2026-09-28", "1790000000_Б-А-51.pdf")


def test_cell_without_date_has_no_session_week(mini_buildings):
    cell = flatten(mini_buildings)[0]
    assert (cell.date, cell.session_week) == ("", "")


def test_superseded_week_versions_are_dropped():
    old = _group("Б-А-51", "1790000000_Б-А-51 с 28.09.pdf", [("понедельник", "2026-09-28"), ("вторник", "2026-09-29")])
    new = _group("Б-А-51", "1790500000_Б-А-51 с 28.09 (испр).pdf", [("понедельник", "2026-09-28")])
    other_week = _group("Б-А-51", "1790100000_Б-А-51 с 05.10.pdf", [("понедельник", "2026-10-05")])
    other_group = _group("Б-А-41", "1790000000_Б-А-41 с 28.09.pdf", [("понедельник", "2026-09-28")])
    cells, dropped = drop_superseded(flatten(_zaoch([old, new, other_week, other_group])))
    assert dropped == 2
    assert sorted((c.group_name, c.date, c.source[:10]) for c in cells) == [
        ("Б-А-41", "2026-09-28", "1790000000"), ("Б-А-51", "2026-09-28", "1790500000"),
        ("Б-А-51", "2026-10-05", "1790100000")]
