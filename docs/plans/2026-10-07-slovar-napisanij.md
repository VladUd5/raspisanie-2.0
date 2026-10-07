# Проверенный словарь написаний — план реализации

> **Для исполнителя:** выполнять по задачам через superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans. Шаги — чекбоксы `- [ ]`.

**Цель:** канон дисциплин, преподавателей, аудиторий, групп и типов занятий берётся из проверенного вручную словаря; автоправила работают только для новых написаний и помечают их «не проверено»; разбор ячейки исправлен по найденным классам ошибок; страница «Словарь написаний» показывает каждое слово со всеми его написаниями и подсвеченной разницей.

**Архитектура:** `clean.py` дополнительно отдаёт исходный текст аудиторий и маркера типа. Новый `etl/dictionary.py` читает CSV словаря, `etl/canon.py` (класс `Canonizer`) решает канон каждого написания: словарь → автоправила `normalize.py` → как есть. `etl/variants.py` классифицирует вид ошибки и строит посимвольную разницу. `load.py` пишет таблицы `spellings` и `rule_audit` вместо `merges`, флаг `unverified_name`. Страница `views/spellings.py` читает `spellings`.

**Стек:** Python 3.10, Streamlit 1.65, pandas, rapidfuzz, SQLite, pytest. Новых зависимостей нет (`difflib`, `csv`, `html` — стандартная библиотека).

**Спека:** `docs/specs/2026-10-07-slovar-napisanij-design.md`; основа — `docs/specs/2026-10-07-raspisanie-2-0-design.md`.

## Глобальные ограничения

- Парсер (`vendor/…`, git submodule) не модифицируется.
- Python 3.10 (образ `python:3.10-slim`): без синтаксиса 3.11+.
- Новых зависимостей в `stand/requirements.txt` не добавлять.
- Тесты запускаются из корня: `.venv/bin/python -m pytest …` (`pytest.ini`: `pythonpath = stand`).
- Словарь — UTF-8 CSV с заголовком в `stand/etl/dictionary/`, строки отсортированы по ключу.
- Источники канона ровно такие: `словарь`, `словарь?`, `правило`, `как есть`, `разбор`.
- Канон «не дисциплина» — строка `—` (U+2014).
- В коммитах, PR и файлах проекта — никаких упоминаний ИИ и строк `Co-Authored-By`; git email не менять.
- Тексты интерфейса и комментарии — на русском, как в остальном коде.
- Ни одна существующая фикстура `tests/fixtures/subject_cases.json` не правится молча: если ожидание меняется, в шаге сказано какое и почему.

## Что проверить на ревью (не покрыто прямыми требованиями спеки)

1. Словарь, отредактированный вручную в Excel/LibreOffice: BOM в начале, пустые строки, разделитель `;` — BOM и пустые строки читаются, `;` даёт понятную ошибку с именем файла; стенд показывает предупреждение, а не падает. → тесты в задаче 6.
2. БД от предыдущей версии стенда (таблица `merges`, нет `unverified_name`) — стенд пересоздаёт схему и перечитывает снапшоты. → тест в задаче 10.
3. Написание с `<`, `&`, `"` — в карточке экранируется, разметка не ломается. → тест в задаче 12.
4. Фильтры, после которых не осталось ни одной карточки, — сообщение вместо исключения. → тест в задаче 12.
5. Строка `teachers.csv` с дисциплиной, которой нет среди канонов `disciplines.csv`, — никогда не сработает; ловится тестом настоящего словаря. → тест в задаче 11.

---

### Задача 1: Разбор — аудитории и их исходный текст

**Файлы:**
- Изменить: `stand/etl/clean.py` (`ParsedLesson`, `_BUILDING_UK`, `_ROOMS`, `_extract_places`, `_parse_lesson`)
- Изменить: `stand/etl/locations.py` (`LOCATIONS`)
- Изменить: `tests/fixtures/subject_cases.json` (новые случаи)
- Тест: `tests/test_clean.py`

**Интерфейсы:**
- Производит: `ParsedLesson.rooms_raw: list[str]` — для каждой аудитории из `rooms` (тот же порядок, та же длина) текст, как он записан в ячейке, без префикса `ауд.`/`уд.`/`№` и без обрамляющих `().,`. Для мест из справочника — совпавший текст (`физ. зал`, `лаб.з. Ин-яз`).

- [ ] **Шаг 1: Добавить фикстуры (strict) в `tests/fixtures/subject_cases.json`, в конец массива `cases`**

```json
{"id": "room-letter-after-c-prefix", "category": "аудитория С- с буквой", "raw": "пр.з. Правоведение С-305а доц.Рубанова М.Е.", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "Правоведение", "teachers": ["Рубанова М.Е."], "rooms": ["С-305а"], "building": null, "subgroup": null}]}},
{"id": "lowercase-uk", "category": "корпус строчными", "raw": "лаб.з. почвоведение Губов В.И. ук 1 610", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лабораторная", "discipline": "почвоведение", "teachers": ["Губов В.И."], "rooms": ["610"], "building": "УК1", "subgroup": null}]}},
{"id": "hydraulic-lab", "category": "аудитория ГЛ-N", "raw": "пр.з. гидравлика Миркина Е.Н. ГЛ-5", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "гидравлика", "teachers": ["Миркина Е.Н."], "rooms": ["ГЛ-5"], "building": null, "subgroup": null}]}},
{"id": "lhm-lab", "category": "аудитория ЛХМ", "raw": "лек. ПАТЕНТОВЕДЕНИЕ проф. Фокин С.В. ЛХМ", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ПАТЕНТОВЕДЕНИЕ", "teachers": ["Фокин С.В."], "rooms": ["ЛХМ"], "building": null, "subgroup": null}]}},
{"id": "aud-number-sign", "category": "ауд. № N", "raw": "Лек. КЛИНИЧЕСКАЯ ДИАГНОСТИКА доцент Анникова Л.В. ауд.№ 7", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "КЛИНИЧЕСКАЯ ДИАГНОСТИКА", "teachers": ["Анникова Л.В."], "rooms": ["7"], "building": null, "subgroup": null}]}},
{"id": "ud-typo", "category": "опечатка уд. вместо ауд.", "raw": "лек. БИОТЕХНИКА ВОСПРОИЗВОДСТВА С ОСНОВАМИ АКУШЕРСТВА профессор Семиволос А.М. уд.Малая", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "БИОТЕХНИКА ВОСПРОИЗВОДСТВА С ОСНОВАМИ АКУШЕРСТВА", "teachers": ["Семиволос А.М."], "rooms": ["Малая"], "building": null, "subgroup": null}]}},
{"id": "aud-patanatomy", "category": "ауд. с названием", "raw": "лек.ФИЗИЧЕСКАЯ КУЛЬТУРА И СПОРТ проф. Милехин А.В. ауд. Пат.анатомии", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ФИЗИЧЕСКАЯ КУЛЬТУРА И СПОРТ", "teachers": ["Милехин А.В."], "rooms": ["Ауд. патанатомии"], "building": null, "subgroup": null}]}},
{"id": "lab-inyaz-after-lesson", "category": "лаб.з. Ин-яз — аудитория", "raw": "пр.з. Иностранный язык лаб.з. Ин-яз ст.пр. Гришкова В.А., ст.пр. Бобылева Г.А.", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "Иностранный язык", "teachers": ["Гришкова В.А.", "Бобылева Г.А."], "rooms": ["Лаб. иностранных языков"], "building": null, "subgroup": null}]}},
{"id": "uk-comma-two-digit", "category": "двузначная аудитория после УК№N,", "raw": "лаб.з. Механизация и автоматизация животноводства УК№2, 40 асс.Березкин А.Сю", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лабораторная", "discipline": "Механизация и автоматизация животноводства", "teachers": ["Березкин А.С."], "rooms": ["40"], "building": "УК2", "subgroup": null}]}},
{"id": "room-with-dot", "category": "аудитория с точкой", "raw": "лек.ИНЖЕНЕРНОЕ ОБЕСПЕЧЕНИЕ БИОТЕХНОЛОГИЧЕСКИХ ПРОЦЕССОВ доц. Анисимов А.В. 352.31", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ИНЖЕНЕРНОЕ ОБЕСПЕЧЕНИЕ БИОТЕХНОЛОГИЧЕСКИХ ПРОЦЕССОВ", "teachers": ["Анисимов А.В."], "rooms": ["352.31"], "building": null, "subgroup": null}]}},
{"id": "empty-uk-sign", "category": "УК№ без номера", "raw": "лаб.з. Электротехника 1п/г УК№ ,416 Абрамова В.С.", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лабораторная", "discipline": "Электротехника", "teachers": ["Абрамова В.С."], "rooms": ["416"], "building": null, "subgroup": 1}]}}
```

- [ ] **Шаг 2: Тест исходного текста аудиторий в `tests/test_clean.py`**

```python
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
```

- [ ] **Шаг 3: Запустить — должны упасть**

Run: `.venv/bin/python -m pytest tests/test_clean.py -q`
Expected: FAIL на 11 новых strict-случаях и на `test_rooms_raw_keeps_written_form` (`AttributeError: 'ParsedLesson' object has no attribute 'rooms_raw'`); `test_c_prefix_does_not_take_assistant_title_as_letter` проходит уже сейчас (защита от регрессии).

- [ ] **Шаг 4: `stand/etl/locations.py` — новые места**

В список `LOCATIONS` после строки с `Агроцентр ФТИК` добавить:

```python
    _loc(r"(?<![А-ЯЁа-яё])ЛХМ(?![А-ЯЁа-яё])", "ЛХМ", None),
    _loc(r"(?<![А-ЯЁа-яё])ауд\.?\s*пат\.?\s*анатоми[яи]", "Ауд. патанатомии", None, re.I),
    # «лаб.з. Ин-яз» — аудитория, а не тип занятия: ловится раньше маркеров
    _loc(r"(?<![А-ЯЁа-яё])лаб\.\s*з\.\s*ин(?:-яз|\.\s*яз)\.?(?![А-ЯЁа-яё])", "Лаб. иностранных языков", None, re.I),
```

- [ ] **Шаг 5: `stand/etl/clean.py` — поля и шаблоны**

В `ParsedLesson` после `subgroup` добавить:

```python
    rooms_raw: list[str] = field(default_factory=list)   # как записано в ячейке, параллельно rooms
    type_raw: str | None = None                            # маркер типа как в ячейке («лек.», «лекю»)
```

Заменить `_BUILDING_UK` и `_ROOMS`, добавить `_EMPTY_UK` и `_ROOM_PREFIX`:

```python
_BUILDING_UK = re.compile(
    rf"\(?(?<![{_L}])(?i:УК)\s*№?\s*(?P<uk>\d)\)?"
    rf"(?:\s*,\s*(?P<room>\d{{2,4}})(?![\d.:]))?"           # «УК№2, 40» — аудитория сразу за корпусом
)
_EMPTY_UK = re.compile(rf"(?<![{_L}])(?i:УК)\s*№(?!\s*\d)")   # «УК№ ,416» — номер корпуса потерян
_ROOM_PREFIX = re.compile(r"^(?:ауд|уд)\s*\.?\s*№?\s*", re.I)
_ROOMS = re.compile(
    rf"{_PH}(?P<ph>\d+){_PH}"
    rf"|(?<![{_L}])(?:(?i:ауд)|уд)\s*\.?\s*(?P<named>Большая|Малая)"
    rf"|(?<![{_L}])(?i:ауд)\s*\.?\s*№?\s*(?P<aud>\d{{1,4}})(?:\s?(?P<audl>[аб])(?![{_L}]))?\.?"
    rf"|(?<![\w.\-])(?P<cl>[СCХX])\s?-\s?(?P<c>\d{{2,4}})(?:\s?(?P<cll>[аб])(?![{_L}]))?"
    rf"|(?<![\w\-])ГЛ\s?-\s?(?P<gl>\d{{1,2}})(?!\d)"
    rf"|(?<![\w:\-.])(?P<dot>\d{{3}}\.\d{{2}})(?![\d.:])"         # «352.31» — формат не ясен, берём как есть
    rf"|(?<![\w:\-])(?<!\d[.:])(?P<num>\d{{3,4}})(?!\d)(?:\s?(?P<numl>[аб])(?![{_L}]))?(?![.:]\d)"
    rf"|(?<![\w:\-(])(?<!\d[.:])(?P<num2>\d{{2}})(?=[\s.]*$)"      # «Демин Е.Е.33», «… В.В. 40» в конце
)
```

`_extract_places` — сохранять совпавший текст третьим элементом:

```python
def _extract_places(s: str) -> tuple[str, list[tuple[str, str | None, str]]]:
    places: list[tuple[str, str | None, str]] = []
    for loc in LOCATIONS:
        def repl(m: re.Match, loc=loc) -> str:
            places.append((m.expand(loc.room), loc.building, m.group(0)))
            return f" {_PH}{len(places) - 1}{_PH} "
        s = loc.pattern.sub(repl, s)
    return s, places
```

В `_parse_lesson` (тип аргумента `places` — `list[tuple[str, str | None, str]]`) заменить блок от `def building_uk` до `text = _ROOMS.sub(room, text)` и строку `lesson.rooms = _unique(rooms)`:

```python
    rooms: list[tuple[str, str]] = []          # (аудитория, как записано)

    def add_room(name: str, raw: str) -> None:
        written = _ROOM_PREFIX.sub("", raw.strip(" .,()")).strip(" .,()")
        rooms.append((name, written or name))

    def building_uk(m: re.Match) -> str:
        lesson.building = f"УК{m.group('uk')}"
        if m.group("room"):
            add_room(m.group("room"), m.group("room"))
        return f" {_ROOM} "

    def building_named(m: re.Match) -> str:
        lesson.building = m.group(1)
        return f" {_ROOM} "

    text = _BUILDING_UK.sub(building_uk, text)
    text = _EMPTY_UK.sub(" ", text)
    text = _BUILDING_NAMED.sub(building_named, text)

    def room(m: re.Match) -> str:
        raw = m.group(0)
        if m.group("ph") is not None:
            name, building, raw = places[int(m.group("ph"))]
            add_room(name, raw)
            if building:
                lesson.building = building
        elif m.group("named"):
            add_room(m.group("named"), raw)
        elif m.group("aud"):
            add_room(m.group("aud") + (m.group("audl") or ""), raw)
        elif m.group("c"):
            letter = {"C": "С", "X": "Х"}.get(m.group("cl"), m.group("cl"))   # латиница → кириллица
            add_room(f"{letter}-{m.group('c')}{m.group('cll') or ''}", raw)
        elif m.group("gl"):
            add_room(f"ГЛ-{m.group('gl')}", raw)
        elif m.group("dot"):
            add_room(m.group("dot"), raw)
        elif m.group("num2"):
            add_room(m.group("num2"), raw)
        else:
            add_room(m.group("num") + (m.group("numl") or ""), raw)
        return f" {_ROOM} "

    text = _ROOMS.sub(room, text)
```

и вместо `lesson.rooms = _unique(rooms)`:

```python
    written_of: dict[str, str] = {}
    for name, written in rooms:
        written_of.setdefault(name, written)
    lesson.rooms = list(written_of)
    lesson.rooms_raw = list(written_of.values())
```

- [ ] **Шаг 6: Запустить тесты разбора и корпус**

Run: `.venv/bin/python -m pytest tests/test_clean.py tests/test_clean_corpus.py -q`
Expected: PASS. Если упал старый strict-случай — разобрать: это регрессия нового шаблона, ожидание не править.

- [ ] **Шаг 7: Коммит**

```bash
git add stand/etl/clean.py stand/etl/locations.py tests/fixtures/subject_cases.json tests/test_clean.py
git commit -m "Разбор: литера у аудиторий С-, ук строчными, ГЛ-N, ЛХМ, ауд. №, исходный текст аудиторий"
```

---

### Задача 2: Разбор — границы занятий, тип и его исходный текст

