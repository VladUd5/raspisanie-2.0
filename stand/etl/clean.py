"""Разбор строки subject (текст одной ячейки PDF) на занятия и их поля.

Конвейер описан в спеке, раздел «Правила очистки». Функция clean() никогда
не бросает исключение: всё, что не удалось разобрать, остаётся пустым и
помечается needs_review.
"""
import re
from dataclasses import dataclass, field

from etl.locations import ADJACENT, LOCATIONS

UNKNOWN = "не определён"

_L = "А-ЯЁа-яё"            # кириллическая буква
_ROOM = "\x01"             # метка: здесь была аудитория или корпус
_TEACHER = "\x02"          # метка: здесь был преподаватель
_PH = "\x03"               # обрамление плейсхолдера места из справочника


@dataclass
class ParsedLesson:
    lesson_type: str = UNKNOWN
    discipline: str | None = None
    teachers: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    building: str | None = None
    subgroup: int | None = None

    @property
    def needs_review(self) -> bool:
        return not (self.discipline and self.teachers and self.rooms)


@dataclass
class ParsedCell:
    is_service: bool = False
    lessons: list[ParsedLesson] = field(default_factory=list)
    truncated: bool = False

    @property
    def needs_review(self) -> bool:
        return self.truncated or any(lesson.needs_review for lesson in self.lessons)


# --- 1. предобработка ---------------------------------------------------------
_SPACED = re.compile(rf"(?<!\S)(?:[{_L}] ){{2,}}[{_L}](?!\S)")

# --- 2. служебные фрагменты ---------------------------------------------------
_SERVICE = re.compile(
    r"переход\s+на\s+УК\s*№?\s*\d|переезд(?:\s+на\s+УК\s*№?\s*\d)?|(?:единый\s+)?кураторский\s+час|\*",
    re.I,
)

# --- 3. аннотации часов и звания ----------------------------------------------
_HOURS = re.compile(
    r"\d+\s*лек\.?\s*\+\s*\d+\s*пр(?:\.?\s*з)?\.?"   # 4 лек. + 5 пр.
    r"|\(\s*\d*\s*(?:лек|пр)[^)]*\)"               # (5 лек.), (пр.з.)
    r"|\(\s*\d+\s*\)"                              # (28)
    r"|(?<![А-ЯЁа-яё])с\s+\d{1,2}[.:]\d{2}",            # ЗАЧЕТ с 13.40
    re.I,
)
_TITLES = re.compile(
    rf"(?<![{_L}])(?:ст\.\s*преп\.?|ст\.\s*пр\.?|доцент(?![{_L}])|профессор(?![{_L}])"
    rf"|доц(?:\.|(?![{_L}]))|проф(?:\.|(?![{_L}]))|преп\.|асс\.)",
    re.I,
)

# --- 5. маркеры типа занятия --------------------------------------------------
_END = rf"(?:\s?\.|(?![{_L}]))"        # точка или конец слова
_MARKERS: list[tuple[str, str]] = [
    ("практика", rf"(?i:пр)\s?\.?\s?(?i:з){_END}"),
    ("лабораторная", rf"(?i:лаб)\s?\.?\s?(?i:з){_END}"),
    ("лабораторная", rf"(?i:лб)\s?\.?\s?(?i:з){_END}"),
    ("лекция", rf"(?i:лек){_END}"),
    ("практика", r"(?i:пр)\s?\.(?![а-яё])"),          # но не «пр.ва»
    ("лабораторная", r"(?i:лаб)\s?\.(?![а-яё])"),     # но не «Лаб.диагност.»
    ("семинар", rf"(?i:сем){_END}"),
    ("консультация", rf"(?i:конс){_END}"),
    ("зачёт", rf"(?i:зач[её]т)(?![{_L}])"),
    ("экзамен", rf"(?i:экзамен)(?![{_L}])"),
]
_ONLY_AT_START = {"семинар", "консультация"}   # «сем. посевов» в середине — не семинар
_MARKER = re.compile(
    rf"(?<![{_L}A-Za-z0-9(.\-])(?:"
    + "|".join(f"(?P<m{i}>{rx})" for i, (_, rx) in enumerate(_MARKERS))
    + ")"
)

