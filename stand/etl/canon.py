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
