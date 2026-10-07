"""Прогон всех реальных строк subject: clean не падает, покрытие не деградирует.

Пороги = замер на корпусе 2026-10-07 минус 1 п.п. Если правка clean.py
роняет долю ниже порога — это регрессия.
"""
from pathlib import Path

import pytest

from etl.clean import UNKNOWN, clean

CORPUS = (Path(__file__).parent / "fixtures" / "subjects_corpus.txt").read_text().splitlines()

THRESHOLDS = {"тип": 96.1, "дисциплина": 97.4, "преподаватель": 96.7, "аудитория": 94.6}


@pytest.fixture(scope="module")
def lessons():
    return [lesson for raw in CORPUS for lesson in clean(raw).lessons]


def test_corpus_size():
    assert len(CORPUS) == 4005


@pytest.mark.parametrize("field,check", [
    ("тип", lambda l: l.lesson_type != UNKNOWN),
    ("дисциплина", lambda l: bool(l.discipline)),
    ("преподаватель", lambda l: bool(l.teachers)),
    ("аудитория", lambda l: bool(l.rooms)),
])
def test_coverage_not_below_threshold(lessons, field, check):
    share = 100 * sum(check(l) for l in lessons) / len(lessons)
    assert share >= THRESHOLDS[field], f"{field}: {share:.2f}% < {THRESHOLDS[field]}%"
