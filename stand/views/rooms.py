import streamlit as st

from analytics import queries as q
from charts.common import bar_h, heatmap
from labels import ru
from ui import filters, ranking, theme

st.title("Аудитории")
st.caption("Загруженность кабинетов и связка «кабинет — дисциплина». Аудитория определяется парой "
           "(корпус, номер); места в прилегающих зданиях — отдельной группой.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)

scopes = {"all": "Все", "main": "Основные корпуса", "adjacent": "Прилегающие здания"}
scope = st.segmented_control("Где", list(scopes), format_func=scopes.get, default="all", required=True)
load = q.room_load(lessons, rooms, scope)
if load.empty:
    st.info("В выборке нет занятий с распознанной аудиторией.")
    st.stop()

top, ascending = ranking.controls("rooms", "аудиторий", 50, 20)
load = q.rank(load, "hours", "room_label", ascending)
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(load, "room_label", "hours", ranking.title(top, ascending, "аудиторий", "часам в неделю"),
                        "часов в неделю", theme.mode(), top=top), width="stretch")
right.dataframe(ru(load.drop(columns=["room_label"])), hide_index=True, width="stretch", height=520,
                column_config={"Часов в неделю": st.column_config.NumberColumn(format="%.2f")})

st.subheader("Кабинет × дисциплина")
matrix = q.room_discipline_matrix(lessons, rooms, scope)
n_rooms = st.slider("Аудиторий в матрице", 5, 60, 25)
n_disc = st.slider("Дисциплин в матрице", 5, 40, 15)
st.plotly_chart(heatmap(matrix.iloc[:n_rooms, :n_disc], "Часов в неделю: аудитория × дисциплина", "часов",
                        theme.mode()), width="stretch")
with st.expander("Полная матрица таблицей"):
    st.dataframe(matrix.round(2), width="stretch")

st.subheader("Неделя одной аудитории")
room = st.selectbox("Аудитория", load["room_label"].tolist())
st.plotly_chart(heatmap(q.room_heatmap(lessons, rooms, room), f"{room}: часы по дням и времени", "часов",
                        theme.mode()), width="stretch")
