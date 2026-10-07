"""Нормализация: ключи сравнения, склейка дисциплин и преподавателей."""
import re
from collections import Counter
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from etl.variants import NOT_DISCIPLINE

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
    """Запрет склейки разных дисциплин, похожих по буквам.

    - «органическая химия» ⊂ «неорганическая химия» — добавка, а не опечатка;
    - разные номера («Иностранный язык 1» / «2») — разные дисциплины;
    - короткие аббревиатуры без точки должны совпадать («в ЛА» / «в ЛД»);
    - у каждого слова от 3 букв должна быть пара в другом названии:
      «Общая биотехнология» и «Пищевая биотехнология» не склеиваются.
    """
    short, long_ = sorted((a, b), key=len)
    if short in long_:
        return False
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return False
    if _short_tokens(a) != _short_tokens(b):
        return False
    wa, wb = _words(a), _words(b)
    return all(_counterpart(w, wb, known) for w in wa) and all(_counterpart(w, wa, known) for w in wb)


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
    самый длинный; капс приводится к виду предложения. Журнал — склейки со
    score < 100.
    """
    anchors = {n: c for n, c in (anchors or {}).items() if c != NOT_DISCIPLINE}
    known = known_words or set()
    counts = Counter(n for n in names if n not in anchors)
    key_counts: Counter[str] = Counter()
    for name, n in counts.items():
        key_counts[disc_key(name)] += n

    reps: list[str] = []                  # ключи-представители кластеров
    anchor_canon: dict[str, str] = {}
    for name, canon in anchors.items():
        k = disc_key(name)
        if k not in anchor_canon:
            anchor_canon[k] = canon
            reps.append(k)
    cluster_of: dict[str, str] = {k: k for k in anchor_canon}     # ключ → ключ-представитель
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
        # при равной частоте — более длинный вариант: опечатки чаще теряют буквы
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


def is_surname_only(teacher: str) -> bool:
    return not _FULL.match(teacher)

