import math

import streamlit as st

from analytics import queries as q
from charts.common import bar_h
from labels import ru
from ui import data, filters, theme
from ui.cards import card_html, card_title, legend_html

KINDS = {"teacher": "Преподаватели", "discipline": "Дисциплины", "room": "Аудитории",
         "group": "Группы", "lesson_type": "Типы занятий"}
SOURCES = ["словарь", "словарь?", "правило", "как есть", "разбор"]
PER_PAGE = 30

st.title("Словарь написаний")
st.caption("Одно и то же слово в расписании записано по-разному: с опечатками, сокращениями, лишними "
           "пробелами, капсом. Здесь каждое слово показано со всеми его написаниями, которые посчитаны вместе, "
           "и видно, чем каждое написание отличается от канона. «?» — решение под сомнением, "
           "«не проверено» — написания нет в проверенном словаре, канон выбрали автоправила. "
           "Фильтры боковой панели здесь не действуют: словарь строится по всему снапшоту.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
sp, audit = data.spellings(ctx.snapshot_id)
mode = theme.mode()

kind = st.segmented_control("Справочник", list(KINDS), default="teacher", required=True, format_func=KINDS.get)
summary = q.error_summary(sp, kind)
if summary.empty:
    st.info("В этом справочнике нет написаний, отличающихся от канона.")
else:
    left, right = st.columns([3, 2])
    left.plotly_chart(bar_h(summary, "error_kind", "uses", "Занятий с ошибкой в написании, по видам",
                            "занятий", mode), width="stretch")
    right.dataframe(ru(summary), hide_index=True, width="stretch")

c1, c2, c3 = st.columns([2, 2, 3])
kinds = c1.multiselect("Вид ошибки", list(summary["error_kind"]), placeholder="все")
sources = c2.multiselect("Источник канона", SOURCES, placeholder="все")
query = c3.text_input("Поиск по слову")
singles = st.checkbox("Показывать и слова без разночтений (одно написание, совпадающее с каноном)", value=False)
cards = q.spelling_cards(sp, kind, tuple(kinds), tuple(sources), query, singles)

st.markdown(legend_html(mode), unsafe_allow_html=True)
canons = list(dict.fromkeys(cards["canonical"]))
if not canons:
    st.info("Под выбранные фильтры не подходит ни одно слово.")
else:
    pages = math.ceil(len(canons) / PER_PAGE)
    page = st.number_input(f"Страница (всего {pages})", min_value=1, max_value=pages, value=1) if pages > 1 else 1
    for canon in canons[(page - 1) * PER_PAGE: page * PER_PAGE]:
        rows = cards[cards["canonical"] == canon]
        with st.container(border=True):
            st.markdown(card_html(card_title(kind, canon), rows, mode), unsafe_allow_html=True)

st.subheader("Насколько можно верить автоправилам")
st.caption("Автоправила прогнаны на проверенных написаниях так, будто словаря нет, и сравнены с ручными "
           "решениями по парам написаний. Ложная склейка — правила объединили то, что человек разделил.")
audit_view = audit.assign(kind_label=audit["kind"].map(KINDS))
st.dataframe(ru(audit_view[["kind_label", "tp", "fp", "fn", "precision", "recall"]]), hide_index=True, width="stretch")

st.subheader("Все написания")
table = sp[sp["kind"] == kind].drop(columns=["kind", "score"])
st.dataframe(ru(table), hide_index=True, width="stretch")
st.download_button("Скачать CSV", table.to_csv(index=False).encode("utf-8"),
                   file_name=f"spellings_{kind}.csv", mime="text/csv")
