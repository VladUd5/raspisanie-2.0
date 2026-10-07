import pytest

from etl.normalize import cluster_disciplines, disc_key, is_surname_only, normalize_group, resolve_teachers


def test_disc_key_ignores_case_yo_spaces_and_edge_punctuation():
    assert disc_key("  ЗООГИГИЕНА. ") == disc_key("зоогигиена")
    assert disc_key("Учёт  и аудит") == "учет и аудит"


def test_typos_are_merged_into_most_frequent_normal_variant():
    names = ["Физическая культура и спорт"] * 3 + ["Физическая культура и сорт", "ФИЗИЧЕСКАЯ КУЛЬТУРА И СПОРТ"]
    mapping, merges = cluster_disciplines(names)
    assert set(mapping.values()) == {"Физическая культура и спорт"}
    assert [m.alias for m in merges] == ["Физическая культура и сорт"]


def test_typo_inostanny():
    mapping, _ = cluster_disciplines(["Иностранный язык", "Иностранный язык", "Иностанный язык"])
    assert mapping["Иностанный язык"] == "Иностранный язык"


def test_letter_spacing_glued_words_are_merged():
    mapping, _ = cluster_disciplines(["Безопасность жизнедеятельности", "БЕЗОПАСНОСТЬЖИЗНЕДЕЯТЕЛЬНОСТИ"])
    assert mapping["БЕЗОПАСНОСТЬЖИЗНЕДЕЯТЕЛЬНОСТИ"] == "Безопасность жизнедеятельности"


def test_different_disciplines_are_not_merged():
    names = ["Органическая химия", "Неорганическая химия", "Иностранный язык 1", "Иностранный язык 2",
             "Физика", "Физиология"]
    mapping, merges = cluster_disciplines(names)
    assert len(set(mapping.values())) == 6
    assert merges == []


def test_caps_only_cluster_gets_sentence_case_keeping_abbreviations():
    mapping, _ = cluster_disciplines(["ИННОВАЦИОННЫЙ МЕНЕДЖМЕНТ АПК"])
    assert mapping["ИННОВАЦИОННЫЙ МЕНЕДЖМЕНТ АПК"] == "Инновационный менеджмент АПК"


def test_surname_joins_single_full_name():
    mapping, _ = resolve_teachers(["Потоцкая Л.Н.", "Потоцкая", "Потоцкая"])
    assert mapping["Потоцкая"] == "Потоцкая Л.Н."


def test_surname_stays_when_ambiguous():
    mapping, _ = resolve_teachers(["Кузьмин А.М.", "Кузьмин А.Н.", "Кузьмин"])
    assert mapping["Кузьмин"] == "Кузьмин"
    assert is_surname_only(mapping["Кузьмин"])


def test_full_name_typo_merged_with_same_initials():
    mapping, merges = resolve_teachers(["Скосырева Е.Н."] * 3 + ["Скрсырева Е.Н."])
    assert mapping["Скрсырева Е.Н."] == "Скосырева Е.Н."
    assert merges[0].kind == "teacher"


def test_gender_pair_not_merged():
    mapping, _ = resolve_teachers(["Иванов А.А.", "Иванова А.А.", "Иванова"])
    assert mapping["Иванов А.А."] == "Иванов А.А."
    assert mapping["Иванова"] == "Иванова А.А."


def test_surname_with_typo_joins_unique_similar_full_name():
    mapping, merges = resolve_teachers(["Раздобарова М.Н.", "Раздобарава"])
    assert mapping["Раздобарава"] == "Раздобарова М.Н."


def test_short_surnames_are_not_fuzzy_merged():
    mapping, _ = resolve_teachers(["Ким А.А.", "Кин А.А."])
    assert mapping["Кин А.А."] == "Кин А.А."


def test_word_level_guard_blocks_different_first_words():
    names = ["Пищевая биотехнология", "Общая биотехнология",
             "Русский язык в деловой и научной коммуникации", "Иностранный язык в деловой и научной коммуникации",
             "Основы научных исследований", "Методы научных исследований"]
    mapping, merges = cluster_disciplines(names)
    assert merges == []


def test_abbreviations_are_merged():
    mapping, _ = cluster_disciplines(["Цифровые технологии в защите растений", "ЦИФР. ТЕХНОЛ. В ЗАЩИТЕ РАСТЕНИЙ",
                                      "Организация работы в малых группах", "ОРГАНИЗАЦИЯ РАБОТЫ МАЛЫХ ГРУПП"])
    assert mapping["ЦИФР. ТЕХНОЛ. В ЗАЩИТЕ РАСТЕНИЙ"] == "Цифровые технологии в защите растений"
    assert mapping["ОРГАНИЗАЦИЯ РАБОТЫ МАЛЫХ ГРУПП"] == "Организация работы в малых группах"


def test_canonical_starts_with_capital():
    mapping, _ = cluster_disciplines(["основы реконструкции ландшафтных объектов"])
    assert mapping["основы реконструкции ландшафтных объектов"] == "Основы реконструкции ландшафтных объектов"


