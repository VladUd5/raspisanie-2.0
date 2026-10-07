from etl.flatten import flatten


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
