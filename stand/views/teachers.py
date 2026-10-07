import streamlit as st

from analytics import queries as q
from charts.common import bar_by_type, bar_h, heatmap
from labels import WEEK_TYPES, ru
from ui import filters, ranking, theme

st.title("Преподаватели")
st.caption("Нагрузка за неделю по всем институтам и формам обучения в выборке. Поточная лекция для "
           "нескольких групп считается один раз.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)
load = q.teacher_load(lessons, teachers, rooms)
if load.empty:
    st.info("В выборке нет занятий с преподавателями.")
    st.stop()

top, ascending = ranking.controls("teachers", "преподавателей", 50, 20)
load = q.rank(load, "hours", "teacher", ascending)
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(load, "teacher", "hours", ranking.title(top, ascending, "преподавателей", "часам в неделю"),
                        "часов в неделю", theme.mode(), top=top), width="stretch")
right.dataframe(ru(load), hide_index=True, width="stretch", height=520,
                column_config={"Часов в неделю": st.column_config.NumberColumn(format="%.2f"),
                               "Занятий в неделю": st.column_config.NumberColumn(format="%.2f")})

st.subheader("Неделя одного преподавателя")
teacher = st.selectbox("Преподаватель", load["teacher"].tolist())
hm = q.teacher_heatmap(lessons, teachers, teacher)
by_type = q.teacher_by_type(lessons, teachers, teacher)
c1, c2 = st.columns([3, 2])
c1.plotly_chart(heatmap(hm, f"{teacher}: часы по дням и времени", "часов", theme.mode()), width="stretch")
c2.plotly_chart(bar_by_type(by_type, "lesson_type", "hours", "По типам занятий", "часов", theme.mode()),
                width="stretch")
sched = q.teacher_schedule(lessons, teachers, rooms, teacher)
sched["week_type"] = sched["week_type"].map(WEEK_TYPES)
st.dataframe(ru(sched), hide_index=True, width="stretch")
