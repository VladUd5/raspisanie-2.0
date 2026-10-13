"""Человекочитаемые названия для slug-ов, которые отдаёт парсер."""
import re

INSTITUTES = {
    "institut-agrobiznesa": "Институт агробизнеса",
    "institut-genetiki-i-agronomii": "Институт генетики и агрономии",
    "institut-injenerii-i-robototexniki": "Институт инженерии и робототехники",
    "institut-biotexnologii": "Институт биотехнологии",
    "institut-veterinarnoi-mediciny-i-farmacii": "Институт ветеринарной медицины и фармации",
}
FORMS = {
    "ochnaya-forma-obucheniya": "Очная",
    "zaochnaya-forma-obucheniya": "Заочная",
    "ochno-zaochnaya-forma-obucheniya": "Очно-заочная",
}
# Пара делится пополам: верхняя половина ячейки — верхняя неделя, нижняя — нижняя.
# В JSON парсера они называются numerator/denominator (числитель/знаменатель).
WEEK_TYPES = {"both": "обе недели", "numerator": "верхняя неделя", "denominator": "нижняя неделя"}
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
SHORT_DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
# Звонки: начало пары → её номер. Время, которого здесь нет, показывается без номера.
PAIRS = {"08:30": 1, "10:10": 2, "12:00": 3, "13:40": 4, "15:20": 5, "17:00": 6, "18:40": 7}


def building_label(slug: str) -> str:
    m = re.fullmatch(r"uk(\d+)", slug or "")
    return f"УК{m.group(1)}" if m else (slug or "—")


def institute_label(slug: str) -> str:
    return INSTITUTES.get(slug, slug or "—")


def form_label(slug: str) -> str:
    return FORMS.get(slug, slug or "—")

COLUMNS = {
    "teacher": "Преподаватель", "lessons": "Занятий в неделю",
    "disciplines": "Дисциплин", "groups": "Групп", "rooms": "Аудитории", "room_label": "Аудитория",
    "room_building": "Корпус аудитории", "room": "Номер", "discipline": "Дисциплина", "teachers": "Преподаватели",
    "lesson_type": "Тип занятия", "day": "День", "date": "Дата", "session_week": "Неделя сессии", "time_from": "Начало", "time_to": "Конец",
    "week_type": "Неделя", "institute": "Институт", "study_form": "Форма обучения", "group_name": "Группа",
    "cell_building": "Корпус", "subgroup": "Подгруппа", "subject_raw": "Исходный текст ячейки",
    "lessons_in_cell": "Занятий в ячейке", "kind": "Что", "alias": "Вариант написания",
    "canonical": "Каноническое название", "score": "Похожесть", "field": "Поле", "share": "Доля, %",
    "events": "Занятий в слоте", "count": "Занятий", "collected_at": "Собран", "source_url": "Источник",
    "file_name": "Файл", "groups_cnt": "Групп", "cells_cnt": "Ячеек", "lessons_cnt": "Занятий после разбора",
    "service_cnt": "Служебных строк",
    "spelling": "Написание", "source": "Источник", "confidence": "Уверенность", "error_kinds": "Вид ошибки",
    "error_kind": "Вид ошибки", "note": "Примечание", "uses": "Занятий", "spellings": "Написаний",
    "pairs": "Пар в неделю", "building": "Корпус", "slots": "Слотов в неделю", "busy": "Занято пар",
    "occupancy": "Занято, %",
    "tp": "Верных склеек", "fp": "Ложных склеек", "fn": "Пропущенных склеек",
    "precision": "Точность, %", "recall": "Полнота, %", "kind_label": "Справочник",
}


# Академический час — 45 минут: пара (1.5 астрономического часа) — 2 ак. часа.
HOURS = {True: "ак. часов", False: "астр. часов"}


def hours_label(academic: bool) -> str:
    """Заголовок столбца hours: «Ак. часов в неделю» / «Астр. часов в неделю»."""
    return f"{HOURS[academic].capitalize()} в неделю"


def ru(df, academic: bool = True):
    """Переименовать колонки DataFrame для показа пользователю. academic — в каких часах
    посчитан столбец hours (как в фильтре «Часы»)."""
    return df.rename(columns={**COLUMNS, "hours": hours_label(academic)})
