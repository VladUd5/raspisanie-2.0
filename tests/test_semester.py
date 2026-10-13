from datetime import date

import pytest

from semester import LOWER, UPPER, monday, semester_for, week_type_on


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    for k in ["AUTUMN_START", "AUTUMN_END", "SPRING_START", "SPRING_END"]:
        monkeypatch.delenv(k, raising=False)


def test_autumn_starts_upper_and_alternates():
    assert week_type_on(date(2026, 9, 1)) == UPPER       # вторник: неделя начала — верхняя
    assert week_type_on(date(2026, 8, 31)) is None        # понедельник до начала семестра
    assert week_type_on(date(2026, 9, 7)) == LOWER
    assert week_type_on(date(2026, 9, 14)) == UPPER
    assert week_type_on(date(2026, 10, 13)) == UPPER      # 7-я неделя (6 недель от 31.08)
    assert week_type_on(date(2026, 12, 31)) is not None


def test_spring_needs_manual_start(monkeypatch):
    assert semester_for(date(2027, 2, 15)) is None
    monkeypatch.setenv("SPRING_START", "2027-02-09")
    assert semester_for(date(2027, 2, 15)) == (date(2027, 2, 9), date(2027, 6, 30))
    assert week_type_on(date(2027, 2, 9)) == UPPER
    assert week_type_on(date(2027, 2, 15)) == LOWER
    assert week_type_on(date(2028, 2, 15)) is None        # дата с годом — только на тот год


def test_monday():
    assert monday(date(2026, 10, 18)) == date(2026, 10, 12)