# --- 6. поля занятия ----------------------------------------------------------
_SUBGROUP = re.compile(r"(?<!\d)(\d)\s*(?:-?\s*я\s*)?(?:п/г|подгрупп[аы])", re.I)
_BUILDING_UK = re.compile(rf"\(?(?<![{_L}])УК\s*№?\s*(\d)\)?")
_BUILDING_NAMED = re.compile(r"(?:[А-ЯЁ]{3,},?\s*)?корпус\s+([А-ЯЁ]{2,}),?")
_ROOMS = re.compile(
    rf"{_PH}(?P<ph>\d+){_PH}"
    rf"|(?<![{_L}])(?i:ауд)\s*\.?\s*(?P<named>Большая|Малая)"
    rf"|(?<![{_L}])(?i:ауд)\s*\.?\s*(?P<aud>\d{{1,4}})(?:\s?(?P<audl>[аб])(?![{_L}]))?\.?"
    rf"|(?<![\w.\-])(?P<cl>[СCХX])\s?-\s?(?P<c>\d{{2,4}})"
    rf"|(?<![\w:\-])(?<!\d[.:])(?P<num>\d{{3,4}})(?!\d)(?:\s?(?P<numl>[аб])(?![{_L}]))?(?![.:]\d)"
    rf"|(?<![\w:\-(])(?<!\d[.:])(?P<num2>\d{{2}})(?=[\s.]*$)"      # «Демин Е.Е.33», «… В.В. 40» в конце
)
_SURNAME = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
_FULL_NAME = re.compile(
    rf"(?<![{_L}])(?P<s>{_SURNAME})\s*"
    rf"(?:(?P<i1>[А-ЯЁ])\s*\.+\s*(?P<i2>[А-ЯЁ])\s*\.*"      # И.О. / И. О. / И.О
    rf"|(?P<j1>[А-ЯЁ])(?P<j2>[А-ЯЁ])\s*\."                    # ИО.
    rf"|(?P<k1>[А-ЯЁ])\s(?P<k2>[А-ЯЁ])\.)"                    # И О.
)
_CANDIDATE = re.compile(rf"(?<![{_L}])[А-ЯЁ][а-яё]{{2,}}(?:-[А-ЯЁ][а-яё]+)?(?![{_L}])")
_FIRST_WORD = re.compile(rf"[{_L}A-Za-z]+")
# Слова с заглавной буквы, которые встречаются в конце названий дисциплин.
_NOT_SURNAMES = {"России", "Российской", "Земли", "Европы", "Азии", "Сибири", "Поволжья", "Мира"}


def clean(subject: str) -> ParsedCell:
    try:
        return _clean(subject)
    except Exception:  # noqa: BLE001 — clean не должен ронять ETL
        return ParsedCell(lessons=[ParsedLesson()], truncated=True)


def _clean(subject: str) -> ParsedCell:
    s = " ".join((subject or "").split())
    s = _SPACED.sub(lambda m: m.group(0).replace(" ", ""), s)

    s = _SERVICE.sub(" ", s)
    if not re.search(rf"[{_L}A-Za-z]", s):
        return ParsedCell(is_service=True)

    truncated = bool(re.match(rf"\s*[а-яё]", s)) and not _MARKER.match(s.lstrip())

    s = _HOURS.sub(" ", s)
    s = _TITLES.sub(" ", s)
    s, places = _extract_places(s)

    lessons = [_parse_lesson(t, text, places) for t, text in _split(s)]
    return ParsedCell(lessons=lessons, truncated=truncated)


def _extract_places(s: str) -> tuple[str, list[tuple[str, str | None]]]:
    places: list[tuple[str, str | None]] = []
    for loc in LOCATIONS:
        def repl(m: re.Match, loc=loc) -> str:
            places.append((m.expand(loc.room), loc.building))
            return f" {_PH}{len(places) - 1}{_PH} "
        s = loc.pattern.sub(repl, s)
    return s, places


def _marker_type(m: re.Match) -> str:
    return next(_MARKERS[i][0] for i in range(len(_MARKERS)) if m.group(f"m{i}") is not None)


def _split(s: str) -> list[tuple[str, str]]:
    matches = [
        m for m in _MARKER.finditer(s)
        if _marker_type(m) not in _ONLY_AT_START or not s[: m.start()].strip()
    ]
    if not matches:
        return [(UNKNOWN, s)]
    parts = [
        (_marker_type(m), s[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(s)])
        for i, m in enumerate(matches)
    ]
    parts = [(t, text) for t, text in parts if re.search(rf"[{_L}\d{_PH}]", text)] or [(parts[-1][0], "")]
    prefix = s[: matches[0].start()]
    if re.search(rf"[{_L}]", prefix):
        if _FULL_NAME.search(prefix) or _ROOMS.search(prefix):
            parts.insert(0, (UNKNOWN, prefix))          # перед маркером целое занятие
        else:
            parts[0] = (parts[0][0], prefix + " " + parts[0][1])   # «2-я подгруппа лаб. з. …»
    return parts


