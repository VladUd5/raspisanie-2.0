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


@pytest.mark.parametrize("raw", ["доц. Тарбаев В.А. ауд. 324", "асс. Козлов С.Е. лаб.терап.", "ст.пр. Суркова Т.Н. 105"])
def test_title_at_start_is_not_truncated(raw):
    # звание в начале — обычная ячейка без дисциплины, а не оборванная
    assert clean(raw).truncated is False


def test_lowercase_fragment_is_truncated():
    assert clean("отоки производ. на предпр-ях общ.пит. 1п/г С-219 Фоменко").truncated is True


@pytest.mark.parametrize("raw, rooms, rooms_raw", [
    ("лек. КОРПОРАТИВНЫЙ МЕНЕДЖМЕНТ В АГРОБИЗНЕСЕ доц. Власова О.В. 431 а УК 2", ["431а"], ["431 а"]),
    ("Лек. КЛИНИЧЕСКАЯ ДИАГНОСТИКА доцент Анникова Л.В. ауд.№ 7", ["7"], ["7"]),
    ("пр.з. Правоведение С-305а доц.Рубанова М.Е.", ["С-305а"], ["С-305а"]),
    ("пр.з. Иностранный язык лаб.з. Ин-яз ст.пр. Гришкова В.А., ст.пр. Бобылева Г.А.",
     ["Лаб. иностранных языков"], ["лаб.з. Ин-яз"]),
])
def test_rooms_raw_keeps_written_form(raw, rooms, rooms_raw):
    lesson = clean(raw).lessons[0]
    assert lesson.rooms == rooms
    assert lesson.rooms_raw == rooms_raw


def test_c_prefix_does_not_take_assistant_title_as_letter():
    # «С-208 асс.» — «а» здесь начало «асс.», а не литера аудитории
    assert clean("пр.з. Философия С-208 асс.Буняев М.Б.").lessons[0].rooms == ["С-208"]


@pytest.mark.parametrize("raw, types_raw", [
    ("лекю УПРАВЛЕНИЕ КАЧЕСТВОМ В ПТС доц.Тяпаев Т.Б. 341", ["лекю"]),
    ("лек. ОБЩАЯ СЕЛЕКЦИЯ доц. Степанова Н.В. 903 пр.з. з. Философия познания Крайнов А.Л. 801", ["лек.", "пр.з. з."]),
    ("ОБЩАЯ ФИЗИЧЕСКАЯ ПОДГОТОВКА физ. зал Пяткина", [None]),
])
def test_type_raw_is_marker_as_written(raw, types_raw):
    assert [l.type_raw for l in clean(raw).lessons] == types_raw


def test_cut_marker_r_z_at_start_is_practice():
    assert clean("р.з.Иностранный язык лаб.ин-язИванова Л.М,Романова О.").lessons[0].lesson_type == "практика"


def test_ek_inside_text_is_not_a_marker():
    # «ек.» распознаётся только в начале ячейки
    assert [l.lesson_type for l in clean("лек. Биотехнология в АПК ек. 324").lessons] == ["лекция"]
