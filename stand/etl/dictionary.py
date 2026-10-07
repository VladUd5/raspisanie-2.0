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
                    raise DictionaryError(
                        f"{file.name}, строка {line}: канон «{canonical}» — не «Фамилия И.О.» и не фамилия")
                _put(d.teachers.setdefault(row["написание"], {}), row["дисциплина"],
                     _entry(row, canonical), file, line)
            elif name == "lesson_types":
                if canonical not in LESSON_TYPES:
                    raise DictionaryError(f"{file.name}, строка {line}: неизвестный тип занятия «{canonical}»")
                _put(d.lesson_types, row["написание"], _entry(row, canonical), file, line)
            else:
                _put(getattr(d, name), row["написание"], _entry(row, canonical), file, line)
    return d
