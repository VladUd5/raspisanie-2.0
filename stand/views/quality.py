import streamlit as st

from analytics import queries as q
from charts.common import bar_h
from labels import WEEK_TYPES, ru
from ui import data, filters, theme

st.title("Качество данных")
st.caption("Что сделала стадия очистки: насколько полно разобраны ячейки PDF, какие строки отброшены, "
           "какие написания склеены и где разбор стоит проверить вручную.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
cells, service, merges = data.quality(ctx.snapshot_id)

shares = q.quality_shares(cells)
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(shares[shares["kind"] == "распознано"].iloc[::-1], "field", "share",
                        "Доля занятий с распознанным полем", "% занятий", theme.mode()), width="stretch")
right.dataframe(ru(shares), hide_index=True, width="stretch",
                column_config={"Доля, %": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100)})

st.subheader("Занятия, требующие проверки")
flags = st.multiselect("Показать занятия с флагами", list(q.FLAG_FIELDS), default=["needs_review"],
                       format_func=q.FLAG_FIELDS.get)
view = cells
for f in flags:
    view = view[view[f] == 1]
st.caption(f"Найдено: {len(view)}")
st.dataframe(ru(view[["institute", "group_name", "subject_raw", "lesson_type", "discipline", "teachers", "rooms",
                      "lessons_in_cell"]]), hide_index=True, width="stretch")

st.subheader("Наложения в расписании преподавателей")
st.caption("В один слот у преподавателя стоят разные занятия. Это ошибка исходного расписания или "
           "сессия заочников; в нагрузке такой слот считается не больше одной пары.")
lessons, teachers, _ = filters.filtered(ctx)
conflicts = q.teacher_conflicts(lessons, teachers)
conflicts["week_type"] = conflicts["week_type"].map(WEEK_TYPES)
st.dataframe(ru(conflicts), hide_index=True, width="stretch")

c1, c2 = st.columns(2)
with c1:
    st.subheader("Склейки написаний")
    kind = st.segmented_control("Что склеено", ["discipline", "teacher"], default="discipline", required=True,
                                format_func={"discipline": "Дисциплины", "teacher": "Преподаватели"}.get)
    st.dataframe(ru(merges[merges["kind"] == kind].drop(columns=["kind"])), hide_index=True, width="stretch")
with c2:
    st.subheader("Отброшенные служебные строки")
    st.dataframe(ru(service), hide_index=True, width="stretch")
