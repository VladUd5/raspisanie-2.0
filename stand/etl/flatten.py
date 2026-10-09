"""Разворот вложенного JSON парсера в плоский список ячеек расписания."""
import re
from dataclasses import dataclass
from datetime import date, timedelta

from labels import DAYS, building_label, form_label, institute_label

_WEEK = {None: "both", "none": "both", "numerator": "numerator", "denominator": "denominator"}


@dataclass(frozen=True)
class RawCell:
    building: str
    institute: str
    study_form: str
    group_name: str
    day: str
    day_idx: int
    time_from: str
    time_to: str
    week_type: str
    subject_raw: str
    date: str = ""          # "YYYY-MM-DD" — у заочки, если дата есть в таблице
    source: str = ""        # имя PDF-файла; префикс — время загрузки на сайт

    @property
    def session_week(self) -> str:
        """Понедельник недели сессии (для датированных занятий заочки)."""
        if not self.date:
            return ""
        try:
            d = date.fromisoformat(self.date)
        except ValueError:
            return ""
        return (d - timedelta(days=d.weekday())).isoformat()

    @property
    def duration_h(self) -> float:
        return max(0.0, (_minutes(self.time_to) - _minutes(self.time_from)) / 60)


def _minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def flatten(buildings: list[dict] | None) -> list[RawCell]:
    """Каждое занятие каждой группы → RawCell. Отсутствующие списки считаются пустыми."""
    cells: list[RawCell] = []
    for b in buildings or []:
        for inst in b.get("institutes") or []:
            for form in inst.get("forms") or []:
                for group in form.get("groups") or []:
                    for day in (group.get("schedule") or {}).get("days") or []:
                        day_name = (day.get("name") or "").lower()
                        day_idx = DAYS.index(day_name) if day_name in DAYS else len(DAYS)
                        for lesson in day.get("lessons") or []:
                            cells.append(RawCell(
                                building=building_label(b.get("name", "")),
                                institute=institute_label(inst.get("name", "")),
                                study_form=form_label(form.get("name", "")),
                                group_name=group.get("name", ""),
                                day=day_name,
                                day_idx=day_idx,
                                time_from=lesson.get("time_from", ""),
                                time_to=lesson.get("time_to", ""),
                                week_type=_WEEK.get(lesson.get("week"), "both"),
                                subject_raw=lesson.get("subject", ""),
                                date=day.get("date") or "",
                                source=group.get("source") or "",
                            ))
    return cells


def _uploaded(source: str) -> tuple[int, str]:
    """Порядок версий файла: числовой префикс имени — время загрузки на сайт."""
    m = re.match(r"(\d+)_", source or "")
    return (int(m.group(1)) if m else 0, source or "")


def drop_superseded(cells: list[RawCell]) -> tuple[list[RawCell], int]:
    """Заочники: одну неделю сессии группы бывает выложено несколькими файлами (исправленные
    версии). Для каждой (группа, неделя) остаются ячейки только из самого свежего файла.
    Ячейки без даты не трогаются. → (оставшиеся ячейки, сколько отброшено)."""
    newest: dict[tuple, tuple[int, str]] = {}
    for c in cells:
        if c.session_week:
            key = (c.building, c.institute, c.study_form, c.group_name, c.session_week)
            newest[key] = max(newest.get(key, (-1, "")), _uploaded(c.source))
    kept = [c for c in cells if not c.session_week or
            _uploaded(c.source) == newest[(c.building, c.institute, c.study_form, c.group_name, c.session_week)]]
    return kept, len(cells) - len(kept)