**Файлы:**
- Изменить: `stand/etl/clean.py` (`_HOURS`, `_TITLES`, `_MARKERS`, `_MARKER`, `_split`, `_clean`, `_parse_lesson`)
- Изменить: `tests/fixtures/subject_cases.json`
- Тест: `tests/test_clean.py`

**Интерфейсы:**
- Потребляет: `ParsedLesson.type_raw` из задачи 1.
- Производит: `ParsedLesson.type_raw` заполнен совпавшим текстом маркера (`"лек."`, `"лекю"`, `"пр.з. з."`) или `None`, если маркера нет.

- [ ] **Шаг 1: Фикстуры (strict) в `subject_cases.json`**

```json
{"id": "st-pr-without-dot", "category": "ст пр. — должность", "raw": "пр.з. Природно-хозяйственная оценка территории. ст пр.Боброва Ю.И. 535", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "Природно-хозяйственная оценка территории", "teachers": ["Боброва Ю.И."], "rooms": ["535"], "building": null, "subgroup": null}]}},
{"id": "pr-before-full-name", "category": "пр. перед ФИО — должность", "raw": "лек. ТЕХНОЛОГИИ ПРОИЗВОДСТВА пр. Старцев А.С. 131", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ТЕХНОЛОГИИ ПРОИЗВОДСТВА", "teachers": ["Старцев А.С."], "rooms": ["131"], "building": null, "subgroup": null}]}},
{"id": "hours-zan", "category": "пометка (3 зан.)", "raw": "пр.з. Логистика Наянов (3 зан.) 316", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "Логистика", "teachers": ["Наянов"], "rooms": ["316"], "building": null, "subgroup": null}]}},
{"id": "hours-with-practice-teacher", "category": "пометка часов с преподавателем практик", "raw": "лек. ЭКОНОМИЧЕСКАЯ КУЛЬТУРА доц. Васильева О.А. 5 лек. + Нерозя 5 пр.з. 234", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ЭКОНОМИЧЕСКАЯ КУЛЬТУРА", "teachers": ["Васильева О.А."], "rooms": ["234"], "building": null, "subgroup": null}]}},
{"id": "shared-tail-after-enumeration", "category": "общие преподаватель и аудитория у перечисленных занятий", "raw": "лек. ПРОЕКТ. ДЕЯТЕЛЬНОСТЬ В МАРКЕТИНГЕ (3 зан.), лек. БИРЖЕВАЯ ТОРГОВЛЯ (3 зан.) доц. Ледяев Т.Б. 314", "mode": "strict",
 "expected": {"service": false, "lessons": [
   {"lesson_type": "лекция", "discipline": "ПРОЕКТ. ДЕЯТЕЛЬНОСТЬ В МАРКЕТИНГЕ", "teachers": ["Ледяев Т.Б."], "rooms": ["314"], "building": null, "subgroup": null},
   {"lesson_type": "лекция", "discipline": "БИРЖЕВАЯ ТОРГОВЛЯ", "teachers": ["Ледяев Т.Б."], "rooms": ["314"], "building": null, "subgroup": null}]}},
{"id": "marker-lektsiya", "category": "маркер «лекция»", "raw": "лекция ЗЕМЛЕУСТРОИТЕЛЬНОЕ ПРОЕКТИРОВАНИЕ проф. Тарасенко П.В. ауд. 1003", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ЗЕМЛЕУСТРОИТЕЛЬНОЕ ПРОЕКТИРОВАНИЕ", "teachers": ["Тарасенко П.В."], "rooms": ["1003"], "building": null, "subgroup": null}]}},
{"id": "marker-lekyu", "category": "маркер «лекю»", "raw": "лекю УПРАВЛЕНИЕ КАЧЕСТВОМ В ПТС доц.Тяпаев Т.Б. 341", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "УПРАВЛЕНИЕ КАЧЕСТВОМ В ПТС", "teachers": ["Тяпаев Т.Б."], "rooms": ["341"], "building": null, "subgroup": null}]}},
{"id": "marker-ek-at-start", "category": "оборванное «лек.» в начале", "raw": "ек. КОМПЛЕКСНЫЙ АНАЛИЗ ХОЗЯЙСТВЕННОЙ ДЕЯТЕЛЬНОСТИ доц. Шарикова И.В. 232", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "КОМПЛЕКСНЫЙ АНАЛИЗ ХОЗЯЙСТВЕННОЙ ДЕЯТЕЛЬНОСТИ", "teachers": ["Шарикова И.В."], "rooms": ["232"], "building": null, "subgroup": null}]}},
{"id": "marker-doubled-z", "category": "сдвоенный маркер «пр.з. з.»", "raw": "лек. ОБЩАЯ СЕЛЕКЦИЯ доц. Степанова Н.В. 903 пр.з. з. Философия познания Крайнов А.Л. 801", "mode": "strict",
 "expected": {"service": false, "lessons": [
   {"lesson_type": "лекция", "discipline": "ОБЩАЯ СЕЛЕКЦИЯ", "teachers": ["Степанова Н.В."], "rooms": ["903"], "building": null, "subgroup": null},
   {"lesson_type": "практика", "discipline": "Философия познания", "teachers": ["Крайнов А.Л."], "rooms": ["801"], "building": null, "subgroup": null}]}}
```

- [ ] **Шаг 2: Тесты `type_raw` и «р.з.» в `tests/test_clean.py`**

```python
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
```

- [ ] **Шаг 3: Запустить — должны упасть**

Run: `.venv/bin/python -m pytest tests/test_clean.py -q`
Expected: FAIL на новых случаях (`type_raw` везде `None`, фантомные занятия, тип «не определён»).

- [ ] **Шаг 4: `_HOURS` и `_TITLES`**

```python
_HOURS = re.compile(
    r"\d+\s*лек\.?\s*\+\s*(?:[А-ЯЁ][а-яё]+\s*)?\d+\s*пр(?:\.?\s*з)?\.?"   # 4 лек. + 5 пр.; 5 лек. + Нерозя 5 пр.з.
    r"|\(\s*\d*\s*(?:лек|пр|зан)(?:\.|\s*з|(?![а-яё]))[^)]*\)"  # (5 лек.), (пр.з.), (3 зан.) — но не «(продвинутый уровень)»
    r"|\(\s*\d+\s*\)"                              # (28)
    r"|(?<![А-ЯЁа-яё])с\s+\d{1,2}[.:]\d{2}",            # ЗАЧЕТ с 13.40
    re.I,
)
_UP, _LO = "А-ЯЁ", "а-яё"
# дальше идёт фамилия: «Иванов…» или капсом «ИВАНОВ И.»
_NAME_AHEAD = rf"(?=\s*(?:[{_UP}][{_LO}]|[{_UP}]{{2,}}\s+[{_UP}]\s*\.))"
_TITLES = re.compile(
    rf"(?<![{_L}])(?:"
    rf"(?i:ст)\.?\s*(?i:преп)\.?"
    rf"|(?i:ст)\.\s*(?i:пр)\.?"
    rf"|(?i:ст)\s+(?i:пр)\.{_NAME_AHEAD}"                 # «ст пр.Боброва»
    rf"|(?i:доцент)(?![{_L}])|(?i:доц)(?:\.|(?![{_L}]))"
    rf"|(?i:преп)\.|(?i:асс)\."
    rf"|(?i:профессор|проф)\.?{_NAME_AHEAD}"              # но не «в проф. образ.», «ПРОФ. ДЕЯТ.»
    rf"|(?i:пр)\.(?=\s*[{_UP}][{_LO}]+\s*[{_UP}]\s*\.\s*[{_UP}])"   # «пр. Старцев А.С.» — преподаватель
    rf")"
)
```

Флаг `re.I` у `_TITLES` убран намеренно: регистронезависимы только сами слова (`(?i:…)`), а проверка «дальше фамилия» различает заглавные и строчные.

- [ ] **Шаг 5: Маркеры: тройки (тип, шаблон, только в начале)**

```python
_MARKERS: list[tuple[str, str, bool]] = [
    ("практика", rf"(?i:пр)\s?\.?\s?(?i:з){_END}(?:\s?(?i:з)\.)?", False),   # и сдвоенное «пр.з. з.»
    ("лабораторная", rf"(?i:лаб)\s?\.?\s?(?i:з){_END}", False),
    ("лабораторная", rf"(?i:лб)\s?\.?\s?(?i:з){_END}", False),
    ("лекция", rf"(?i:лекци[яи]|лекю)(?![{_L}])", False),                  # «лекция», опечатка «лекю»
    ("лекция", rf"(?i:лек){_END}", False),
    ("практика", r"(?i:пр)\s?\.(?![а-яё])", False),          # но не «пр.ва»
    ("лабораторная", r"(?i:лаб)\s?\.(?![а-яё])", False),     # но не «Лаб.диагност.»
    ("семинар", rf"(?i:сем){_END}", True),                   # «сем. посевов» в середине — не семинар
    ("консультация", rf"(?i:конс){_END}", True),
    ("зачёт", rf"(?i:зач[её]т)(?![{_L}])", False),
    ("экзамен", rf"(?i:экзамен)(?![{_L}])", False),
    ("лекция", r"ек\.", True),                               # оборванное «лек.»
    ("практика", r"р\.\s?з\.", True),                        # оборванное «пр.з.»
]
_MARKER = re.compile(
    rf"(?<![{_L}A-Za-z0-9(.\-])(?:"
    + "|".join(f"(?P<m{i}>{rx})" for i, (_, rx, _) in enumerate(_MARKERS))
    + ")"
)
```

Удалить `_ONLY_AT_START`. `_marker_type` заменить на:

```python
def _marker(m: re.Match) -> tuple[str, bool]:
    """(тип занятия, маркер допустим только в начале ячейки)."""
    i = next(i for i in range(len(_MARKERS)) if m.group(f"m{i}") is not None)
    return _MARKERS[i][0], _MARKERS[i][2]
```

`_split` возвращает тройки (тип, маркер как в ячейке, текст):

```python
def _split(s: str) -> list[tuple[str, str | None, str]]:
    matches = [m for m in _MARKER.finditer(s) if not _marker(m)[1] or not s[: m.start()].strip()]
    if not matches:
        return [(UNKNOWN, None, s)]
    parts = [
        (_marker(m)[0], m.group(0), s[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(s)])
        for i, m in enumerate(matches)
    ]
    parts = [p for p in parts if re.search(rf"[{_L}\d{_PH}]", p[2])] or [(parts[-1][0], parts[-1][1], "")]
    prefix = s[: matches[0].start()]
    if re.search(rf"[{_L}]", prefix):
        if _FULL_NAME.search(prefix) or _ROOMS.search(prefix):
            parts.insert(0, (UNKNOWN, None, prefix))          # перед маркером целое занятие
        else:
            t, raw, text = parts[0]
            parts[0] = (t, raw, prefix + " " + text)          # «2-я подгруппа лаб. з. …»
    return parts
```

Строку `truncated = …` в `_clean` оставить как есть (`_MARKER.match` работает с новым шаблоном).

- [ ] **Шаг 6: `_clean` — тип, исходный маркер и общий хвост перечисления**

Заменить строку `lessons = [_parse_lesson(t, text, places) for t, text in _split(s)]`:

```python
    parts = _split(s)
    lessons = [_parse_lesson(t, raw, text, places) for t, raw, text in parts]
    # «лек. A (3 зан.), лек. B (3 зан.) доц. Ледяев Т.Б. 314»: преподаватель и аудитория
    # в хвосте относятся ко всем перечисленным через запятую занятиям
    for i in range(len(lessons) - 2, -1, -1):
        cur, nxt = lessons[i], lessons[i + 1]
        if (parts[i][2].rstrip().endswith(",") and not cur.teachers and not cur.rooms
                and cur.lesson_type == nxt.lesson_type):
            cur.teachers, cur.rooms, cur.rooms_raw = list(nxt.teachers), list(nxt.rooms), list(nxt.rooms_raw)
            cur.building = nxt.building
```

Сигнатура `_parse_lesson(lesson_type: str, type_raw: str | None, text: str, places: …)`, первая строка тела:

```python
    lesson = ParsedLesson(lesson_type=lesson_type, type_raw=type_raw)
```

- [ ] **Шаг 7: Запустить тесты разбора и корпус**

Run: `.venv/bin/python -m pytest tests/test_clean.py tests/test_clean_corpus.py -q`
Expected: PASS. `test_title_at_start_is_not_truncated` («ст.пр. Суркова Т.Н. 105», «асс. Козлов С.Е. лаб.терап.») должен остаться зелёным.

- [ ] **Шаг 8: Коммит**

```bash
git add stand/etl/clean.py tests/fixtures/subject_cases.json tests/test_clean.py
git commit -m "Разбор: «ст пр.»/«пр.» перед ФИО — должность, опечатки маркеров, пометки часов, общий хвост перечисления"
```

---

### Задача 3: Разбор — преподаватели

**Файлы:**
- Изменить: `stand/etl/clean.py` (`_FULL_NAME`, `full_name` в `_parse_lesson`, `_NOT_SURNAMES`)
- Изменить: `tests/fixtures/subject_cases.json`
- Тест: `tests/test_clean.py` (strict-случаи)

**Интерфейсы:** внешних изменений нет; `teachers` получает правильные ФИО.

- [ ] **Шаг 1: Фикстуры (strict)**

```json
{"id": "prof-inside-discipline", "category": "«проф.» внутри названия", "raw": "пр.з. Педагог. технологии в проф. образ. Таньчева И.В. 801", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "Педагог. технологии в проф. образ.", "teachers": ["Таньчева И.В."], "rooms": ["801"], "building": null, "subgroup": null}]}},
{"id": "prof-inside-discipline-surname", "category": "«проф.» внутри названия, фамилия без инициалов", "raw": "пр.з. Правовое регулирование проф. деятельности Рубанова 1008", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "Правовое регулирование проф. деятельности", "teachers": ["Рубанова"], "rooms": ["1008"], "building": null, "subgroup": null}]}},
{"id": "initials-with-comma", "category": "инициалы через запятую", "raw": "лек. БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ доцент Карпова О,В. 213", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ", "teachers": ["Карпова О.В."], "rooms": ["213"], "building": null, "subgroup": null}]}},
{"id": "caps-surname", "category": "фамилия капсом", "raw": "лек. ЭКОЛОГИЧЕСКАЯ ОЦЕНКА ЕСТЕСТВЕННЫХ И ИСКУССТВЕННЫХ ВОДОЁМОВ проф. ПОДДУБНАЯ И.В. ауд. 434", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лекция", "discipline": "ЭКОЛОГИЧЕСКАЯ ОЦЕНКА ЕСТЕСТВЕННЫХ И ИСКУССТВЕННЫХ ВОДОЁМОВ", "teachers": ["Поддубная И.В."], "rooms": ["434"], "building": null, "subgroup": null}]}},
{"id": "surname-glued-to-discipline", "category": "фамилия слиплась с названием", "raw": "пр.з. русский язык в деловой и научной коммуникацииВыходцева И.С. 407", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "практика", "discipline": "русский язык в деловой и научной коммуникации", "teachers": ["Выходцева И.С."], "rooms": ["407"], "building": null, "subgroup": null}]}},
{"id": "dot-after-surname", "category": "точка после фамилии", "raw": "лаб.з. Технохимический контроль в мясной отрасли Асеева. Е.Ю. ауд. 105", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лабораторная", "discipline": "Технохимический контроль в мясной отрасли", "teachers": ["Асеева Е.Ю."], "rooms": ["105"], "building": null, "subgroup": null}]}},
{"id": "povolzhye-not-surname", "category": "«Поволжье» — не фамилия", "raw": "лаб.з. Биогеохимические основы животноводства в Поволжье 343 проф.Забелина М.В.", "mode": "strict",
 "expected": {"service": false, "lessons": [{"lesson_type": "лабораторная", "discipline": "Биогеохимические основы животноводства в Поволжье", "teachers": ["Забелина М.В."], "rooms": ["343"], "building": null, "subgroup": null}]}}
```

- [ ] **Шаг 2: Запустить — должны упасть**

