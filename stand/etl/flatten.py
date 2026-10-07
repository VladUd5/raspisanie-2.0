"""Разворот вложенного JSON парсера в плоский список ячеек расписания."""
from dataclasses import dataclass

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
                            ))
    return cells