def test_surname_first_letter_must_match():
    mapping, _ = resolve_teachers(["Азизов И.Р.", "Газизов"])
    assert mapping["Газизов"] == "Газизов"


def test_inserted_letters_are_not_a_typo():
    mapping, merges = cluster_disciplines(["Экономика", "Экономика", "Эконометрика"])
    assert mapping["Эконометрика"] == "Эконометрика"
    assert merges == []


def test_similar_single_word_sciences_are_not_merged():
    names = ["Экология", "Экология", "Геология", "Зоология", "Биология", "Микология",
             "Правоведение", "Почвоведение"]
    mapping, merges = cluster_disciplines(names)
    assert merges == []


def test_glued_abbreviation_is_merged():
    mapping, _ = cluster_disciplines(["Общая физическая подготовка"] * 2 + ["Общая физ.подготовка"])
    assert mapping["Общая физ.подготовка"] == "Общая физическая подготовка"


def test_canonical_prefers_full_form_over_abbreviation():
    mapping, _ = cluster_disciplines(["Внутрен.незараз. болезни"] * 3 + ["ВНУТРЕННИЕ НЕЗАРАЗНЫЕ БОЛЕЗНИ"])
    assert mapping["Внутрен.незараз. болезни"] == "Внутренние незаразные болезни"


def test_tie_prefers_longer_variant():
    mapping, _ = cluster_disciplines(["Иностанный язык", "Иностранный язык"])
    assert set(mapping.values()) == {"Иностранный язык"}


def test_canonical_variant_is_not_logged_as_its_own_merge():
    # канон кластера («полная форма») не является представителем кластера — но и «склейкой» сам с собой не считается
    mapping, merges = cluster_disciplines(["ОБЩАЯ ФИЗ.ПОДГОТОВКА"] * 5 + ["Общая физическая подготовка"])
    assert all(m.alias != m.canonical for m in merges)


def test_unverified_spelling_joins_dictionary_cluster_and_takes_its_canon():
    mapping, merges = cluster_disciplines(["Иностанный язык"], anchors={"Иностранный язык": "Иностранный язык"})
    assert mapping == {"Иностанный язык": "Иностранный язык"}
    assert merges[0].alias == "Иностанный язык"


def test_dictionary_canon_wins_over_frequency():
    mapping, _ = cluster_disciplines(["ФИЗИКА"] * 5, anchors={"Физика": "Физика"})
    assert mapping["ФИЗИКА"] == "Физика"


def test_rules_do_not_pull_unrelated_names_into_dictionary_cluster():
    mapping, _ = cluster_disciplines(["Физиология"], anchors={"Физика": "Физика"})
    assert mapping["Физиология"] == "Физиология"


def test_truncated_name_joins_full_one_with_shared_teacher():
    short = "РАЗРАБОТКА НОРМАТИВНОЙ И ТЕХНИЧЕСКОЙ ДОКУМЕНТАЦИИ ПРИ ПРОИЗВОДСТВЕ"
    full = ("Разработка нормативной и технической документации при производстве "
            "хлебобулочных, кондитерских и макаронных изделий")
    teachers = {short: {"Колотова Н.А."}, full: {"Колотова Н.А."}}
    mapping, _ = cluster_disciplines([short, full], teachers_of=teachers)
    assert mapping[short] == mapping[full] == full
    mapping, _ = cluster_disciplines([short, full], teachers_of={short: {"Иванов И.И."}, full: {"Колотова Н.А."}})
    assert mapping[short] != mapping[full]


def test_two_dictionary_words_are_not_typos_of_each_other():
    known = {"микроэкономика", "макроэкономика"}
    mapping, _ = cluster_disciplines(["Микроэкономика", "Макроэкономика"], known_words=known)
    assert len(set(mapping.values())) == 2


def test_short_capital_tokens_must_match():
    mapping, _ = cluster_disciplines(["Ландшафтное проектирование в ЛА", "Ландшафтное проектирование в ЛД"])
    assert len(set(mapping.values())) == 2


def test_sentence_case_lowercases_prepositions_and_keeps_abbreviations():
    mapping, _ = cluster_disciplines(["БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ И ОХРАНА ТРУДА"])
    assert mapping["БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ И ОХРАНА ТРУДА"] == "Безопасность жизнедеятельности и охрана труда"
    mapping, _ = cluster_disciplines(["УПРАВЛЕНИЕ НЕСООТВЕТСТВИЯМИ В ПТС"])
    assert mapping["УПРАВЛЕНИЕ НЕСООТВЕТСТВИЯМИ В ПТС"] == "Управление несоответствиями в ПТС"


@pytest.mark.parametrize("raw, expected", [
    ("ВТ -404", "ВТ-404"), ("Б-ВБ 301", "Б-ВБ-301"), ("Б-УК- 301", "Б-УК-301"),
    ("М-ППР-ТМП- 201", "М-ППР-ТМП-201"), ("Б-Э-101", "Б-Э-101"), ("-101", "-101"), ("", ""),
])
def test_normalize_group(raw, expected):
    assert normalize_group(raw) == expected