Run: `.venv/bin/python -m pytest tests/test_clean.py -q -k "prof or initials or caps or glued or dot-after or povolzhye"`
Expected: FAIL на 6 случаях; `prof-inside-discipline-surname` может упасть тоже (сейчас «проф.» вырезается).

- [ ] **Шаг 3: `_FULL_NAME`**

```python
_FULL_NAME = re.compile(
    rf"(?<![{_UP}])(?P<s>{_SURNAME})\.?\s*"                  # перед фамилией может стоять строчная: «…коммуникацииВыходцева»
    rf"(?:(?P<i1>[{_UP}])\s*[.,]+\s*(?P<i2>[{_UP}])\s*\.*"   # И.О. / И. О. / И.О / О,В.
    rf"|(?P<j1>[{_UP}])(?P<j2>[{_UP}])\s*\."                 # ИО.
    rf"|(?P<k1>[{_UP}])\s(?P<k2>[{_UP}])\.)"                 # И О.
    rf"|(?<![{_L}])(?P<cs>[{_UP}]{{3,}}(?:-[{_UP}]{{3,}})?)\s+(?P<c1>[{_UP}])\.\s*(?P<c2>[{_UP}])\."  # ПОДДУБНАЯ И.В.
)
```

Определение `_UP`, `_LO` из задачи 2 должно стоять выше `_FULL_NAME` (перенести его к `_L` в начало файла).

- [ ] **Шаг 4: `full_name` в `_parse_lesson`**

```python
    def full_name(m: re.Match) -> str:
        if m.group("cs"):
            surname = "-".join(p.capitalize() for p in m.group("cs").split("-"))
            i1, i2 = m.group("c1"), m.group("c2")
        else:
            surname = m.group("s")
            i1, i2 = next((m.group(a), m.group(b)) for a, b in (("i1", "i2"), ("j1", "j2"), ("k1", "k2")) if m.group(a))
        teachers.append((m.start(), f"{surname} {i1}.{i2}."))
        return _TEACHER + " " * (m.end() - m.start() - 1)   # длина сохраняется: позиции нужны ниже
```

- [ ] **Шаг 5: `_NOT_SURNAMES`**

```python
_NOT_SURNAMES = {"России", "Российской", "Земли", "Европы", "Азии", "Сибири", "Поволжья", "Поволжье", "Мира"}
```

- [ ] **Шаг 6: Все тесты разбора и корпус**

Run: `.venv/bin/python -m pytest tests/test_clean.py tests/test_clean_corpus.py -q`
Expected: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add stand/etl/clean.py tests/fixtures/subject_cases.json
git commit -m "Разбор: звания только перед фамилией, инициалы через запятую, фамилия капсом и слипшаяся"
```

---

### Задача 4: Вид ошибки и посимвольная разница (`etl/variants.py`)

**Файлы:**
- Создать: `stand/etl/variants.py`
- Тест: `tests/test_variants.py`

**Интерфейсы:**
- Производит:
  - `NOT_DISCIPLINE = "—"`
  - `classify(kind: str, spelling: str, canonical: str) -> list[str]` — `kind` ∈ `discipline|teacher|room|group|lesson_type`; для аудиторий передаются номера без корпуса.
  - `diff_spans(spelling: str, canonical: str) -> list[tuple[str, str]]` — пары (операция, текст), операция ∈ `равно|лишнее|замена|недостаёт`; склейка текстов всех операций, кроме `недостаёт`, равна `spelling`.

- [ ] **Шаг 1: Тесты**

```python
import pytest

from etl.variants import classify, diff_spans


@pytest.mark.parametrize("kind, spelling, canonical, expected", [
    ("discipline", "Физика", "Физика", []),
    ("discipline", "БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ", "Безопасность жизнедеятельности", ["регистр"]),
    ("discipline", "Иностанный язык", "Иностранный язык", ["опечатка"]),
    ("discipline", "Безопасность жизнедеят.", "Безопасность жизнедеятельности", ["сокращение"]),
    ("discipline", "БЖД", "Безопасность жизнедеятельности", ["аббревиатура"]),
    ("discipline", "Учёт и аудит", "Учет и аудит", ["ё/е"]),
    ("discipline", "БЕЗОПАСНОСТЬЖИЗНЕДЕЯТЕЛЬНОСТИ", "Безопасность жизнедеятельности", ["регистр", "пробел"]),
    ("discipline", "РАЗРАБОТКА НОРМАТИВНОЙ И ТЕХНИЧЕСКОЙ ДОКУМЕНТАЦИИ ПРИ ПРОИЗВОДСТВЕ",
     "Разработка нормативной и технической документации при производстве хлебобулочных, кондитерских и макаронных изделий",
     ["регистр", "обрезано"]),
    ("discipline", "Технические основы проектирования оборудования ПиПП 352.31",
     "Технические основы проектирования оборудования ПиПП", ["лишняя пометка"]),
    ("discipline", "Комплексный анализ ХД", "—", ["не дисциплина"]),
    ("teacher", "Тороппова В.В.", "Торопова В.В.", ["опечатка"]),
    ("teacher", "Торопова В.Ю.", "Торопова В.В.", ["инициалы"]),
    ("teacher", "Торопова", "Торопова В.В.", ["нет инициалов"]),
    ("teacher", "Березкина А.С.", "Березкин А.С.", ["родовое окончание"]),
    ("teacher", "Берёзкин А.С.", "Березкин А.С.", ["ё/е"]),
    ("room", "С-305 а", "С-305а", ["пробел"]),
    ("room", "5111", "511", ["опечатка"]),
    ("room", "C-142", "С-142", ["латиница"]),
    ("group", "ВТ -404", "ВТ-404", ["пробел"]),
    ("lesson_type", "лек.", "лекция", ["сокращение"]),
    ("lesson_type", "ек.", "лекция", ["обрезано"]),
])
def test_classify(kind, spelling, canonical, expected):
    assert classify(kind, spelling, canonical) == expected


@pytest.mark.parametrize("spelling, canonical", [
    ("Тороппова В.В.", "Торопова В.В."), ("С-305 а", "С-305а"), ("Иностанный язык", "Иностранный язык"),
    ("БЕЗОПАСНОСТЬ ЖИЗНЕДЕЯТЕЛЬНОСТИ", "Безопасность жизнедеятельности"), ("", "Физика"), ("Физика", ""),
])
def test_diff_spans_rebuild_spelling(spelling, canonical):
    spans = diff_spans(spelling, canonical)
    assert "".join(t for op, t in spans if op != "недостаёт") == spelling


def test_diff_spans_marks_extra_letter_and_ignores_case():
    assert diff_spans("Тороппова", "Торопова") == [("равно", "Тороп"), ("лишнее", "п"), ("равно", "ова")]
    assert diff_spans("ФИЗИКА", "Физика") == [("равно", "ФИЗИКА")]
    assert ("недостаёт", "р") in diff_spans("Иностанный", "Иностранный")
```

- [ ] **Шаг 2: Запустить — должен упасть**

Run: `.venv/bin/python -m pytest tests/test_variants.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'etl.variants'`.

- [ ] **Шаг 3: Реализация `stand/etl/variants.py`**

```python
"""Вид ошибки написания относительно канона и посимвольная разница для подсветки.

Виды проверяются по очереди: сначала «снимаются» латиница, ё/е и регистр (вид
записывается, если снятие уменьшило расстояние между строками), потом пробелы,
потом структурные признаки: аббревиатура, сокращение, обрезано, опечатка.
"""
import re
from difflib import SequenceMatcher

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

NOT_DISCIPLINE = "—"
_LATIN = str.maketrans("ABCEHKMOPTXaceopxy", "АВСЕНКМОРТХасеорху")
_FULL = re.compile(r"^(?P<s>\S+) (?P<i>[А-ЯЁ]\.[А-ЯЁ]\.)$")
_TOKEN = re.compile(r"[а-яa-z0-9]+")
_NOTE = re.compile(r"\([^)]*\)|\d+(?:[.,]\d+)*")
_ACRONYM = re.compile(r"[А-ЯЁA-Z]{2,6}")


def _yo(s: str) -> str:
    return s.replace("ё", "е").replace("Ё", "Е")


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _subsequence(short: str, long_: str) -> bool:
    it = iter(long_)
    return all(ch in it for ch in short)


def _is_abbrev(s: str, c: str) -> bool:
    """Каждое слово написания — начало очередного слова канона («жизнедеят.» / «жизнедеятельности»)."""
    words, i = _TOKEN.findall(c), 0
    for t in _TOKEN.findall(s):
        while i < len(words) and not words[i].startswith(t):
            i += 1
        if i == len(words):
            return False
        i += 1
    return True


def _text_kind(orig: str, s: str, c: str) -> str:
    sk, ck = s.strip(" .,"), c.strip(" .,")
    if ("." in s or "-" in s) and _is_abbrev(s, c):
        return "сокращение"
    if sk and sk in ck:
        return "обрезано"
    if _is_abbrev(s, c):
        return "сокращение"
    if Levenshtein.distance(sk, ck) <= 2 or fuzz.ratio(sk, ck) >= 85:
        return "опечатка"
    return "другое"


def _teacher_kind(spelling: str, canonical: str) -> list[str]:
    ms, mc = _FULL.match(spelling), _FULL.match(canonical)
    kinds: list[str] = []
    if mc and not ms:
        kinds.append("нет инициалов")
        a, b = spelling, mc.group("s")
    elif ms and mc:
        if ms.group("i") != mc.group("i"):
            kinds.append("инициалы")
        a, b = ms.group("s"), mc.group("s")
    else:
        a, b = spelling, canonical
    a, b = _yo(a).casefold(), _yo(b).casefold()
    if a != b:
        if a + "а" == b or b + "а" == a:
            kinds.append("родовое окончание")
        elif Levenshtein.distance(a, b) <= 2:
            kinds.append("опечатка")
        else:
            kinds.append("другое")
    return kinds or ["другое"]


def classify(kind: str, spelling: str, canonical: str) -> list[str]:
    if canonical == NOT_DISCIPLINE:
        return ["не дисциплина"]
    if spelling == canonical:
        return []
    if kind != "teacher" and _ACRONYM.fullmatch(spelling.strip()) and " " in canonical \
            and _subsequence(spelling.strip().casefold(), _yo(canonical).casefold()) \
            and spelling.strip()[0].casefold() == canonical[0].casefold():
        return ["аббревиатура"]
    kinds: list[str] = []
    s, c = spelling, canonical
    for name, f in (("латиница", lambda x: x.translate(_LATIN)), ("ё/е", _yo), ("регистр", str.casefold)):
        s2, c2 = f(s), f(c)
        if Levenshtein.distance(s2, c2) < Levenshtein.distance(s, c):
            kinds.append(name)
        s, c = s2, c2
        if s == c:
            return kinds
    if _nospace(s) == _nospace(c):
        return kinds + ["пробел"]
    if kind == "teacher":
        return kinds + _teacher_kind(spelling, canonical)
    if kind == "discipline":
        extra = [t for t in _NOTE.findall(s) if t not in c]
        if extra:
            kinds.append("лишняя пометка")
            for t in extra:
                s = s.replace(t, " ")
            s = " ".join(s.split())
            if s == c or _nospace(s) == _nospace(c):
                return kinds
    return kinds + [_text_kind(spelling, s, c)]


def diff_spans(spelling: str, canonical: str) -> list[tuple[str, str]]:
    """Отрезки написания относительно канона. Регистр не подсвечивается: на это есть вид «регистр»."""
    a, b = spelling.lower(), canonical.lower()
    if len(a) != len(spelling) or len(b) != len(canonical):   # редкие символы меняют длину при lower()
        a, b = spelling, canonical
    out: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(("равно", spelling[i1:i2]))
        elif op == "delete":
            out.append(("лишнее", spelling[i1:i2]))
        elif op == "insert":
            out.append(("недостаёт", canonical[j1:j2]))
        else:
            out.append(("замена", spelling[i1:i2]))
    return out
```

- [ ] **Шаг 4: Запустить**

Run: `.venv/bin/python -m pytest tests/test_variants.py -q`
Expected: PASS. Если какой-то пример классифицируется иначе — проверить порядок признаков в `_text_kind`, а не подгонять ожидание: примеры взяты из ручной проверки.

- [ ] **Шаг 5: Коммит**

```bash
git add stand/etl/variants.py tests/test_variants.py
git commit -m "Вид ошибки написания и посимвольная разница"
```

---

### Задача 5: Сверка склеек (`etl/audit.py`)

**Файлы:**
- Создать: `stand/etl/audit.py`
- Тест: `tests/test_audit.py`

**Интерфейсы:**
- Производит: `Agreement(tp: int, fp: int, fn: int)` с свойствами `precision: float`, `recall: float` (1.0 при пустом знаменателе); `pair_agreement(rules: dict[str, str], truth: dict[str, str]) -> Agreement` — сравнение по парам написаний, учитываются только ключи, которые есть в обоих словарях.

- [ ] **Шаг 1: Тест**

```python
from etl.audit import Agreement, pair_agreement


def test_pairs_counted_against_truth():
    truth = {"a": "X", "b": "X", "c": "Y", "d": "Y"}
    rules = {"a": "1", "b": "1", "c": "1", "d": "2"}
    # правила склеили (a,b) верно, (a,c), (b,c) ложно; пропустили (c,d)
    assert pair_agreement(rules, truth) == Agreement(tp=1, fp=2, fn=1)


def test_keys_missing_in_one_side_are_ignored_and_empty_is_perfect():
    assert pair_agreement({"a": "1"}, {"b": "X"}) == Agreement(0, 0, 0)
    assert Agreement(0, 0, 0).precision == 1.0 and Agreement(0, 0, 0).recall == 1.0
    assert Agreement(3, 1, 0).precision == 0.75
```

- [ ] **Шаг 2: Запустить — должен упасть** (`.venv/bin/python -m pytest tests/test_audit.py -q`, `ModuleNotFoundError`)

- [ ] **Шаг 3: Реализация**

```python
"""Сверка автоправил со словарём: сколько пар написаний правила склеили верно,
сколько ложно и сколько пропустили."""
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Agreement:
    tp: int   # склеено и правилами, и словарём
    fp: int   # склеено правилами, словарь разделил
    fn: int   # склеено словарём, правила не склеили

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


