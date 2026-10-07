import json
from pathlib import Path

import pytest

from etl.clean import ParsedLesson, clean
from etl.normalize import disc_key

CASES = json.loads((Path(__file__).parent / "fixtures" / "subject_cases.json").read_text())["cases"]


def _as_dict(lesson: ParsedLesson) -> dict:
    return {
        "lesson_type": lesson.lesson_type,
        "discipline": disc_key(lesson.discipline) if lesson.discipline else None,
        "teachers": lesson.teachers,
        "rooms": lesson.rooms,
        "building": lesson.building,
        "subgroup": lesson.subgroup,
    }


def _expected(lesson: dict) -> dict:
    return {**lesson, "discipline": disc_key(lesson["discipline"]) if lesson["discipline"] else None}


@pytest.mark.parametrize("case", [c for c in CASES if c["mode"] == "strict"], ids=lambda c: c["id"])
def test_strict_cases(case):
    cell = clean(case["raw"])
    assert cell.is_service == case["expected"]["service"]
    assert [_as_dict(l) for l in cell.lessons] == [_expected(l) for l in case["expected"]["lessons"]]


@pytest.mark.parametrize("case", [c for c in CASES if c["mode"] == "flags"], ids=lambda c: c["id"])
def test_flag_cases(case):
    cell = clean(case["raw"])
    assert cell.needs_review == case["expected_flags"]["needs_review"]


@pytest.mark.parametrize("raw", ["", "   ", "\n"])
def test_empty_is_service(raw):
    assert clean(raw).is_service is True
    assert clean(raw).lessons == []


def test_never_raises_on_garbage():
    for raw in ["лек.", "пр.з. 324", "(((", "ауд.", "Иванов И.", "УК №", "\x03\x01\x02"]:
        clean(raw)
