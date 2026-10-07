"""Управление рейтингом на страницах: сколько показать и с какого края.

Внизу рейтинга — выбросы: преподаватель или дисциплина с одним-двумя занятиями
часто оказывается непроверенным написанием или обрывком ячейки."""
import streamlit as st

ORDER = {"top": "Самые загруженные", "bottom": "Наименее загруженные"}


def controls(key: str, noun: str, max_n: int, default: int) -> tuple[int, bool]:
    """(сколько показать, по возрастанию). key — имя страницы: виджеты не путаются между страницами."""
    left, right = st.columns([2, 3])
    order = left.segmented_control("Порядок", list(ORDER), format_func=ORDER.get, default="top",
                                   required=True, key=f"{key}_order")
    n = right.slider(f"Сколько {noun} показать на графике", 5, max_n, default, key=f"{key}_n")
    return n, order == "bottom"


def title(n: int, ascending: bool, what: str, measure: str) -> str:
    """«Топ-20 преподавателей по часам в неделю» / «20 наименее загруженных преподавателей …»."""
    return f"{n} наименее загруженных {what} по {measure}" if ascending else f"Топ-{n} {what} по {measure}"