def _pairs(groups: Counter) -> int:
    return sum(n * (n - 1) // 2 for n in groups.values())


def pair_agreement(rules: dict[str, str], truth: dict[str, str]) -> Agreement:
    keys = [k for k in truth if k in rules]
    both = _pairs(Counter((rules[k], truth[k]) for k in keys))
    return Agreement(both,
                     _pairs(Counter(rules[k] for k in keys)) - both,
                     _pairs(Counter(truth[k] for k in keys)) - both)
```

- [ ] **Шаг 4: Запустить** — PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add stand/etl/audit.py tests/test_audit.py
git commit -m "Сверка склеек правил со словарём по парам написаний"
```

---

### Задача 6: Чтение словаря (`etl/dictionary.py`)

**Файлы:**
- Создать: `stand/etl/dictionary.py`
- Создать: `stand/etl/dictionary/disciplines.csv`, `teachers.csv`, `places.csv`, `groups.csv`, `lesson_types.csv` — пока только заголовки
- Тест: `tests/test_dictionary.py`

**Интерфейсы:**
- Потребляет: `etl.variants.NOT_DISCIPLINE`, `etl.normalize.disc_key`, `etl.clean.LESSON_TYPES` (см. шаг 3).
- Производит:
  - `Entry(canonical: str, confidence: str, kind: str = "", note: str = "")`, свойство `source` → `"словарь"` при `h`, `"словарь?"` при `l`.
  - `Dictionary(disciplines: dict[str, Entry], teachers: dict[str, dict[str, Entry]], rooms: dict[tuple[str, str], Entry], groups: dict[str, Entry], lesson_types: dict[str, Entry])`; `teachers[написание][дисциплина или ""]`; `rooms[(корпус, как записано)].canonical == "корпус|аудитория"`.
  - `Dictionary.empty() -> Dictionary`, `Dictionary.teacher(spelling: str, discipline: str | None) -> Entry | None`, `Dictionary.known_words() -> set[str]`.
  - `DICTIONARY_DIR: Path`, `COLUMNS: dict[str, list[str]]` (заголовки файлов), `load_dictionary(path: Path = DICTIONARY_DIR) -> Dictionary`, `DictionaryError(ValueError)`.

- [ ] **Шаг 1: Заголовки CSV**

```bash
mkdir -p stand/etl/dictionary
printf 'написание,канон,уверенность,вид,примечание\n' > stand/etl/dictionary/disciplines.csv
printf 'написание,дисциплина,канон,уверенность,вид,примечание\n' > stand/etl/dictionary/teachers.csv
printf 'корпус,как записано,корпус_канон,аудитория_канон,уверенность,вид,примечание\n' > stand/etl/dictionary/places.csv
printf 'написание,канон,уверенность,вид,примечание\n' > stand/etl/dictionary/groups.csv
printf 'написание,канон,уверенность,вид,примечание\n' > stand/etl/dictionary/lesson_types.csv
```

- [ ] **Шаг 2: Тесты**

```python
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
    (base / "groups.csv").write_text("\ufeff" + text + "\nВТ -404,ВТ-404,h,,\n\n", encoding="utf-8")
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
```

- [ ] **Шаг 3: Запустить — должен упасть** (`ModuleNotFoundError: No module named 'etl.dictionary'`)

- [ ] **Шаг 4: Список типов занятий в `clean.py`**

В `stand/etl/clean.py` рядом с `UNKNOWN`:

```python
LESSON_TYPES = ("лекция", "практика", "лабораторная", "семинар", "консультация", "зачёт", "экзамен", UNKNOWN)
```

- [ ] **Шаг 5: Реализация `stand/etl/dictionary.py`**

```python
"""Проверенный вручную словарь написаний (stand/etl/dictionary/*.csv).

Ключ — написание после clean (для аудиторий — корпус и текст аудитории как в
ячейке). Метод проверки и правила дополнения — в dictionary/README.md.
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from etl.clean import LESSON_TYPES
from etl.normalize import disc_key
from etl.variants import NOT_DISCIPLINE

DICTIONARY_DIR = Path(__file__).parent / "dictionary"
_TEACHER_CANON = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?(?: [А-ЯЁ]\.[А-ЯЁ]\.)?$")
_COMMON = ["уверенность", "вид", "примечание"]
COLUMNS = {
    "disciplines": ["написание", "канон", *_COMMON],
    "teachers": ["написание", "дисциплина", "канон", *_COMMON],
    "places": ["корпус", "как записано", "корпус_канон", "аудитория_канон", *_COMMON],
    "groups": ["написание", "канон", *_COMMON],
    "lesson_types": ["написание", "канон", *_COMMON],
}


class DictionaryError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    canonical: str
    confidence: str          # h — уверенно, l — под сомнением
    kind: str = ""           # вид ошибки, если автоматическая классификация не подходит
    note: str = ""

    @property
    def source(self) -> str:
        return "словарь" if self.confidence == "h" else "словарь?"


@dataclass
class Dictionary:
    disciplines: dict[str, Entry] = field(default_factory=dict)
    teachers: dict[str, dict[str, Entry]] = field(default_factory=dict)
    rooms: dict[tuple[str, str], Entry] = field(default_factory=dict)
    groups: dict[str, Entry] = field(default_factory=dict)
    lesson_types: dict[str, Entry] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "Dictionary":
        return cls()

    def teacher(self, spelling: str, discipline: str | None) -> Entry | None:
        """Строка с дисциплиной занятия, иначе строка без дисциплины."""
        by_discipline = self.teachers.get(spelling)
        if not by_discipline:
            return None
        return by_discipline.get(discipline or "") or by_discipline.get("")

    def known_words(self) -> set[str]:
        """Слова канонов дисциплин: два таких слова не считаются опечаткой друг друга."""
        return {w for e in self.disciplines.values() if e.canonical != NOT_DISCIPLINE
                for w in re.findall(r"[а-яa-z]+", disc_key(e.canonical)) if len(w) >= 3}


def _rows(path: Path, name: str):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS[name]:
            raise DictionaryError(f"{path.name}: ожидались столбцы {', '.join(COLUMNS[name])}, "
                                  f"а в файле: {reader.fieldnames}")
        for line, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            row = {k: (v or "").strip() for k, v in row.items()}
            if row["уверенность"] not in ("h", "l"):
                raise DictionaryError(f"{path.name}, строка {line}: уверенность должна быть h или l")
            yield line, row


def _entry(row: dict, canonical: str) -> Entry:
    return Entry(canonical, row["уверенность"], row["вид"], row["примечание"])


def _put(target: dict, key, entry: Entry, path: Path, line: int) -> None:
    if key in target:
        raise DictionaryError(f"{path.name}, строка {line}: дубль ключа {key}")
    target[key] = entry


def load_dictionary(path: Path = DICTIONARY_DIR) -> Dictionary:
    path = Path(path)
    d = Dictionary()
    for name in COLUMNS:
        file = path / f"{name}.csv"
        for line, row in _rows(file, name):
            if name == "places":
                if not row["корпус_канон"] or not row["аудитория_канон"]:
                    raise DictionaryError(f"{file.name}, строка {line}: пустой канон")
                _put(d.rooms, (row["корпус"], row["как записано"]),
                     _entry(row, f"{row['корпус_канон']}|{row['аудитория_канон']}"), file, line)
                continue
            canonical = row["канон"]
            if not canonical:
                raise DictionaryError(f"{file.name}, строка {line}: пустой канон")
            if name == "teachers":
                if not _TEACHER_CANON.match(canonical):
                    raise DictionaryError(f"{file.name}, строка {line}: канон «{canonical}» — не «Фамилия И.О.» и не фамилия")
                _put(d.teachers.setdefault(row["написание"], {}), row["дисциплина"],
                     _entry(row, canonical), file, line)
            elif name == "lesson_types":
                if canonical not in LESSON_TYPES:
                    raise DictionaryError(f"{file.name}, строка {line}: неизвестный тип занятия «{canonical}»")
                _put(d.lesson_types, row["написание"], _entry(row, canonical), file, line)
            else:
                _put(getattr(d, name), row["написание"], _entry(row, canonical), file, line)
    return d
```

Сообщение о дубле содержит слово «дубль», о пустом каноне — «канон», о неизвестном типе — «тип», о заголовке — «столбц»: на них опираются тесты.

- [ ] **Шаг 6: Запустить**

Run: `.venv/bin/python -m pytest tests/test_dictionary.py -q`
Expected: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add stand/etl/dictionary.py stand/etl/dictionary/ stand/etl/clean.py tests/test_dictionary.py
git commit -m "Чтение проверенного словаря написаний из CSV"
```

---

### Задача 7: Автоправила — дисциплины и группы

**Файлы:**
- Изменить: `stand/etl/normalize.py` (`_sentence_case`, `_counterpart`, `_can_merge`, `cluster_disciplines`; новое `normalize_group`)
- Тест: `tests/test_normalize.py`

**Интерфейсы:**
- Производит:
  - `cluster_disciplines(names: list[str], anchors: dict[str, str] | None = None, teachers_of: dict[str, set[str]] | None = None, known_words: set[str] | None = None) -> tuple[dict[str, str], list[Merge]]` — `names` — непроверенные написания (с повторами по числу занятий); `anchors` — проверенные написания → канон словаря (канон `—` игнорируется); `teachers_of` — написание дисциплины (любое) → преподаватели; маппинг возвращается только для `names`, не входящих в `anchors`.
  - `normalize_group(name: str) -> str`.
  - `LOWER_WORDS: frozenset[str]` — предлоги и союзы.

- [ ] **Шаг 1: Тесты в `tests/test_normalize.py`**

```python
from etl.normalize import normalize_group


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
```

Добавить `import pytest` в начало файла, если его нет.

- [ ] **Шаг 2: Запустить — должны упасть**

Run: `.venv/bin/python -m pytest tests/test_normalize.py -q`
Expected: FAIL (`unexpected keyword argument 'anchors'`, `ImportError: normalize_group`, «И» с заглавной).

- [ ] **Шаг 3: `_sentence_case`, `LOWER_WORDS`, `normalize_group`**

```python
LOWER_WORDS = frozenset({"и", "в", "во", "на", "с", "со", "по", "для", "из", "к", "от", "до", "при", "без",
                         "над", "под", "об", "о", "у", "за", "или"})


def _sentence_case(name: str, keep_caps: frozenset[str] = frozenset()) -> str:
    """«ИННОВАЦИОННЫЙ МЕНЕДЖМЕНТ АПК» → «Инновационный менеджмент АПК».

    Капсом остаются слова, которые капсом записаны в других (не капсовых)
    вариантах кластера, и короткие аббревиатуры (до 3 букв), кроме предлогов и
    союзов: «… И ОХРАНА ТРУДА» → «… и охрана труда».
    """
    out = []
    for i, w in enumerate(name.split()):
        core = w.strip(".,;:()«»")
        short_abbr = sum(c.isalpha() for c in w) <= 3 and w.isupper() and core.lower() not in LOWER_WORDS
        out.append(w if i > 0 and (core in keep_caps or short_abbr) else w.lower())
    s = " ".join(out)
    return s[:1].upper() + s[1:]


def normalize_group(name: str) -> str:
    """«ВТ -404» → «ВТ-404», «Б-ВБ 301» → «Б-ВБ-301». Обрывки имён («-101», «») не чинятся."""
    s = " ".join((name or "").split())
    s = re.sub(r"\s*-\s*", "-", s)
    return re.sub(r"(?<=[А-ЯЁа-яё])\s+(?=\d)", "-", s)
```

- [ ] **Шаг 4: Запреты склейки**

```python
_SHORT_TOKEN = re.compile(r"(?<![а-яa-z])[а-яa-z]{2,3}(?![а-яa-z.])")


def _short_tokens(key: str) -> list[str]:
    """Короткие слова без точки — аббревиатуры («в ЛА» / «в ЛД»): должны совпадать точно."""
    return sorted(t for t in _SHORT_TOKEN.findall(key) if t not in LOWER_WORDS)


def _counterpart(word: str, others: list[str], known: set[str]) -> bool:
    """У слова есть пара: совпадение, сокращение («технол.» / «технологии»),
    слипшиеся слова («безопасностьжизнедеятельности») или опечатка — если оба
    слова не самостоятельные слова словаря («микро…» / «макроэкономика»)."""
    for o in others:
        short, long_ = sorted((word, o), key=len)
        if short == long_ or long_.startswith(short):
            return True
        if len(short) >= 5 and short in long_:
            return True
        if _word_typo(word, o) and not (word in known and o in known):
            return True
    return False


def _can_merge(a: str, b: str, known: set[str] = frozenset()) -> bool:
    """Запрет склейки разных дисциплин, похожих по буквам (см. спеку, «Нормализация»)."""
    short, long_ = sorted((a, b), key=len)
    if short in long_:
        return False
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    if _short_tokens(a) != _short_tokens(b):
        return False
    wa, wb = _words(a), _words(b)
    return all(_counterpart(w, wb, known) for w in wa) and all(_counterpart(w, wa, known) for w in wb)
```

- [ ] **Шаг 5: `cluster_disciplines`**

```python
PREFIX_MIN_WORDS, PREFIX_MIN_LEN = 3, 20


def cluster_disciplines(names: list[str], anchors: dict[str, str] | None = None,
                        teachers_of: dict[str, set[str]] | None = None,
                        known_words: set[str] | None = None) -> tuple[dict[str, str], list[Merge]]:
    """Склеивает непроверенные написания дисциплин.

    Проверенные написания (anchors: написание → канон словаря) — готовые
    кластеры: новое написание может к ним присоединиться и получает канон
    словаря, но сами они не перекраиваются. Затем обрезанное название
    присоединяется к единственному кластеру, чьё название с него начинается и у
    которого есть общий преподаватель. Канон нового кластера — вариант с
    наименьшим числом сокращений, затем не капсом, затем самый частый, затем
    самый длинный; капс приводится к виду предложения.
    """
    anchors = {n: c for n, c in (anchors or {}).items() if c != NOT_DISCIPLINE}
    known = known_words or set()
    counts = Counter(n for n in names if n not in anchors)
    key_counts: Counter[str] = Counter()
    for name, n in counts.items():
        key_counts[disc_key(name)] += n

    reps: list[str] = []
    anchor_canon: dict[str, str] = {}
    for name, canon in anchors.items():
        k = disc_key(name)
        if k not in anchor_canon:
            anchor_canon[k] = canon
            reps.append(k)
    cluster_of: dict[str, str] = {k: k for k in anchor_canon}
    score_of: dict[str, float] = {k: 100.0 for k in anchor_canon}
    for key, _ in key_counts.most_common():
        if key in anchor_canon:
            continue
        best = None
        if reps:
            for cand, score, _ in process.extract(key, reps, scorer=fuzz.ratio,
                                                  score_cutoff=DISCIPLINE_THRESHOLD, limit=5):
                if _can_merge(key, cand, known):
                    best = (cand, score)
                    break
        if best:
            cluster_of[key], score_of[key] = best
        else:
            reps.append(key)
            cluster_of[key], score_of[key] = key, 100.0

    if teachers_of:
        _join_truncated(key_counts, cluster_of, score_of, anchor_canon, teachers_of)

    variants: dict[str, Counter[str]] = {}
    for name, n in counts.items():
        variants.setdefault(cluster_of[disc_key(name)], Counter())[name] += n
    canonical_of_rep: dict[str, str] = {}
    for rep, vs in variants.items():
        if rep in anchor_canon:
            canonical_of_rep[rep] = anchor_canon[rep]
            continue
        keep_caps = frozenset(w.strip(".,;:()«»") for v in vs if not _is_caps(v)
                              for w in v.split() if sum(c.isalpha() for c in w) >= 2 and w.isupper())
        best = min(vs, key=lambda v: (_abbreviations(v), _is_caps(v), -vs[v], -len(v), v))
        canonical_of_rep[rep] = _sentence_case(best, keep_caps) if _is_caps(best) else best[:1].upper() + best[1:]

    mapping = {name: canonical_of_rep[cluster_of[disc_key(name)]] for name in counts}
    merges = [
        Merge("discipline", name, mapping[name], score_of[disc_key(name)])
        for name in counts
        if score_of[disc_key(name)] < 100 and mapping[name] != name   # канон сам с собой не склеивается
    ]
    return mapping, merges


def _join_truncated(key_counts, cluster_of, score_of, anchor_canon, teachers_of) -> None:
    """Обрезанное название → единственный кластер, чьё название с него начинается
    и у которого есть общий преподаватель."""
    teachers_by_key: dict[str, set[str]] = {}
    for name, ts in teachers_of.items():
        teachers_by_key.setdefault(disc_key(name), set()).update(ts)
    all_keys = list(cluster_of)
    for key in key_counts:
        if cluster_of[key] != key or key in anchor_canon:
            continue
        if len(_words(key)) < PREFIX_MIN_WORDS and len(key) < PREFIX_MIN_LEN:
            continue
        mine = teachers_by_key.get(key, set())
        targets = {cluster_of[k] for k in all_keys
                   if k != key and k.startswith(key) and mine & teachers_by_key.get(k, set())}
        if len(targets) == 1:
            target = targets.pop()
            for k in all_keys:
                if cluster_of[k] == key:
                    cluster_of[k] = target
            score_of[key] = fuzz.ratio(key, target)
```

В начало `normalize.py` добавить `from etl.variants import NOT_DISCIPLINE`.

- [ ] **Шаг 6: Запустить нормализацию и загрузку**

Run: `.venv/bin/python -m pytest tests/test_normalize.py tests/test_load.py -q`
Expected: PASS (старые тесты `cluster_disciplines(names)` работают без новых аргументов).

- [ ] **Шаг 7: Коммит**

```bash
git add stand/etl/normalize.py tests/test_normalize.py
git commit -m "Автоправила дисциплин: кластеры словаря, обрезанные названия, запрет ложных опечаток, регистр предлогов; нормализация групп"
```

---

### Задача 8: Автоправила — преподаватели

**Файлы:**
- Изменить: `stand/etl/normalize.py` (`resolve_teachers`)
- Тест: `tests/test_normalize.py`

**Интерфейсы:**
- Производит: `resolve_teachers(names: list[str], disciplines_of: dict[str, set[str]] | None = None, fixed: dict[str, str] | None = None) -> tuple[dict[str, str], list[Merge]]` — `names` — непроверенные написания; `fixed` — проверенные написание → канон (их канонов ФИО — готовые цели); `disciplines_of` — написание преподавателя (любое) → каноны дисциплин его занятий; маппинг — только для написаний не из `fixed`.

- [ ] **Шаг 1: Тесты**

```python
def test_initials_differ_by_one_letter_with_shared_discipline():
    mapping, _ = resolve_teachers(["Анникова Л.В."] * 2 + ["Анникова Л.А."],
                                  disciplines_of={"Анникова Л.В.": {"Клиническая диагностика"},
                                                  "Анникова Л.А.": {"Клиническая диагностика"}})
    assert mapping["Анникова Л.А."] == "Анникова Л.В."


def test_swapped_initials_with_shared_discipline():
    mapping, _ = resolve_teachers(["Козлов Е.С."] * 4 + ["Козлов С.Е."] * 3,
                                  disciplines_of={"Козлов Е.С.": {"Лабораторная диагностика"},
                                                  "Козлов С.Е.": {"Лабораторная диагностика"}})
    assert mapping["Козлов С.Е."] == "Козлов Е.С."


def test_different_initials_without_shared_discipline_stay_apart():
    mapping, _ = resolve_teachers(["Кузьмин А.М."] * 6 + ["Кузьмин А.Н."] * 2,
                                  disciplines_of={"Кузьмин А.М.": {"Общая физическая подготовка"},
                                                  "Кузьмин А.Н.": {"Физическая культура и спорт"}})
    assert mapping["Кузьмин А.Н."] == "Кузьмин А.Н."


def test_bare_surname_goes_to_full_name_with_shared_discipline():
    mapping, _ = resolve_teachers(
        ["Антипова Е.Ю."] * 16 + ["Антипова Е.А."] * 3 + ["Антипова"] * 4,
        disciplines_of={"Антипова Е.Ю.": {"Философия"}, "Антипова Е.А.": {"Педагогика"},
                        "Антипова": {"Философия"}})
    assert mapping["Антипова"] == "Антипова Е.Ю."
    assert mapping["Антипова Е.А."] == "Антипова Е.А."     # «Е.А.» и «Е.Ю.» без общей дисциплины


def test_gender_ending_with_shared_discipline():
    mapping, _ = resolve_teachers(["Березкин А.С."] * 14 + ["Березкина А.С."] * 2,
                                  disciplines_of={"Березкин А.С.": {"Тракторы и автомобили"},
                                                  "Березкина А.С.": {"Тракторы и автомобили"}})
    assert mapping["Березкина А.С."] == "Березкин А.С."


def test_fixed_names_are_targets_and_not_remapped():
    mapping, _ = resolve_teachers(["Торопова В.Ю."], fixed={"Торопова В.В.": "Торопова В.В."},
                                  disciplines_of={"Торопова В.Ю.": {"Отраслевая экономика"},
                                                  "Торопова В.В.": {"Отраслевая экономика"}})
    assert mapping == {"Торопова В.Ю.": "Торопова В.В."}
```

Старый тест `test_gender_pair_not_merged` остаётся: без общей дисциплины «Иванов А.А.»/«Иванова А.А.» не склеиваются.

- [ ] **Шаг 2: Запустить — должны упасть** (`unexpected keyword argument 'disciplines_of'`)

- [ ] **Шаг 3: Реализация**

```python
def _close_initials(a: str, b: str) -> bool:
    """«А.В.»/«А.С.» — одна буква; «С.Е.»/«Е.С.» — переставлены."""
    (a1, a2), (b1, b2) = (a[0], a[2]), (b[0], b[2])
    return (a1 == b1) != (a2 == b2) or (a1 == b2 and a2 == b1)


def _gender_pair(a: str, b: str) -> bool:
    a, b = _surname_key(a), _surname_key(b)
    return a + "а" == b or b + "а" == a


def resolve_teachers(names: list[str], disciplines_of: dict[str, set[str]] | None = None,
                     fixed: dict[str, str] | None = None) -> tuple[dict[str, str], list[Merge]]:
    """Канонизирует непроверенные написания преподавателей.

    Цели склейки — проверенные ФИО (fixed) и уже принятые полные ФИО (по
    убыванию частоты). Полное ФИО присоединяется:
    - при тех же инициалах и той же фамилии или фамилии с одной опечаткой;
    - при той же фамилии и инициалах, отличающихся одной буквой или
      переставленных, — только если есть общая дисциплина;
    - при тех же инициалах и фамилии, отличающейся родовым окончанием, — только
      если есть общая дисциплина.
    Фамилия без инициалов присоединяется к единственному полному ФИО с этой
    фамилией, а при нескольких — к единственному, с кем у неё общая дисциплина.
    """
    disciplines_of = disciplines_of or {}
    fixed = fixed or {}
    counts = Counter(n for n in names if n not in fixed)
    mapping: dict[str, str] = {}
    merges: list[Merge] = []

    canon_disc: dict[str, set[str]] = {}
    for spelling, canon in fixed.items():
        canon_disc.setdefault(canon, set()).update(disciplines_of.get(spelling, set()))
    canon_full = [c for c in dict.fromkeys(fixed.values()) if _FULL.match(c)]

    for name in sorted((n for n in counts if _FULL.match(n)), key=lambda n: (-counts[n], n)):
        m = _FULL.match(name)
        mine = disciplines_of.get(name, set())
        target = None
        for c in canon_full:
            cm = _FULL.match(c)
            same_i = cm.group("i") == m.group("i")
            same_s = _surname_key(cm.group("s")) == _surname_key(m.group("s"))
            shared = bool(mine & canon_disc.get(c, set()))
            if same_i and same_s:
                target = (c, 100.0)
            elif same_i and _similar_surnames(cm.group("s"), m.group("s")):
                target = (c, fuzz.ratio(c, name))
            elif same_s and shared and _close_initials(cm.group("i"), m.group("i")):
                target = (c, fuzz.ratio(c, name))
            elif same_i and shared and _gender_pair(cm.group("s"), m.group("s")):
                target = (c, fuzz.ratio(c, name))
            if target:
                break
        if target:
            mapping[name] = target[0]
            if target[1] < 100:
                merges.append(Merge("teacher", name, target[0], target[1]))
        else:
            canon_full.append(name)
            mapping[name] = name
        canon_disc.setdefault(mapping[name], set()).update(mine)

    by_surname: dict[str, list[str]] = {}
    for c in canon_full:
        by_surname.setdefault(_surname_key(_FULL.match(c).group("s")), []).append(c)

    for name in (n for n in counts if not _FULL.match(n)):
        exact = by_surname.get(_surname_key(name), [])
        if len(exact) == 1:
            mapping[name] = exact[0]
            continue
        if exact:                     # несколько полных ФИО с этой фамилией — решает общая дисциплина
            mine = disciplines_of.get(name, set())
            shared = [c for c in exact if mine & canon_disc.get(c, set())]
            mapping[name] = shared[0] if len(shared) == 1 else name
            if len(shared) == 1:
                merges.append(Merge("teacher", name, shared[0], 100.0))
            continue
        similar = [c for c in canon_full if _similar_surnames(_FULL.match(c).group("s"), name)]
        if len(similar) == 1:
            mapping[name] = similar[0]
            merges.append(Merge("teacher", name, similar[0], fuzz.ratio(_FULL.match(similar[0]).group("s"), name)))
        else:
            mapping[name] = name
    return mapping, merges
```

- [ ] **Шаг 4: Запустить**

Run: `.venv/bin/python -m pytest tests/test_normalize.py tests/test_load.py -q`
Expected: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add stand/etl/normalize.py tests/test_normalize.py
git commit -m "Автоправила преподавателей: инициалы и родовое окончание при общей дисциплине, проверенные ФИО как цели"
```

---

### Задача 9: Канонизация снапшота (`etl/canon.py`)

**Файлы:**
- Создать: `stand/etl/canon.py`
- Тест: `tests/test_canon.py`

**Интерфейсы:**
- Потребляет: `Dictionary`, `Entry` (задача 6), `cluster_disciplines`, `resolve_teachers`, `normalize_group` (задачи 7–8), `pair_agreement`, `Agreement` (задача 5), `ParsedLesson.type_raw`, `rooms_raw` (задачи 1–2), `NOT_DISCIPLINE`.
- Производит:
  - константы `SOURCE_RULE = "правило"`, `SOURCE_ASIS = "как есть"`, `SOURCE_PARSE = "разбор"`, `UNVERIFIED = {SOURCE_RULE, SOURCE_ASIS}`;
  - `Resolved(canonical: str | None, source: str, confidence: str = "", note: str = "", kind: str = "")` — `canonical is None` только для «не дисциплины»;
  - `Canonizer(dictionary: Dictionary, lessons: list[ParsedLesson])` с методами `discipline(spelling: str) -> Resolved`, `teacher(spelling: str, discipline: str | None) -> Resolved`, `room(building: str, room: str, raw: str) -> tuple[str, str, Resolved]` (канонические корпус и аудитория; `Resolved.canonical == "корпус|аудитория"`), `group(name: str) -> Resolved`, `lesson_type(raw: str | None, parsed: str) -> Resolved`, `audit() -> dict[str, Agreement]` (ключи `discipline`, `teacher`); атрибуты `disc_merges`, `teacher_merges: list[Merge]`.

- [ ] **Шаг 1: Тесты**

```python
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
```

- [ ] **Шаг 2: Запустить — должен упасть** (`ModuleNotFoundError: No module named 'etl.canon'`)

- [ ] **Шаг 3: Реализация `stand/etl/canon.py`**

```python
"""Канон каждого написания снапшота: проверенный словарь → автоправила → как есть.

Дисциплины решаются раньше преподавателей: правилам преподавателей и строкам
словаря с полем «дисциплина» нужен канон дисциплины занятия.
"""
from collections import Counter
from dataclasses import dataclass

from etl.audit import Agreement, pair_agreement
from etl.clean import ParsedLesson
from etl.dictionary import Dictionary, Entry
from etl.normalize import cluster_disciplines, normalize_group, resolve_teachers
from etl.variants import NOT_DISCIPLINE

SOURCE_RULE, SOURCE_ASIS, SOURCE_PARSE = "правило", "как есть", "разбор"
UNVERIFIED = {SOURCE_RULE, SOURCE_ASIS}


@dataclass(frozen=True)
class Resolved:
    canonical: str | None      # None — «не дисциплина»
    source: str
    confidence: str = ""
    note: str = ""
    kind: str = ""             # вид ошибки из словаря


def _from(e: Entry) -> Resolved:
    canonical = None if e.canonical == NOT_DISCIPLINE else e.canonical
    return Resolved(canonical, e.source, e.confidence, e.note, e.kind)


def _by_rule(spelling: str, canonical: str) -> Resolved:
    return Resolved(canonical, SOURCE_RULE if canonical != spelling else SOURCE_ASIS)


class Canonizer:
    def __init__(self, dictionary: Dictionary, lessons: list[ParsedLesson]):
        self.d = dictionary
        self._disc_names = [l.discipline for l in lessons if l.discipline]
        self._teachers_of: dict[str, set[str]] = {}
        for l in lessons:
            if l.discipline:
                self._teachers_of.setdefault(l.discipline, set()).update(l.teachers)
        verified = {n: e.canonical for n, e in dictionary.disciplines.items()}
        self._disc_rules, self.disc_merges = cluster_disciplines(
            [n for n in self._disc_names if n not in dictionary.disciplines],
            anchors=verified, teachers_of=self._teachers_of, known_words=dictionary.known_words())

        self._disc_of: dict[str, set[str]] = {}
        self._teacher_names: list[str] = []
        for l in lessons:
            canon = self.discipline(l.discipline).canonical if l.discipline else None
            for t in l.teachers:
                self._teacher_names.append(t)
                if canon:
                    self._disc_of.setdefault(t, set()).add(canon)
        fixed = {sp: ctx[""].canonical for sp, ctx in dictionary.teachers.items() if "" in ctx}
        self._teacher_rules, self.teacher_merges = resolve_teachers(
            [t for t in self._teacher_names if t not in dictionary.teachers],
            disciplines_of=self._disc_of, fixed=fixed)

    def discipline(self, spelling: str) -> Resolved:
        e = self.d.disciplines.get(spelling)
        return _from(e) if e else _by_rule(spelling, self._disc_rules.get(spelling, spelling))

    def teacher(self, spelling: str, discipline: str | None) -> Resolved:
        e = self.d.teacher(spelling, discipline)
        if e:
            return _from(e)
        if spelling in self.d.teachers:          # в словаре есть только строки для других дисциплин
            return Resolved(spelling, SOURCE_ASIS)
        return _by_rule(spelling, self._teacher_rules.get(spelling, spelling))

    def room(self, building: str, room: str, raw: str) -> tuple[str, str, Resolved]:
        e = self.d.rooms.get((building, raw))
        if e:
            b, r = e.canonical.split("|", 1)
            return b, r, _from(e)
        return building, room, Resolved(f"{building}|{room}", SOURCE_PARSE)

    def group(self, name: str) -> Resolved:
        e = self.d.groups.get(name)
        return _from(e) if e else _by_rule(name, normalize_group(name))

    def lesson_type(self, raw: str | None, parsed: str) -> Resolved:
        e = self.d.lesson_types.get(raw) if raw else None
        return _from(e) if e else Resolved(parsed, SOURCE_PARSE)

    def audit(self) -> dict[str, Agreement]:
        """Автоправила на проверенных написаниях так, будто словаря нет."""
        names = list(Counter(self._disc_names))
        truth = {n: self.d.disciplines[n].canonical for n in names
                 if n in self.d.disciplines and self.d.disciplines[n].canonical != NOT_DISCIPLINE}
        rules, _ = cluster_disciplines(list(truth), teachers_of=self._teachers_of)
        t_names = list(Counter(self._teacher_names))
        t_truth = {t: self.d.teachers[t][""].canonical for t in t_names
                   if set(self.d.teachers.get(t, {})) == {""}}
        t_rules, _ = resolve_teachers(list(t_truth), disciplines_of=self._disc_of)
        return {"discipline": pair_agreement(rules, truth), "teacher": pair_agreement(t_rules, t_truth)}
```

- [ ] **Шаг 4: Запустить**

Run: `.venv/bin/python -m pytest tests/test_canon.py -q`
Expected: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add stand/etl/canon.py tests/test_canon.py
git commit -m "Канонизация снапшота: словарь, затем автоправила, затем как есть"
```

---

### Задача 10: Загрузка в БД — `spellings`, `rule_audit`, флаг `unverified_name`, версия схемы

**Файлы:**
- Изменить: `stand/etl/load.py` (схема, `connect`, `load_snapshot`)
- Изменить: `stand/analytics/queries.py` (`merges_frame` → `spellings_frame`, `rule_audit_frame`; `FLAG_FIELDS`)
- Изменить: `stand/ui/data.py` (`_quality` → 2 таблицы; новое `spellings`)
- Изменить: `stand/views/quality.py` (раздел «Склейки написаний» → указатель на новую страницу)
- Изменить: `stand/labels.py` (`COLUMNS`)
- Тест: `tests/test_load.py`, `tests/test_analytics.py` (фикстура `frames`)

**Интерфейсы:**
- Потребляет: `Canonizer`, `Resolved`, `UNVERIFIED` (задача 9), `load_dictionary`, `Dictionary` (задача 6), `classify` (задача 4).
- Производит:
  - `load_snapshot(conn, path, dictionary: Dictionary | None = None) -> int` — `None` → `load_dictionary()`.
  - таблица `spellings(snapshot_id, kind, spelling, canonical, source, confidence, error_kinds, note, lessons, score)`; для `room` `spelling == "корпус|как записано"`, `canonical == "корпус|аудитория"`; для дисциплин-«не дисциплин» `canonical == "—"`.
  - таблица `rule_audit(snapshot_id, kind, tp, fp, fn)`.
  - `quality.unverified_name`.
  - `SCHEMA_VERSION = 2`; `connect()` пересоздаёт БД при другой версии.
  - `queries.spellings_frame(conn, sid) -> DataFrame[kind, spelling, canonical, source, confidence, error_kinds, note, uses, score]`, `queries.rule_audit_frame(conn, sid) -> DataFrame[kind, tp, fp, fn, precision, recall]`.
  - `data.quality(sid) -> tuple[cells, service]`, `data.spellings(sid) -> tuple[spellings, audit]`.

- [ ] **Шаг 1: Тесты в `tests/test_load.py`**

Во всех существующих вызовах `load_snapshot(conn, mini_snapshot_path)` в `tests/test_load.py` и в фикстуре `frames` файла `tests/test_analytics.py` добавить `dictionary=Dictionary.empty()` — они проверяют работу автоправил и не должны зависеть от содержимого настоящего словаря. Импорт: `from etl.dictionary import Dictionary, load_dictionary`. Новые тесты:

```python
import sqlite3

from etl.load import SCHEMA_VERSION


def _dict_dir(tmp_path, disciplines="", teachers=""):
    from etl.dictionary import COLUMNS
    d = tmp_path / "dict"
    d.mkdir()
    rows = {"disciplines": disciplines, "teachers": teachers}
    for name, header in COLUMNS.items():
        (d / f"{name}.csv").write_text(",".join(header) + "\n" + rows.get(name, ""), encoding="utf-8")
    return load_dictionary(d)


def test_dictionary_applied_and_spellings_recorded(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    d = _dict_dir(tmp_path, disciplines="Иностанный язык,Иностранный язык,h,,опечатка\n",
                  teachers="Пяткина,,Пяткина Н.А.,l,,одна в институте\n")
    load_snapshot(conn, mini_snapshot_path, dictionary=d)
    row = conn.execute("SELECT canonical, source, confidence, error_kinds, lessons FROM spellings "
                       "WHERE kind='discipline' AND spelling='Иностанный язык'").fetchone()
    assert row == ("Иностранный язык", "словарь", "h", "опечатка", 1)
    assert "Пяткина Н.А." in {r[0] for r in conn.execute("SELECT full_name FROM teachers")}
    assert conn.execute("SELECT source FROM spellings WHERE spelling='Пяткина'").fetchone() == ("словарь?",)
    assert _count(conn, "SELECT SUM(discipline_fuzzy) FROM quality") == 0


def test_spellings_cover_every_lesson_once_per_kind(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path, dictionary=Dictionary.empty())
    with_discipline = _count(conn, "SELECT COUNT(*) FROM lessons WHERE discipline_id IS NOT NULL")
    assert _count(conn, "SELECT SUM(lessons) FROM spellings WHERE kind='discipline'") == with_discipline
    assert _count(conn, "SELECT SUM(lessons) FROM spellings WHERE kind='group'") == 10
    rooms = conn.execute("SELECT spelling, canonical, source FROM spellings WHERE kind='room' "
                         "AND canonical='Прилегающие здания|Физ. зал'").fetchone()
    assert rooms == ("Прилегающие здания|физ. зал", "Прилегающие здания|Физ. зал", "разбор")
    assert {r[0] for r in conn.execute("SELECT kind FROM rule_audit")} == {"discipline", "teacher"}


def test_unverified_flag_without_dictionary(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path, dictionary=Dictionary.empty())
    assert _count(conn, "SELECT SUM(unverified_name) FROM quality") == 10


def test_old_database_is_recreated(tmp_path):
    path = tmp_path / "t.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE merges (snapshot_id INTEGER, kind TEXT, alias TEXT, canonical TEXT, score REAL);"
                      "CREATE TABLE snapshots (id INTEGER PRIMARY KEY, file_name TEXT);"
                      "INSERT INTO snapshots (file_name) VALUES ('old.json');")
    old.close()
    conn = connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "merges" not in tables and {"spellings", "rule_audit"} <= tables
    assert _count(conn, "SELECT COUNT(*) FROM snapshots") == 0
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
```

В `test_quality_flags` ожидания не меняются: `discipline_fuzzy == 1` («Иностанный язык» склеен правилом).

- [ ] **Шаг 2: Запустить — должны упасть**

Run: `.venv/bin/python -m pytest tests/test_load.py -q`
Expected: FAIL (`unexpected keyword argument 'dictionary'`, нет таблицы `spellings`).

- [ ] **Шаг 3: Схема и `connect` в `load.py`**

В `SCHEMA`: в `quality` после `needs_review INTEGER` добавить `, unverified_name INTEGER`; блок `merges` заменить на

```sql
CREATE TABLE IF NOT EXISTS spellings (
    snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    kind TEXT, spelling TEXT, canonical TEXT, source TEXT, confidence TEXT,
    error_kinds TEXT, note TEXT, lessons INTEGER, score REAL);
CREATE TABLE IF NOT EXISTS rule_audit (
    snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE CASCADE,
    kind TEXT, tp INTEGER, fp INTEGER, fn INTEGER);
CREATE INDEX IF NOT EXISTS ix_spellings_snapshot ON spellings(snapshot_id);
```

```python
# Меняется при несовместимой правке схемы: стенд пересоздаёт БД, а снапшоты
# из data/snapshots перечитывает ensure_loaded на следующем запуске.
SCHEMA_VERSION = 2


def connect(db_path: Path | str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        conn.execute("PRAGMA foreign_keys = OFF")
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
```

- [ ] **Шаг 4: `load_snapshot`**

Импорты: убрать `cluster_disciplines, resolve_teachers`; добавить

```python
from etl.canon import UNVERIFIED, Canonizer, Resolved
from etl.dictionary import Dictionary, load_dictionary
from etl.variants import NOT_DISCIPLINE, classify
```

Тело — по шагам (всё, что не упомянуто, остаётся как было):

```python
def load_snapshot(conn: sqlite3.Connection, path: Path, dictionary: Dictionary | None = None) -> int:
    path = Path(path)
    dictionary = load_dictionary() if dictionary is None else dictionary
    snap = read_snapshot(path)
    cells = flatten(snap["buildings"])
    parsed = [clean(c.subject_raw) for c in cells]
    canon = Canonizer(dictionary, [l for p in parsed for l in p.lessons])
    fuzzy_aliases = {m.alias for m in canon.disc_merges}    # склеено правилом с score < 100, не словарём
    tally: dict[tuple[str, str, str], list] = {}       # (вид, написание, канон) → [Resolved, занятий]

    def note(kind: str, spelling: str, r: Resolved, canonical: str) -> None:
        key = (kind, spelling, canonical)
        if key in tally:
            tally[key][1] += 1
        else:
            tally[key] = [r, 1]
```

`discipline_id(alias)` → `discipline_id(alias: str, canonical: str)`: берёт `canonical` из аргумента вместо `disc_map[alias]`.

Вставка ячейки: `group = canon.group(cell.group_name)`; в `INSERT INTO cells` вместо `cell.group_name` — `group.canonical`; в подсчёте `groups_cnt` — по `canon.group(c.group_name).canonical`.

Цикл занятий:

```python
            for part_idx, lesson in enumerate(p.lessons):
                note("group", cell.group_name, group, group.canonical)
                lt = canon.lesson_type(lesson.type_raw, lesson.lesson_type)
                if lesson.type_raw:
                    note("lesson_type", lesson.type_raw, lt, lt.canonical)
                d = canon.discipline(lesson.discipline) if lesson.discipline else None
                if d:
                    note("discipline", lesson.discipline, d, d.canonical or NOT_DISCIPLINE)
                disc = d.canonical if d else None
                building = lesson.building or cell.building
                lesson_id = conn.execute(
                    "INSERT INTO lessons (cell_id, snapshot_id, part_idx, lesson_type, discipline_id, subgroup,"
                    " building, week_factor) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (cell_id, snap_id, part_idx, lt.canonical,
                     discipline_id(lesson.discipline, disc) if disc else None,
                     lesson.subgroup, building, base / n),
                ).lastrowid
                resolved = [(t, canon.teacher(t, disc)) for t in lesson.teachers]
                for t, r in resolved:
                    note("teacher", t, r, r.canonical)
                canon_teachers = list(dict.fromkeys(r.canonical for _, r in resolved))
                for t in canon_teachers:
                    tid = get_id("t", (t,), "INSERT INTO teachers (snapshot_id, full_name, surname) VALUES (?, ?, ?)",
                                 (snap_id, t, t.split()[0]))
                    conn.execute("INSERT INTO lesson_teachers (lesson_id, teacher_id) VALUES (?, ?)", (lesson_id, tid))
                rooms = []
                for room, raw in zip(lesson.rooms, lesson.rooms_raw):
                    b, r_name, res = canon.room(building, room, raw)
                    note("room", f"{building}|{raw}", res, f"{b}|{r_name}")
                    rooms.append((b, r_name))
                for b, r_name in dict.fromkeys(rooms):
                    rid = get_id("r", (b, r_name), "INSERT INTO rooms (snapshot_id, building, name) VALUES (?, ?, ?)",
                                 (snap_id, b, r_name))
                    conn.execute("INSERT INTO lesson_rooms (lesson_id, room_id) VALUES (?, ?)", (lesson_id, rid))
                flags = {
                    "has_type": lt.canonical != UNKNOWN,
                    "has_discipline": bool(disc),
                    "has_teacher": bool(lesson.teachers),
                    "has_room": bool(lesson.rooms),
                    "discipline_fuzzy": lesson.discipline in fuzzy_aliases,
                    "teacher_surname_only": any(is_surname_only(t) for t in canon_teachers),
                    "split_cell": n > 1,
                    "suspicious_group": suspicious_group(group.canonical),
                    "truncated": p.truncated,
                }
                flags["needs_review"] = (not (flags["has_discipline"] and flags["has_teacher"] and flags["has_room"])
                                         or flags["suspicious_group"] or flags["truncated"])
                flags["unverified_name"] = ((bool(d) and d.source in UNVERIFIED)
                                            or any(r.source in UNVERIFIED for _, r in resolved))
```

Вместо вставки в `merges`:

```python
        scores = {(m.kind, m.alias): m.score for m in [*canon.disc_merges, *canon.teacher_merges]}
        rows = []
        for (kind, spelling, canonical), (r, uses) in tally.items():
            shown = spelling.split("|", 1)[1] if kind == "room" else spelling
            target = canonical.split("|", 1)[1] if kind == "room" else canonical
            kinds = [r.kind] if r.kind else classify(kind, shown, target)
            rows.append((snap_id, kind, spelling, canonical, r.source, r.confidence, ", ".join(kinds),
                         r.note, uses, scores.get((kind, spelling))))
        conn.executemany("INSERT INTO spellings (snapshot_id, kind, spelling, canonical, source, confidence,"
                         " error_kinds, note, lessons, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany("INSERT INTO rule_audit (snapshot_id, kind, tp, fp, fn) VALUES (?, ?, ?, ?, ?)",
                         [(snap_id, kind, a.tp, a.fp, a.fn) for kind, a in canon.audit().items()])
```

`ensure_loaded` ловит `ValueError`: `DictionaryError` — его подкласс, поэтому битый словарь даёт предупреждение «Снапшот не загружен: groups.csv: …», а не падение стенда.

- [ ] **Шаг 5: Запросы, данные, страница качества, подписи**

`stand/analytics/queries.py`: удалить `merges_frame`, добавить

```python
def spellings_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT kind, spelling, canonical, source, confidence, error_kinds, note, lessons AS uses, score"
        " FROM spellings WHERE snapshot_id = ?", conn, params=(snapshot_id,))