def _parse_lesson(lesson_type: str, text: str, places: list[tuple[str, str | None]]) -> ParsedLesson:
    lesson = ParsedLesson(lesson_type=lesson_type)

    m = _SUBGROUP.search(text)
    if m:
        lesson.subgroup = int(m.group(1))
        text = text[: m.start()] + " " + text[m.end():]

    def building_uk(m: re.Match) -> str:
        lesson.building = f"УК{m.group(1)}"
        return f" {_ROOM} "

    def building_named(m: re.Match) -> str:
        lesson.building = m.group(1)
        return f" {_ROOM} "

    text = _BUILDING_UK.sub(building_uk, text)
    text = _BUILDING_NAMED.sub(building_named, text)

    rooms: list[str] = []

    def room(m: re.Match) -> str:
        if m.group("ph") is not None:
            name, building = places[int(m.group("ph"))]
            rooms.append(name)
            if building:
                lesson.building = building
        elif m.group("named"):
            rooms.append(m.group("named"))
        elif m.group("aud"):
            rooms.append(m.group("aud") + (m.group("audl") or ""))
        elif m.group("c"):
            letter = {"C": "С", "X": "Х"}.get(m.group("cl"), m.group("cl"))   # латиница → кириллица
            rooms.append(f"{letter}-{m.group('c')}")
        elif m.group("num2"):
            rooms.append(m.group("num2"))
        else:
            rooms.append(m.group("num") + (m.group("numl") or ""))
        return f" {_ROOM} "

    text = _ROOMS.sub(room, text)

    teachers: list[tuple[int, str]] = []

    def full_name(m: re.Match) -> str:
        i1, i2 = next((m.group(a), m.group(b)) for a, b in (("i1", "i2"), ("j1", "j2"), ("k1", "k2")) if m.group(a))
        teachers.append((m.start(), f"{m.group('s')} {i1}.{i2}."))
        return _TEACHER + " " * (m.end() - m.start() - 1)   # длина сохраняется: позиции нужны ниже

    text = _FULL_NAME.sub(full_name, text)
    text, surnames = _extract_surnames(text)
    teachers += surnames

    lesson.rooms = _unique(rooms)
    lesson.teachers = _unique(name for _, name in sorted(teachers))
    lesson.discipline = _discipline(text)
    return lesson


def _extract_surnames(text: str) -> tuple[str, list[tuple[int, str]]]:
    """Фамилии без инициалов: в хвосте строки, перед аудиторией, концом строки
    или через запятую перед другим преподавателем. Первое слово — всегда дисциплина."""
    first = _FIRST_WORD.search(text)
    first_start = first.start() if first else -1
    found: list[tuple[int, str]] = []
    accepted_starts: set[int] = set()
    for m in reversed(list(_CANDIDATE.finditer(text))):
        word = m.group(0)
        if m.start() == first_start or word in _NOT_SURNAMES:
            continue
        right = text[m.end():].lstrip()
        ok = not right.strip(" .,;") or right.startswith(_ROOM)
        if not ok and right.startswith(","):
            after = right[1:].lstrip()
            pos = len(text) - len(after)
            ok = after.startswith((_ROOM, _TEACHER)) or pos in accepted_starts
        if ok:
            found.append((m.start(), word))
            accepted_starts.add(m.start())
    for start, word in found:
        text = text[:start] + _TEACHER + " " * (len(word) - 1) + text[start + len(word):]
    return text, found


def _discipline(text: str) -> str | None:
    cut = min((i for i in (text.find(_ROOM), text.find(_TEACHER)) if i >= 0), default=len(text))
    d = " ".join(text[:cut].replace(_PH, " ").split())
    d = d.lstrip(" .,;:/-").rstrip(" ,;:/-")
    repeated = re.fullmatch(r"(.+?)(?:\s+\1)+", d)
    if repeated:
        d = repeated.group(1)
    return d or None


def _unique(items) -> list[str]:
    return list(dict.fromkeys(items))
