"""Нормализация: ключи сравнения, склейка дисциплин и преподавателей."""
import re
from collections import Counter
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

_EDGE_PUNCT = " .,;:/- "
DISCIPLINE_THRESHOLD = 80
SURNAME_MIN_LEN = 5


@dataclass(frozen=True)
class Merge:
    kind: str        # "discipline" | "teacher"
    alias: str
    canonical: str
    score: float


def disc_key(name: str) -> str:
    """Ключ сравнения дисциплин: регистр, ё/е, пробелы и пунктуация по краям не важны."""
    s = name.casefold().replace("ё", "е")
    s = " ".join(s.split())
    return s.strip(_EDGE_PUNCT)


def _is_caps(name: str) -> bool:
    letters = [c for c in name if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _abbreviations(name: str) -> int:
    """Сколько сокращений в названии: «физ.подготовка», «ГОС. РЕГУЛИР.», «хоз-ва»."""
    body = name.rstrip(" .")
    return len(re.findall(r"[А-ЯЁа-яё]\.", body)) + len(re.findall(r"[а-яё]-[а-яё]{1,3}\b", body))


def _sentence_case(name: str) -> str:
    """«ИННОВАЦИОННЫЙ МЕНЕДЖМЕНТ АПК» → «Инновационный менеджмент АПК»."""
    words = name.split()
    out = []
    for i, w in enumerate(words):
        letters = sum(c.isalpha() for c in w)
        if i > 0 and letters <= 3 and w.isupper():   # аббревиатуры: АПК, ПО, ЧС
            out.append(w)
        else:
            out.append(w.lower())
    s = " ".join(out)
    return s[:1].upper() + s[1:]


_WORD = re.compile(r"[а-яa-z]+")
LONG_WORD = 9


def _words(key: str) -> list[str]:
    return [w for w in _WORD.findall(key) if len(w) >= 3]


def _word_typo(a: str, b: str) -> bool:
    """Опечатка в слове: одна правка в слове от 4 букв; две — только в длинном
    слове (от 9 букв) с одинаковым началом. Иначе «геология»/«экология» и
    «почвоведение»/«правоведение» оказались бы «опечатками»."""
    if min(len(a), len(b)) < 4:
        return False
    d = Levenshtein.distance(a, b)
    return d <= 1 or (d == 2 and min(len(a), len(b)) >= LONG_WORD and a[:2] == b[:2])


def _counterpart(word: str, others: list[str]) -> bool:
    """У слова есть пара: совпадение, сокращение («технол.» / «технологии»),
    слипшиеся слова («безопасностьжизнедеятельности») или опечатка."""
    for o in others:
        short, long_ = sorted((word, o), key=len)
        if short == long_ or long_.startswith(short):
            return True
        if len(short) >= 5 and short in long_:
            return True
        if _word_typo(word, o):
            return True
    return False


def _can_merge(a: str, b: str) -> bool:
    """Запрет склейки разных дисциплин, похожих по буквам.

    - «органическая химия» ⊂ «неорганическая химия» — добавка, а не опечатка;
    - разные номера («Иностранный язык 1» / «2») — разные дисциплины;
    - у каждого слова от 3 букв должна быть пара в другом названии:
      «Общая биотехнология» и «Пищевая биотехнология» не склеиваются.
    """
    short, long_ = sorted((a, b), key=len)
    if short in long_:
        return False
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    wa, wb = _words(a), _words(b)
    return all(_counterpart(w, wb) for w in wa) and all(_counterpart(w, wa) for w in wb)


def cluster_disciplines(names: list[str]) -> tuple[dict[str, str], list[Merge]]:
    """Склеивает варианты написания дисциплин.

    Возвращает маппинг «исходное написание → каноническое название» и журнал
    склеек со score < 100. Канон кластера — вариант с наименьшим числом
    сокращений, затем не капсом, затем самый частый, затем самый длинный;
    капс приводится к виду предложения.
    """
    counts = Counter(names)
    key_counts: Counter[str] = Counter()
    for name, n in counts.items():
        key_counts[disc_key(name)] += n

    reps: list[str] = []                  # ключи-представители кластеров
    cluster_of: dict[str, str] = {}       # ключ → ключ-представитель
    score_of: dict[str, float] = {}
    for key, _ in key_counts.most_common():
        best = None
        if reps:
            for cand, score, _ in process.extract(key, reps, scorer=fuzz.ratio,
                                                  score_cutoff=DISCIPLINE_THRESHOLD, limit=5):
                if _can_merge(key, cand):
                    best = (cand, score)
                    break
        if best:
            cluster_of[key] = best[0]
            score_of[key] = best[1]
        else:
            reps.append(key)
            cluster_of[key] = key
            score_of[key] = 100.0

    variants: dict[str, Counter[str]] = {}
    for name, n in counts.items():
        variants.setdefault(cluster_of[disc_key(name)], Counter())[name] += n

    canonical_of_rep: dict[str, str] = {}
    for rep, vs in variants.items():
        # при равной частоте — более длинный вариант: опечатки чаще теряют буквы
        best = min(vs, key=lambda v: (_abbreviations(v), _is_caps(v), -vs[v], -len(v), v))
        canonical_of_rep[rep] = _sentence_case(best) if _is_caps(best) else best[:1].upper() + best[1:]

    mapping = {name: canonical_of_rep[cluster_of[disc_key(name)]] for name in counts}
    merges = [
        Merge("discipline", name, mapping[name], score_of[disc_key(name)])
        for name in counts
        if score_of[disc_key(name)] < 100
    ]
    return mapping, merges


_FULL = re.compile(r"^(?P<s>\S+) (?P<i>[А-ЯЁ]\.[А-ЯЁ]\.)$")


def _surname_key(s: str) -> str:
    return s.casefold().replace("ё", "е")


def _similar_surnames(a: str, b: str) -> bool:
    """Опечатка в фамилии: ровно одна правка, та же первая буква, то же окончание,
    длина от 5 букв.

    Первая буква защищает разных людей («Газизов»/«Азизов»), окончание — пары
    по роду («Иванов»/«Иванова»), длина — короткие фамилии («Ким»/«Кин»).
    """
    a, b = _surname_key(a), _surname_key(b)
    return (
        a != b
        and a[0] == b[0]
        and min(len(a), len(b)) >= SURNAME_MIN_LEN
        and a[-2:] == b[-2:]
        and Levenshtein.distance(a, b) <= 1
    )


def resolve_teachers(names: list[str]) -> tuple[dict[str, str], list[Merge]]:
    """Канонизирует преподавателей в пределах снапшота.

    1. Полные ФИО с одинаковыми инициалами и фамилиями, отличающимися одной
       опечаткой (_similar_surnames), склеиваются; канон — самый частый вариант.
    2. Фамилия без инициалов присоединяется к полному ФИО, если подходящее полное
       ФИО ровно одно (сначала точное совпадение фамилии, затем с одной опечаткой).
       Иначе остаётся как есть.
    """
    counts = Counter(names)
    full = [n for n in counts if _FULL.match(n)]
    bare = [n for n in counts if not _FULL.match(n)]
    mapping: dict[str, str] = {}
    merges: list[Merge] = []

    canon_full: list[str] = []
    for name in sorted(full, key=lambda n: (-counts[n], n)):
        m = _FULL.match(name)
        target = None
        for c in canon_full:
            cm = _FULL.match(c)
            if cm.group("i") != m.group("i"):
                continue
            if _surname_key(cm.group("s")) == _surname_key(m.group("s")):
                target = (c, 100.0)
            elif _similar_surnames(cm.group("s"), m.group("s")):
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

    by_surname: dict[str, list[str]] = {}
    for c in canon_full:
        by_surname.setdefault(_surname_key(_FULL.match(c).group("s")), []).append(c)

    for name in bare:
        exact = by_surname.get(_surname_key(name), [])
        if len(exact) == 1:
            mapping[name] = exact[0]
            continue
        if exact:                     # несколько полных ФИО с этой фамилией
            mapping[name] = name
            continue
        similar = [c for c in canon_full if _similar_surnames(_FULL.match(c).group("s"), name)]
        if len(similar) == 1:
            mapping[name] = similar[0]
            merges.append(Merge("teacher", name, similar[0], fuzz.ratio(_FULL.match(similar[0]).group("s"), name)))
        else:
            mapping[name] = name
    return mapping, merges


def is_surname_only(teacher: str) -> bool:
    return not _FULL.match(teacher)