def rule_audit_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT kind, tp, fp, fn FROM rule_audit WHERE snapshot_id = ?",
                           conn, params=(snapshot_id,))
    df["precision"] = (100 * df["tp"] / (df["tp"] + df["fp"])).fillna(100.0).round(1)
    df["recall"] = (100 * df["tp"] / (df["tp"] + df["fn"])).fillna(100.0).round(1)
    return df
```

В `FLAG_FIELDS` добавить `"unverified_name": "написание не проверено"` (перед `needs_review`).

`stand/ui/data.py`: `_quality` возвращает `q.cells_quality_frame(...), q.service_cells(...)`, тип `tuple[pd.DataFrame, pd.DataFrame]`; `quality()` — тоже. Добавить

```python
@st.cache_data(show_spinner=False)
def _spellings(db: str, version: float, snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = connect(db)
    try:
        return q.spellings_frame(c, snapshot_id), q.rule_audit_frame(c, snapshot_id)
    finally:
        c.close()


def spellings(snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _spellings(*db_key(), snapshot_id)
```

`stand/views/quality.py`: `cells, service = data.quality(ctx.snapshot_id)`; блок `c1, c2 = st.columns(2)` … до конца заменить на

```python
st.subheader("Отброшенные служебные строки")
st.dataframe(ru(service), hide_index=True, width="stretch")
st.info("Что с чем объединено и где ошибки в написаниях — на странице «Словарь написаний».")
```

`stand/labels.py`, в `COLUMNS` добавить:

```python
    "spelling": "Написание", "source": "Источник", "confidence": "Уверенность", "error_kinds": "Вид ошибки",
    "error_kind": "Вид ошибки", "note": "Примечание", "uses": "Занятий", "spellings": "Написаний",
    "tp": "Верных склеек", "fp": "Ложных склеек", "fn": "Пропущенных склеек",
    "precision": "Точность, %", "recall": "Полнота, %", "kind_label": "Справочник",
```

- [ ] **Шаг 6: Все тесты, кроме демо**

Run: `.venv/bin/python -m pytest -q --ignore=tests/test_demo_snapshot.py`
Expected: PASS (страница «Качество данных» в `test_smoke.py` открывается без раздела склеек).

- [ ] **Шаг 7: Коммит**

```bash
git add stand/etl/load.py stand/analytics/queries.py stand/ui/data.py stand/views/quality.py stand/labels.py tests/test_load.py tests/test_analytics.py
git commit -m "Загрузка: словарь написаний, таблицы spellings и rule_audit, флаг unverified_name, версия схемы БД"
```

---

### Задача 11: Словарь — перенос ручных решений, досмотр новых написаний, CSV

Задача выполняется инструментами вне репозитория (`~/raspisanie-review/tools/`), в репозиторий попадают только CSV и README словаря. Решения прежней проверки: `~/raspisanie-review/{disciplines,teachers}.tsv` + `d_*.py`, `t_*.py`, `p_places.py` (формат описан в их заголовках).

**Файлы:**
- Создать (вне репозитория): `~/raspisanie-review/tools/export_v2.py`, `~/raspisanie-review/tools/to_csv.py`, решения `~/raspisanie-review/v2_*.py`
- Заполнить: `stand/etl/dictionary/*.csv`
- Создать: `stand/etl/dictionary/README.md`
- Тест: `tests/test_dictionary.py` (проверка настоящего словаря)

**Интерфейсы:**
- Потребляет: `clean`, `flatten`, `read_snapshot` в новой версии (задачи 1–3), `load_dictionary` (задача 6), `Canonizer` (задача 9).
- Производит: заполненный словарь, на котором у снапшота `2026-10-07_144819.json` все написания дисциплин и преподавателей имеют источник `словарь` или `словарь?`.

- [ ] **Шаг 1: Выгрузка написаний новой версией разбора с переносом решений — `~/raspisanie-review/tools/export_v2.py`**

```python
"""Написания дисциплин, преподавателей, групп, маркеров типа и аудиторий после
исправленного разбора; решения прежней проверки переносятся по точному
совпадению написания. Результат: v2_<вид>.tsv (написание, занятий, канон,
уверенность, примечание, перенесено/НОВОЕ, контекст)."""
import glob, runpy, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/home/vladislav/Рабочий_стол/Расписание 2.0")
sys.path.insert(0, str(REPO / "stand"))
from etl.clean import clean
from etl.flatten import flatten
from etl.load import read_snapshot

R = Path.home() / "raspisanie-review"


def old_decisions(tsv: str, prefix: str) -> dict[str, tuple[str, str, str]]:
    rows = {int(l.split("\t")[0]): l.rstrip("\n").split("\t") for l in open(R / tsv, encoding="utf-8")}
    dec = {}
    for f in sorted(glob.glob(str(R / f"{prefix}_*.py"))):
        dec.update(runpy.run_path(f)["R"])
    return {row[1]: dec.get(i, (row[3], "h", "")) for i, row in rows.items()}


old = {"discipline": old_decisions("disciplines.tsv", "d"), "teacher": old_decisions("teachers.tsv", "t")}
snap = read_snapshot(REPO / "data/snapshots/2026-10-07_144819.json")
seen = {k: Counter() for k in ("discipline", "teacher", "group", "lesson_type", "room")}
ctx = defaultdict(Counter)
for c in flatten(snap["buildings"]):
    for l in clean(c.subject_raw).lessons:
        seen["group"][c.group_name] += 1
        if l.type_raw:
            seen["lesson_type"][l.type_raw] += 1
            ctx[("lesson_type", l.type_raw)][l.lesson_type] += 1
        if l.discipline:
            seen["discipline"][l.discipline] += 1
            ctx[("discipline", l.discipline)][f"{'; '.join(l.teachers)} | {c.group_name}"] += 1
        for t in l.teachers:
            seen["teacher"][t] += 1
            ctx[("teacher", t)][f"{l.discipline} | {c.institute}"] += 1
        for room, raw in zip(l.rooms, l.rooms_raw):
            key = f"{l.building or c.building}|{raw}"
            seen["room"][key] += 1
            ctx[("room", key)][room] += 1
for kind, counter in seen.items():
    with open(R / f"v2_{kind}.tsv", "w", encoding="utf-8") as f:
        for spelling, n in sorted(counter.items()):
            canon, conf, note = old.get(kind, {}).get(spelling, ("", "", ""))
            status = "перенесено" if canon else "НОВОЕ"
            top = "; ".join(f"{k}×{v}" for k, v in ctx[(kind, spelling)].most_common(3))
            f.write(f"{spelling}\t{n}\t{canon}\t{conf}\t{note}\t{status}\t{top[:200]}\n")
    print(kind, len(counter), "написаний, новых:", sum(1 for s in counter if s not in old.get(kind, {})))
```

Run: `"/home/vladislav/Рабочий_стол/Расписание 2.0/.venv/bin/python" ~/raspisanie-review/tools/export_v2.py`
Expected: по строке на вид с числом написаний и новых. Числа записать в README словаря (шаг 6).

- [ ] **Шаг 2: Ручной досмотр новых и изменившихся написаний**

Для `v2_discipline.tsv` и `v2_teacher.tsv`: каждое написание со статусом `НОВОЕ` решить вручную тем же методом, что в первой проверке: контекст — преподаватели × группы × институт (`~/raspisanie-review/tools/tctx.py` для преподавателей), при сомнении — сырые ячейки. Решения записать в `~/raspisanie-review/v2_new.py`:

```python
# Новые написания после исправления разбора. Формат: (вид, написание): (канон, "h"/"l", примечание).
R = {
    ("discipline", "Природно-хозяйственная оценка территории"): ("Природно-хозяйственная оценка территории", "h", "раньше с хвостом «ст»"),
}
```

Решения прежней проверки вида «А/Б по дисциплине» (`t_*.py`: 220 Калашникова, 301 Лаврухин, 402 Новиков) перевести в строки с дисциплиной в `~/raspisanie-review/v2_splits.py`:

```python
# Фамилия без инициалов — разные люди по дисциплине: написание → [(канон дисциплины или "", канон)].
SPLITS = {
    "Калашникова": [("Маркетинг", "Калашникова А.Р."),
                    ("Управление документооборотом на предприятиях АПК", "Калашникова С.П."),
                    ("Анализ и прогнозирование конъюнктуры рынков АПК", "Калашникова С.П.")],
}
```

Каноны дисциплин в `SPLITS` брать из итогового канона дисциплин (`v2_discipline.tsv` + `v2_new.py`), а не из сырого написания.

- [ ] **Шаг 3: Группы, маркеры типа, аудитории**

- `v2_group.tsv` (≈256 строк): просмотреть все; канон — `normalize_group(написание)`, кроме битых (`''`, `-101`): для них канон = написание, `l`, примечание «обрывок имени от парсера».
- `v2_lesson_type.tsv`: каждому маркеру назначить тип из `LESSON_TYPES`; для `лекю`, `ек.`, `р.з.`, `лб.з.` — `вид` = `опечатка`/`обрезано`.
Решения записать так:

```python
# ~/raspisanie-review/v2_groups.py — только исключения; остальные группы: канон = normalize_group(имя), h
GROUPS = {
    "": ("", "l", "обрывок имени от парсера (двойной пробел в заголовке)"),
    "-101": ("-101", "l", "обрывок имени от парсера («Б-ЛА -101»)"),
}
```

```python
# ~/raspisanie-review/v2_types.py — каждый маркер из v2_lesson_type.tsv: (тип, "h"/"l", вид, примечание)
TYPES = {
    "лек.": ("лекция", "h", "", ""),
    "лекю": ("лекция", "h", "опечатка", ""),
    "ек.": ("лекция", "h", "обрезано", "оборвано начало ячейки"),
    "р.з.": ("практика", "h", "обрезано", "оборвано начало ячейки"),
    "пр.з. з.": ("практика", "h", "опечатка", "сдвоенный маркер"),
}
```

- `v2_room.tsv`: решения о местах из `p_places.py` перевести в строки `places.csv` для того, что разбор не исправляет сам: `(УК2, 5111) → УК2|511 l опечатка`, `(УК2, 5511) → УК2|551 l опечатка`, `(УК3, 409) → УК3|С-409 l нет префикса`, `(УК3, 305а) → УК3|С-305а h нет префикса`. Остальные места из `p_places.py` после задач 1–3 разбираются правильно — сверить по `v2_room.tsv`, что `ук 1`, `ГЛ-N`, `ЛХМ`, `ауд. № 7`, `С-305а` попали в верный корпус и аудиторию. Решения записать в `~/raspisanie-review/v2_places.py`:

```python
# (корпус, как записано): (корпус_канон, аудитория_канон, "h"/"l", вид, примечание)
PLACES = {
    ("УК2", "5111"): ("УК2", "511", "l", "опечатка", "лишняя 1; ин. яз. в 5xx"),
    ("УК2", "5511"): ("УК2", "551", "l", "опечатка", "рядом 512 и 507"),
    ("УК3", "409"): ("УК3", "С-409", "l", "нет префикса", "в УК3 есть только С-409"),
    ("УК3", "305а"): ("УК3", "С-305а", "h", "нет префикса", "те же гидробиология и Гуркина О.А."),
}
```

- [ ] **Шаг 4: Сборка CSV — `~/raspisanie-review/tools/to_csv.py`**

```python
"""v2_*.tsv + v2_new.py + v2_splits.py + v2_places.py → stand/etl/dictionary/*.csv."""
import csv, runpy, sys
from pathlib import Path

REPO = Path("/home/vladislav/Рабочий_стол/Расписание 2.0")
sys.path.insert(0, str(REPO / "stand"))
from etl.normalize import normalize_group

R = Path.home() / "raspisanie-review"
OUT = REPO / "stand/etl/dictionary"
new = runpy.run_path(str(R / "v2_new.py"))["R"]
splits = runpy.run_path(str(R / "v2_splits.py"))["SPLITS"]
places = runpy.run_path(str(R / "v2_places.py"))["PLACES"]
types = runpy.run_path(str(R / "v2_types.py"))["TYPES"]          # маркер → (тип, "h"/"l", вид, примечание)
groups_l = runpy.run_path(str(R / "v2_groups.py"))["GROUPS"]     # имя → (канон, "h"/"l", примечание) — только исключения


def tsv(kind):
    for line in open(R / f"v2_{kind}.tsv", encoding="utf-8"):
        spelling, n, canon, conf, note, status, _ = line.rstrip("\n").split("\t")
        yield spelling, canon, conf, note, status


def write(name, header, rows):
    with open(OUT / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(sorted(rows))


disc_rows, missing = [], []
for spelling, canon, conf, note, status in tsv("discipline"):
    if ("discipline", spelling) in new:
        canon, conf, note = new[("discipline", spelling)]
    elif status == "НОВОЕ":
        missing.append(("discipline", spelling))
        continue
    disc_rows.append((spelling, canon, conf, "", note))
disc_canons = {r[1] for r in disc_rows}

teacher_rows = []
for spelling, canon, conf, note, status in tsv("teacher"):
    if spelling in splits:
        for discipline, c in splits[spelling]:
            assert discipline == "" or discipline in disc_canons, (spelling, discipline)
            teacher_rows.append((spelling, discipline, c, "h", "", "разные люди по дисциплине"))
        continue
    if ("teacher", spelling) in new:
        canon, conf, note = new[("teacher", spelling)]
    elif status == "НОВОЕ":
        missing.append(("teacher", spelling))
        continue
    assert "/" not in canon, f"«{spelling}»: канон «{canon}» нужно разложить в v2_splits.py"
    teacher_rows.append((spelling, "", canon, conf, "", note))

group_rows = []
for g, *_ in tsv("group"):
    canon, conf, note = groups_l.get(g, (normalize_group(g), "h", ""))
    group_rows.append((g, canon, conf, "", note))
type_rows = [(m, t, conf, kind, note) for m, (t, conf, kind, note) in types.items()]
place_rows = [(b, raw, cb, cr, conf, kind, note) for (b, raw), (cb, cr, conf, kind, note) in places.items()]

assert not missing, f"не решены новые написания: {missing[:20]} … всего {len(missing)}"
write("disciplines", ["написание", "канон", "уверенность", "вид", "примечание"], disc_rows)
write("teachers", ["написание", "дисциплина", "канон", "уверенность", "вид", "примечание"], teacher_rows)
write("groups", ["написание", "канон", "уверенность", "вид", "примечание"], group_rows)
write("lesson_types", ["написание", "канон", "уверенность", "вид", "примечание"], type_rows)
write("places", ["корпус", "как записано", "корпус_канон", "аудитория_канон", "уверенность", "вид", "примечание"], place_rows)
print("дисциплин", len(disc_rows), "преподавателей", len(teacher_rows), "групп", len(group_rows),
      "маркеров", len(type_rows), "мест", len(place_rows))
```

`v2_types.py` и `v2_groups.py` заполняются в шаге 3 (формат — в комментариях выше).

Run: `"/home/vladislav/Рабочий_стол/Расписание 2.0/.venv/bin/python" ~/raspisanie-review/tools/to_csv.py`
Expected: строка с числами; при нерешённых написаниях — `AssertionError` со списком: вернуться к шагу 2.

- [ ] **Шаг 5: Тест настоящего словаря в `tests/test_dictionary.py`**

```python
def test_real_dictionary_is_consistent():
    d = load_dictionary()
    assert len(d.disciplines) > 2000 and len(d.teachers) > 600
    canons = {e.canonical for e in d.disciplines.values()}
    for spelling, by_discipline in d.teachers.items():
        for discipline in by_discipline:
            assert discipline == "" or discipline in canons, (spelling, discipline)
```

И в `tests/test_demo_snapshot.py` (скипается без снапшота):

```python
def test_demo_snapshot_names_are_all_verified(tmp_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, DEMO[-1])
    left = conn.execute("SELECT kind, spelling FROM spellings WHERE kind IN ('discipline', 'teacher')"
                        " AND source NOT IN ('словарь', 'словарь?')").fetchall()
    assert left == []
```

Run: `.venv/bin/python -m pytest tests/test_dictionary.py tests/test_demo_snapshot.py -q -k "real_dictionary or all_verified"`
Expected: PASS. Если `left` не пуст — это написания, которых не было в выгрузке шага 1 (например, разбор поменялся после неё): перевыгрузить и досмотреть.

- [ ] **Шаг 6: `stand/etl/dictionary/README.md`**

Содержание (числа — из вывода шагов 1 и 4):

```markdown
# Словарь написаний

Проверенные вручную каноны написаний для снапшота `data/snapshots/2026-10-07_144819.json`.
Стенд применяет словарь первым шагом нормализации; написания, которых здесь нет,
идут через автоправила и помечаются «не проверено» (страница «Словарь написаний»).

## Как проверялось

Каждое написание просмотрено вместе с контекстом: у дисциплины — преподаватели,
группы и институты; у преподавателя — дисциплины и институты; при сомнении — сырой
текст ячеек PDF. Уверенность `h` — решение однозначно по данным; `l` — вероятно,
но подтвердить можно только по PDF или у кафедры.

| файл | строк | из них `l` |
|---|---|---|
| disciplines.csv | … | … |
| teachers.csv | … | … |
| places.csv | … | … |
| groups.csv | … | … |
| lesson_types.csv | … | … |

## Файлы

- `disciplines.csv` — `написание, канон, уверенность, вид, примечание`; канон `—` — не дисциплина.
- `teachers.csv` — то же плюс `дисциплина`: строка с дисциплиной действует только на занятия
  этой дисциплины (одна фамилия — разные люди).
- `places.csv` — `корпус, как записано, корпус_канон, аудитория_канон, …`: только то, что
  разбор не может исправить сам (опечатки, пропущенный префикс).
- `groups.csv`, `lesson_types.csv` — `написание, канон, уверенность, вид, примечание`.

## Как дополнять

1. Открыть страницу «Словарь написаний», фильтр «Источник: правило, как есть».
2. Для каждого написания решить канон по контексту, дописать строку в CSV (UTF-8, разделитель —
   запятая, строки по алфавиту).
3. `.venv/bin/python -m pytest tests/test_dictionary.py` — словарь читается, дублей нет.
```

Таблицу заполнить фактическими числами (не оставлять `…`).

- [ ] **Шаг 7: Коммит**

```bash
git add stand/etl/dictionary/ tests/test_dictionary.py tests/test_demo_snapshot.py
git commit -m "Проверенный словарь написаний для снапшота 2026-10-07"
```

---

### Задача 12: Страница «Словарь написаний»

**Файлы:**
- Изменить: `stand/analytics/queries.py` (`error_summary`, `spelling_cards`)
- Создать: `stand/ui/cards.py`
- Создать: `stand/views/spellings.py`
- Изменить: `stand/app.py` (навигация)
- Тест: `tests/test_analytics.py`, `tests/test_cards.py`, `tests/test_smoke.py`

**Интерфейсы:**
- Потребляет: `data.spellings(sid)` (задача 10), `diff_spans` (задача 4), `SERIES`, `NEUTRAL`, `bar_h` из `charts/common.py`.
- Производит:
  - `queries.error_summary(sp: DataFrame, kind: str) -> DataFrame[error_kind, spellings, uses]`, по убыванию `uses`.
  - `queries.spelling_cards(sp: DataFrame, kind: str, error_kinds: tuple[str, ...] = (), sources: tuple[str, ...] = (), query: str = "", singles: bool = False) -> DataFrame` — строки выбранного справочника с колонками `shown`, `target` (написание и канон без корпуса для аудиторий) и `weight`; отфильтрованы целыми карточками; отсортированы по `weight` (занятия с неканоническими написаниями) убыв., затем канону, затем `uses` убыв.
  - `cards.diff_html(spelling: str, canonical: str, mode: str = "light") -> str`, `cards.card_html(canonical: str, rows: DataFrame, mode: str = "light") -> str`.

- [ ] **Шаг 1: Тесты чистых функций**

`tests/test_analytics.py` (в импорты добавить `import pandas as pd`):

```python
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
```

`tests/test_cards.py`:

```python
import pandas as pd

from ui.cards import card_html, diff_html


def test_diff_html_escapes_and_marks():
    html = diff_html("<Тороппова & Ко>", "<Торопова & Ко>")
    assert "&lt;" in html and "&amp;" in html and "<Тор" not in html
    assert "line-through" in html            # лишняя «п»


def test_card_html_has_every_spelling_and_note_escaped():
    rows = pd.DataFrame([{"shown": "Торопова", "target": "Торопова В.В.", "error_kinds": "нет инициалов",
                          "uses": 6, "source": "словарь?", "note": 'одна "в" институте'}])
    html = card_html("Торопова В.В.", rows)
    assert "Торопова В.В." in html and "нет инициалов" in html and "&quot;в&quot;" in html
    assert "?" in html
```

- [ ] **Шаг 2: Запустить — должны упасть** (`AttributeError: … error_summary`, `ModuleNotFoundError: ui.cards`)

- [ ] **Шаг 3: Функции в `queries.py`**

```python
def error_summary(sp: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Сколько написаний и занятий дал каждый вид ошибки в справочнике."""
    d = sp[(sp["kind"] == kind) & (sp["error_kinds"] != "")]
    d = d.assign(error_kind=d["error_kinds"].str.split(", ")).explode("error_kind")
    out = d.groupby("error_kind").agg(spellings=("spelling", "count"), uses=("uses", "sum")).reset_index()
    return out.sort_values(["uses", "error_kind"], ascending=[False, True], ignore_index=True)


def spelling_cards(sp: pd.DataFrame, kind: str, error_kinds: tuple[str, ...] = (), sources: tuple[str, ...] = (),
                   query: str = "", singles: bool = False) -> pd.DataFrame:
    """Строки карточек «канон → написания»: фильтры отбирают карточки целиком."""
    d = sp[sp["kind"] == kind].copy()
    strip = (lambda s: s.str.split("|", n=1).str[-1]) if kind == "room" else (lambda s: s)
    d["shown"], d["target"] = strip(d["spelling"]), strip(d["canonical"])

    def keep(mask: pd.Series) -> pd.DataFrame:
        return d[d["canonical"].isin(d.loc[mask, "canonical"])]

    if not singles:
        d = d[d.groupby("canonical")["spelling"].transform("count") > 1]
    if error_kinds:
        d = keep(d["error_kinds"].str.split(", ").apply(lambda ks: bool(set(ks) & set(error_kinds))))
    if sources:
        d = keep(d["source"].isin(sources))
    if query:
        needle = query.casefold()
        d = keep(d["spelling"].str.casefold().str.contains(needle, regex=False)
                 | d["canonical"].str.casefold().str.contains(needle, regex=False))
    off = d["uses"].where(d["shown"] != d["target"], 0)
    d = d.assign(weight=off.groupby(d["canonical"]).transform("sum"),
                 is_canon=(d["shown"] == d["target"]).astype(int))
    return d.sort_values(["weight", "canonical", "is_canon", "uses"],
                         ascending=[False, True, False, False], ignore_index=True)
```

(Канон внутри карточки идёт первой строкой — сортировка по `is_canon`.)

- [ ] **Шаг 4: `stand/ui/cards.py`**

```python
"""HTML карточек «канон → написания» для страницы «Словарь написаний».

Разница подсвечена цветом и начертанием (не только цветом): лишнее зачёркнуто,
недостающее подчёркнуто в скобках, заменённое — жирным. Пробелы в разнице
показаны знаком «␣»."""
import html

import pandas as pd

from charts.common import NEUTRAL, SERIES
from etl.variants import diff_spans

MARK = {"словарь": "", "словарь?": "?", "правило": "не проверено", "как есть": "не проверено", "разбор": ""}


def _colors(mode: str) -> dict[str, str]:
    s = SERIES[mode]
    return {"лишнее": s[1], "замена": s[3], "недостаёт": s[2]}


def diff_html(spelling: str, canonical: str, mode: str = "light") -> str:
    colors, out = _colors(mode), []
    for op, text in diff_spans(spelling, canonical):
        if op == "равно":
            out.append(html.escape(text))
            continue
        t = html.escape(text).replace(" ", "␣")
        style = {"лишнее": "text-decoration:line-through", "недостаёт": "text-decoration:underline",
                 "замена": "font-weight:700"}[op]
        shown = f"[{t}]" if op == "недостаёт" else t
        out.append(f'<span style="color:{colors[op]};{style}" title="{op}">{shown}</span>')
    return "".join(out)


def card_html(canonical: str, rows: pd.DataFrame, mode: str = "light") -> str:
    total = int(rows["uses"].sum())
    head = (f'<div style="font-weight:600;margin-bottom:4px">{html.escape(canonical)}'
            f'<span style="color:{NEUTRAL};font-weight:400"> · {len(rows)} напис. · {total} занятий</span></div>')
    body = []
    for r in rows.itertuples():
        is_canon = r.shown == r.target
        spelling = html.escape(r.shown) if is_canon else diff_html(r.shown, r.target, mode)
        kinds = "канон" if is_canon else html.escape(r.error_kinds or "")
        mark = MARK.get(r.source, "")
        note = html.escape(r.note or "", quote=True)
        body.append(f'<tr title="{note}"><td style="font-family:monospace;padding-right:16px">{spelling}</td>'
                    f'<td style="color:{NEUTRAL};padding-right:16px">{kinds}</td>'
                    f'<td style="text-align:right;padding-right:16px">{int(r.uses)}</td>'
                    f'<td style="color:{SERIES[mode][1] if mark else NEUTRAL}">{html.escape(mark)}</td></tr>')
    return head + '<table style="border-collapse:collapse">' + "".join(body) + "</table>"
```

- [ ] **Шаг 5: `stand/views/spellings.py`**

```python
import math

import streamlit as st

from analytics import queries as q
from charts.common import bar_h
from labels import ru
from ui import data, filters, theme
from ui.cards import card_html

KINDS = {"teacher": "Преподаватели", "discipline": "Дисциплины", "room": "Аудитории",
         "group": "Группы", "lesson_type": "Типы занятий"}
SOURCES = ["словарь", "словарь?", "правило", "как есть", "разбор"]
PER_PAGE = 30

st.title("Словарь написаний")
st.caption("Одно и то же слово в расписании записано по-разному: с опечатками, сокращениями, лишними "
           "пробелами, капсом. Здесь каждое слово показано со всеми его написаниями, которые посчитаны вместе, "
           "и видно, чем каждое написание отличается от канона. «?» — решение под сомнением, "
           "«не проверено» — написания нет в проверенном словаре, канон выбрали автоправила.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
sp, audit = data.spellings(ctx.snapshot_id)
mode = theme.mode()

kind = st.segmented_control("Справочник", list(KINDS), default="teacher", required=True, format_func=KINDS.get)
summary = q.error_summary(sp, kind)
if summary.empty:
    st.info("В этом справочнике нет написаний, отличающихся от канона.")
else:
    left, right = st.columns([3, 2])
    left.plotly_chart(bar_h(summary, "error_kind", "uses", "Занятий с ошибкой в написании, по видам",
                            "занятий", mode), width="stretch")
    right.dataframe(ru(summary), hide_index=True, width="stretch")

c1, c2, c3 = st.columns([2, 2, 3])
kinds = c1.multiselect("Вид ошибки", list(summary["error_kind"]))
sources = c2.multiselect("Источник канона", SOURCES)
query = c3.text_input("Поиск по слову")
singles = st.checkbox("Показывать каноны с одним написанием", value=False)
cards = q.spelling_cards(sp, kind, tuple(kinds), tuple(sources), query, singles)

st.markdown(f'Подсветка разницы: <span style="text-decoration:line-through">лишнее</span> · '
            f'<span style="text-decoration:underline">[недостаёт]</span> · <b>заменено</b> · ␣ — пробел',
            unsafe_allow_html=True)
canons = list(dict.fromkeys(cards["canonical"]))
if not canons:
    st.info("Под выбранные фильтры не подходит ни одно слово.")
else:
    pages = math.ceil(len(canons) / PER_PAGE)
    page = st.number_input(f"Страница (всего {pages})", min_value=1, max_value=pages, value=1) if pages > 1 else 1
    for canon in canons[(page - 1) * PER_PAGE: page * PER_PAGE]:
        rows = cards[cards["canonical"] == canon]
        title = canon.replace("|", " · ") if kind == "room" else canon
        with st.container(border=True):
            st.markdown(card_html(title, rows, mode), unsafe_allow_html=True)

st.subheader("Насколько можно верить автоправилам")
st.caption("Автоправила прогнаны на проверенных написаниях так, будто словаря нет, и сравнены с ручными "
           "решениями по парам написаний. Ложная склейка — правила объединили то, что человек разделил.")
audit_view = audit.assign(kind_label=audit["kind"].map(KINDS)).drop(columns=["kind"])
st.dataframe(ru(audit_view[["kind_label", "tp", "fp", "fn", "precision", "recall"]]), hide_index=True, width="stretch")

st.subheader("Все написания")
table = sp[sp["kind"] == kind].drop(columns=["kind", "score"])
st.dataframe(ru(table), hide_index=True, width="stretch")
st.download_button("Скачать CSV", table.to_csv(index=False).encode("utf-8"),
                   file_name=f"spellings_{kind}.csv", mime="text/csv")
```

- [ ] **Шаг 6: Навигация в `stand/app.py`**

После строки страницы «Качество данных»:

```python
    st.Page("views/spellings.py", title="Словарь написаний", icon="🔤"),
```

В `tests/test_smoke.py` и `tests/test_demo_snapshot.py` в списке `PAGES` после `"quality"` добавить `"spellings"`.

- [ ] **Шаг 7: Запустить**

Run: `.venv/bin/python -m pytest tests/test_analytics.py tests/test_cards.py tests/test_smoke.py -q`
Expected: PASS.

- [ ] **Шаг 8: Посмотреть страницу глазами**

Запустить стенд (`.venv/bin/streamlit run stand/app.py`), открыть «Словарь написаний» на демо-снапшоте, в светлой и тёмной теме: карточки «Торопова В.В.», «Безопасность жизнедеятельности», аудитория «С-305а»; фильтр «Источник: словарь?»; поиск «Березкин». Проверить: подсветка разницы читается, пробелы видны как «␣», подсказка с примечанием появляется при наведении на строку, страница не тормозит (>1 с на перерисовку — разбить карточки или уменьшить `PER_PAGE`).

- [ ] **Шаг 9: Коммит**

```bash
git add stand/analytics/queries.py stand/ui/cards.py stand/views/spellings.py stand/app.py tests/test_analytics.py tests/test_cards.py tests/test_smoke.py tests/test_demo_snapshot.py
git commit -m "Страница «Словарь написаний»: карточки канон → написания с подсветкой разницы"
```

---

### Задача 13: Пороги на демо-снапшоте и документация

**Файлы:**
- Изменить: `tests/test_demo_snapshot.py`, `tests/test_clean_corpus.py`
- Изменить: `docs/specs/2026-10-07-raspisanie-2-0-design.md` (разделы «Нормализация», «Флаги качества», «Страницы стенда», «Структура репозитория», «Тестирование»)
- Изменить: `README.md` (список страниц, словарь)

- [ ] **Шаг 1: Замерить**

```bash
.venv/bin/python - <<'EOF'
import sys, time, tempfile
sys.path.insert(0, "stand")
from pathlib import Path
from etl.load import connect, load_snapshot
from etl.clean import clean, UNKNOWN
db = Path(tempfile.mkdtemp()) / "t.db"
conn = connect(db)
t = time.monotonic(); load_snapshot(conn, sorted(Path("data/snapshots").glob("*.json"))[-1]); print("загрузка, с:", round(time.monotonic() - t, 1))
print("покрытие:", conn.execute("SELECT AVG(has_type), AVG(has_discipline), AVG(has_teacher), AVG(has_room), AVG(needs_review) FROM quality").fetchone())
print("сверка:", conn.execute("SELECT kind, tp, fp, fn FROM rule_audit").fetchall())
corpus = Path("tests/fixtures/subjects_corpus.txt").read_text().splitlines()
ls = [l for r in corpus for l in clean(r).lessons]
for name, f in [("тип", lambda l: l.lesson_type != UNKNOWN), ("дисциплина", lambda l: bool(l.discipline)),
                ("преподаватель", lambda l: bool(l.teachers)), ("аудитория", lambda l: bool(l.rooms))]:
    print(name, round(100 * sum(map(f, ls)) / len(ls), 2))
EOF
```

Записать вывод — он нужен в шагах 2–4.

- [ ] **Шаг 2: Пороги**

- `tests/test_clean_corpus.py`: `THRESHOLDS` = замер шага 1 минус 1 п.п. (округлить вниз до десятых). Пороги не должны опускаться ниже прежних (`96.1, 97.4, 96.7, 94.6`); если опустились — это регрессия разбора, найти её до продолжения.
- `tests/test_demo_snapshot.py`: в `test_demo_snapshot_loads_with_reasonable_quality` время загрузки по-прежнему `< 30` с; доля `has_room` — порог по замеру минус 0.01; добавить сверку правил:

```python
    audit = dict((k, (tp, fp, fn)) for k, tp, fp, fn in conn.execute("SELECT kind, tp, fp, fn FROM rule_audit"))
    for kind, (min_precision, min_recall) in AUDIT_FLOORS.items():
        tp, fp, fn = audit[kind]
        assert tp / (tp + fp) >= min_precision and tp / (tp + fn) >= min_recall, (kind, audit[kind])
```

где `AUDIT_FLOORS = {"discipline": (p − 0.01, r − 0.01), "teacher": (p − 0.01, r − 0.01)}` — значения точности и полноты из замера шага 1 минус 0.01, записанные числами (например `(0.93, 0.71)`), с комментарием «замер 2026-10-07 минус 1 п.п.».

Run: `.venv/bin/python -m pytest -q`
Expected: PASS всех тестов.

- [ ] **Шаг 3: Основная спека**

В `docs/specs/2026-10-07-raspisanie-2-0-design.md`:
- «Нормализация»: первым абзацем — порядок «словарь → автоправила → как есть» со ссылкой на `2026-10-07-slovar-napisanij-design.md`; заменить числа «2162 варианта → 1249 дисциплин, 262 fuzzy-склейки» и «676 вариантов → 543 преподавателя» на итог после словаря (из `SELECT kind, COUNT(DISTINCT canonical) FROM spellings GROUP BY kind`); в описании правил преподавателей — правила с общей дисциплиной.
- «Флаги качества»: строка `unverified_name` — «дисциплина или преподаватель с источником `правило` или `как есть`»; `discipline_fuzzy` — «дисциплина склеена автоправилом (не словарём)».
- «Страницы стенда»: восьмая страница «Словарь написаний»; у «Качества данных» убрать «склейки написаний».
- «Структура репозитория»: `etl/dictionary.py`, `etl/dictionary/*.csv`, `etl/canon.py`, `etl/variants.py`, `etl/audit.py`, `ui/cards.py`, `views/spellings.py`.
- «Модель данных»: `spellings`, `rule_audit` вместо `merges`; `PRAGMA user_version`.
- «Тестирование»: новые файлы тестов; число тестов — по факту `pytest -q`.

- [ ] **Шаг 4: README**

В `README.md`: в списке страниц — восемь страниц, «Словарь написаний» с одной фразой о назначении; раздел «Словарь написаний» — где лежит (`stand/etl/dictionary/`), что делать с «не проверено» (ссылка на `stand/etl/dictionary/README.md`); упоминание, что при обновлении стенда БД пересоздаётся автоматически и снапшоты перечитываются.

- [ ] **Шаг 5: Проверка в Docker**

Run: `docker compose up --build -d && sleep 20 && curl -fsS http://localhost:8501/_stcore/health && docker compose logs stand | tail -20`
Expected: `ok`; в логах нет `Traceback`; стенд открывается, «Словарь написаний» в навигации. Остановить: `docker compose down`.

- [ ] **Шаг 6: Коммит**

```bash
git add tests/test_demo_snapshot.py tests/test_clean_corpus.py docs/specs/2026-10-07-raspisanie-2-0-design.md README.md
git commit -m "Пороги по замеру после словаря; спека стенда и README"
```
