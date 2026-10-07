import streamlit as st

from analytics import queries as q
from charts.common import bar_h
from ui import filters, theme

st.title("Группы")
st.caption("Расписание выбранной группы сеткой «день × время» после очистки.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)
groups = sorted(lessons["group_name"].unique())
if not groups:
    st.info("В выборке нет групп.")
    st.stop()
group = st.selectbox("Группа", groups)
st.dataframe(q.group_grid(lessons, teachers, rooms, group), width="stretch")
daily = q.group_daily_load(lessons, group)
st.plotly_chart(bar_h(daily.iloc[::-1], "day", "hours", f"{group}: часов по дням", "часов", theme.mode(), top=7),
                width="stretch")
