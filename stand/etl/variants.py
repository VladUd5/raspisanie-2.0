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


def _noseparator(s: str) -> str:
    """Без пробелов и дефисов: «Б-ЗТ 301» / «Б-ЗТ-301» — разница в разделителе."""
    return re.sub(r"[\s\-]+", "", s)


def _subsequence(short: str, long_: str) -> bool:
    it = iter(long_)
    return all(ch in it for ch in short)


def _is_abbrev(s: str, c: str) -> bool:
    """Каждое слово написания — начало очередного слова канона («жизнедеят.» / «жизнедеятельности»),
    и хотя бы одно слово действительно короче своего («нормативной и технической» — не сокращение)."""
    words, i, shortened = _TOKEN.findall(c), 0, False
    for t in _TOKEN.findall(s):
        while i < len(words) and not words[i].startswith(t):
            i += 1
        if i == len(words):
            return False
        shortened |= len(t) < len(words[i])
        i += 1
    return shortened


def _text_kind(s: str, c: str) -> str:
    sk, ck = s.strip(" .,"), c.strip(" .,")
    if ("." in s or "-" in s) and _is_abbrev(s, c):
        return "сокращение"
    # обрезано: начало или конец канона; начало могло оборваться на 1–2 буквы («ек.» / «лекция»)
    if sk and (ck.startswith(sk) or ck.endswith(sk) or 0 < ck.find(sk) <= 2):
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


def _acronym_of(spelling: str, canonical: str) -> bool:
    """«БЖД» — первые буквы частей «Безопасность жизнедеятельности»."""
    s = spelling.strip()
    return (bool(_ACRONYM.fullmatch(s)) and " " in canonical
            and s[0].casefold() == canonical[0].casefold()
            and _subsequence(s.casefold(), _yo(canonical).casefold()))


def classify(kind: str, spelling: str, canonical: str) -> list[str]:
    if canonical == NOT_DISCIPLINE:
        return ["не дисциплина"]
    if spelling == canonical:
        return []
    if kind != "teacher" and _acronym_of(spelling, canonical):
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
    if _nospace(s) == _nospace(c) or (kind in ("group", "room") and _noseparator(s) == _noseparator(c)):
        return kinds + ["пробел"]
    if kind == "teacher":
        # латиница и ё уже учтены выше — сравниваем фамилии без них, но с исходным регистром
        return kinds + _teacher_kind(_yo(spelling.translate(_LATIN)), _yo(canonical.translate(_LATIN)))
    if kind == "discipline":
        extra = [t for t in _NOTE.findall(s) if t not in c]
        if extra:
            kinds.append("лишняя пометка")
            for t in extra:
                s = s.replace(t, " ")
            s = " ".join(s.split())
            if s == c or _nospace(s) == _nospace(c):
                return kinds
    return kinds + [_text_kind(s, c)]


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
