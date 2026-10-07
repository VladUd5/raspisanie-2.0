from pathlib import Path

import pytest

from etl.dictionary import COLUMNS, Dictionary, DictionaryError, load_dictionary


def _dir(tmp_path: Path, **files: str) -> Path:
    """Словарь во временной папке: только заголовки плюс переданные строки (не копия настоящего)."""
    for name, header in COLUMNS.items():
        (tmp_path / f"{name}.csv").write_text(",".join(header) + "\n" + files.get(name, ""), encoding="utf-8")
    return tmp_path


def test_reads_all_kinds(tmp_path):
    d = load_dictionary(_dir(
        tmp_path,
        disciplines="Иностанный язык,Иностранный язык,h,,опечатка\nКомплексный анализ ХД,—,h,,обрывок\n",
        teachers="Калашникова,Маркетинг,Калашникова А.Р.,h,,\nКалашникова,,Калашникова С.П.,l,,\n",
        places="УК2,5111,УК2,511,l,опечатка,\n",
        groups="ВТ -404,ВТ-404,h,,\n",
        lesson_types="лекю,лекция,h,опечатка,\n",
    ))
    assert d.disciplines["Иностанный язык"].canonical == "Иностранный язык"
    assert d.disciplines["Иностанный язык"].source == "словарь"
    assert d.teacher("Калашникова", "Маркетинг").canonical == "Калашникова А.Р."
    assert d.teacher("Калашникова", "Менеджмент").canonical == "Калашникова С.П."
    assert d.teacher("Калашникова", None).source == "словарь?"
    assert d.teacher("Нет такого", None) is None
    assert d.rooms[("УК2", "5111")].canonical == "УК2|511"
    assert d.groups["ВТ -404"].canonical == "ВТ-404"
    assert d.lesson_types["лекю"].kind == "опечатка"
    assert "иностранный" in d.known_words() and "язык" in d.known_words()


def test_bom_and_blank_lines_are_fine(tmp_path):
    base = _dir(tmp_path)
    text = (base / "groups.csv").read_text(encoding="utf-8")
    (base / "groups.csv").write_text("﻿" + text + "\nВТ -404,ВТ-404,h,,\n\n", encoding="utf-8")
    assert load_dictionary(base).groups["ВТ -404"].canonical == "ВТ-404"


@pytest.mark.parametrize("name, rows, message", [
    ("disciplines", "Физика,Физика,x,,\n", "уверенность"),
    ("disciplines", "Физика,Физика,h,,\nФизика,Физика,h,,\n", "дубль"),
    ("disciplines", "Физика,,h,,\n", "канон"),
    ("teachers", "Иванов,,иванов и.и.,h,,\n", "канон"),
    ("lesson_types", "лекю,лекцыя,h,,\n", "тип"),
])
def test_invalid_rows_name_file_and_line(tmp_path, name, rows, message):
    with pytest.raises(DictionaryError, match=rf"{name}\.csv.*{message}"):
        load_dictionary(_dir(tmp_path, **{name: rows}))


def test_semicolon_separated_file_is_rejected_with_file_name(tmp_path):
    base = _dir(tmp_path)
    (base / "groups.csv").write_text("написание;канон;уверенность;вид;примечание\n", encoding="utf-8")
    with pytest.raises(DictionaryError, match=r"groups\.csv.*столбц"):
        load_dictionary(base)


def test_empty_dictionary():
    d = Dictionary.empty()
    assert d.disciplines == {} and d.teacher("Иванов", None) is None and d.known_words() == set()


def test_real_dictionary_is_consistent():
    d = load_dictionary()
    assert len(d.disciplines) > 2000 and len(d.teachers) > 600
    canons = {e.canonical for e in d.disciplines.values()}
    for spelling, by_discipline in d.teachers.items():
        for discipline in by_discipline:
            assert discipline == "" or discipline in canons, (spelling, discipline)


def test_unquoted_comma_gives_file_and_line(tmp_path):
    # примечание с запятой без кавычек → лишнее поле
    base = _dir(tmp_path, groups="\nВТ -404,ВТ-404,h,,пробел, лишний\n")
    with pytest.raises(DictionaryError, match=r"groups\.csv, строка 3: лишние поля"):
        load_dictionary(base)


def test_cp1251_file_gives_file_name(tmp_path):
    base = _dir(tmp_path)
    (base / "groups.csv").write_bytes(",".join(COLUMNS["groups"]).encode("cp1251") + b"\n")
    with pytest.raises(DictionaryError, match=r"groups\.csv.*UTF-8"):
        load_dictionary(base)
