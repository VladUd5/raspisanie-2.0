import streamlit as st

from analytics import queries as q
from charts.common import bar_h, stacked_by_type
from labels import WEEK_TYPES, ru
from ui import filters, theme

st.title("Дисциплины")
st.caption("Часы в неделю по дисциплинам, кто их ведёт и у скольких групп. Варианты написания "
           "одной дисциплины склеены на этапе очистки.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)
summary = q.discipline_summary(lessons, teachers)
summary = summary[summary["discipline"] != "—"]
if summary.empty:
    st.info("В выборке нет дисциплин.")
    st.stop()

top = st.slider("Сколько дисциплин показать на графиках", 5, 40, 15)
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(summary, "discipline", "hours", f"Топ-{top} дисциплин по часам", "часов в неделю",
                        theme.mode(), top=top), width="stretch")
right.dataframe(ru(summary), hide_index=True, width="stretch", height=520,
                column_config={"Часов в неделю": st.column_config.NumberColumn(format="%.2f")})

by_type = q.discipline_by_type(lessons, teachers, summary["discipline"].head(top).tolist())
st.plotly_chart(stacked_by_type(by_type, "discipline", "hours", "Часы по типам занятий", "часов",
                                theme.mode()), width="stretch")

st.subheader("Одна дисциплина")
disc = st.selectbox("Дисциплина", summary["discipline"].tolist())
detail = lessons[lessons["discipline"] == disc].merge(teachers, on="lesson_id", how="left")
detail["week_type"] = detail["week_type"].map(WEEK_TYPES)
st.dataframe(ru(detail[["institute", "group_name", "day", "time_from", "week_type", "lesson_type", "teacher",
                        "subject_raw"]].sort_values(["group_name"])), hide_index=True, width="stretch")
