from etl.canon import SOURCE_ASIS, SOURCE_PARSE, SOURCE_RULE, Canonizer
from etl.clean import ParsedLesson
from etl.dictionary import Dictionary, Entry


def _lessons():
    return [
        ParsedLesson("практика", "Иностанный язык", ["Балашова"], ["314"], rooms_raw=["314"], type_raw="пр.з."),
        ParsedLesson("лекция", "Иностранный язык", ["Балашова Е.В."], ["314"], rooms_raw=["314"], type_raw="лек."),
        ParsedLesson("практика", "Комплексный анализ ХД", ["Шарикова И.В."], [], type_raw="пр.з."),
        ParsedLesson("лекция", "Маркетинг", ["Калашникова"], ["5111"], rooms_raw=["5111"], type_raw="лекю"),
    ]


def _dictionary():
    return Dictionary(
        disciplines={"Иностранный язык": Entry("Иностранный язык", "h"),
                     "Комплексный анализ ХД": Entry("—", "h", note="обрывок")},
        teachers={"Калашникова": {"Маркетинг": Entry("Калашникова А.Р.", "h"), "": Entry("Калашникова С.П.", "l")}},
        rooms={("УК2", "5111"): Entry("УК2|511", "l", kind="опечатка")},
        groups={"ВТ -404": Entry("ВТ-404", "h")},
        lesson_types={"лекю": Entry("лекция", "h", kind="опечатка")},
    )


def test_dictionary_first_then_rules_then_as_is():
    c = Canonizer(_dictionary(), _lessons())
    assert c.discipline("Иностранный язык").source == "словарь"
    r = c.discipline("Иностанный язык")
    assert (r.canonical, r.source) == ("Иностранный язык", SOURCE_RULE)
    assert c.discipline("Комплексный анализ ХД").canonical is None
    assert c.discipline("Маркетинг").source == SOURCE_ASIS


def test_teacher_by_discipline_context_and_rules():
    c = Canonizer(_dictionary(), _lessons())
    assert c.teacher("Калашникова", "Маркетинг").canonical == "Калашникова А.Р."
    assert c.teacher("Калашникова", "Менеджмент").source == "словарь?"
    r = c.teacher("Балашова", "Иностранный язык")
    assert (r.canonical, r.source) == ("Балашова Е.В.", SOURCE_RULE)


def test_rooms_groups_types():
    c = Canonizer(_dictionary(), _lessons())
    assert c.room("УК2", "5111", "5111")[:2] == ("УК2", "511")
    b, r, res = c.room("УК1", "314", "314")
    assert (b, r, res.source, res.canonical) == ("УК1", "314", SOURCE_PARSE, "УК1|314")
    assert c.group("ВТ -404").source == "словарь"
    assert (c.group("Б-ВБ 301").canonical, c.group("Б-ВБ 301").source) == ("Б-ВБ-301", SOURCE_RULE)
    assert c.group("Б-Э-101").source == SOURCE_ASIS
    assert c.lesson_type("лекю", "не определён").canonical == "лекция"
    assert c.lesson_type("лек.", "лекция").source == SOURCE_PARSE


def test_audit_reports_both_kinds():
    audit = Canonizer(_dictionary(), _lessons()).audit()
    assert set(audit) == {"discipline", "teacher"}
