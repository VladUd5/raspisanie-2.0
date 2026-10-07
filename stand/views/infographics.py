import pandas as pd
import streamlit as st

from analytics import queries as q
from charts.common import bar_h, heatmap, histogram
from labels import ru
from ui import filters, theme

st.title("Инфографика")
st.caption("Сводная картина по выборке из боковой панели: как распределена нагрузка, когда вуз загружен "
           "сильнее всего и сколько аудиторий свободно. Числитель и знаменатель — по половине пары.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)
if lessons.empty:
    st.info("В выборке нет занятий.")
    st.stop()
mode = theme.mode()

# --- распределения -----------------------------------------------------------------
st.subheader("Распределение нагрузки")
st.caption("Форма распределения и выбросы с обоих краёв. Левый хвост — кандидаты на проверку: один-два "
           "часа в неделю часто означают непроверенное написание или обрывок ячейки. Их список — в рейтинге "
           "«Наименее загруженные» на страницах «Преподаватели», «Группы», «Аудитории».")
WHAT = {"teacher": "Преподаватели", "group": "Группы", "room": "Аудитории"}
what = st.segmented_control("Что", list(WHAT), format_func=WHAT.get, default="teacher", required=True,
                            key="dist_what")
if what == "teacher":
    values, step, unit, noun = q.teacher_load(lessons, teachers, rooms)["hours"], 1.5, "часов в неделю", "преподавателей"
elif what == "group":
    values, step, unit, noun = q.group_load(lessons)["pairs"], 1.0, "пар в неделю", "групп"
else:
    values, step, unit, noun = q.room_load(lessons, rooms)["hours"], 1.5, "часов в неделю", "аудиторий"
bins, stats = q.distribution(values, step)
if not stats:
    st.info("Нечего показать: в выборке нет таких данных.")
else:
    left, right = st.columns([3, 1])
    left.plotly_chart(histogram(bins, step, f"{WHAT[what]}: {unit}", unit, noun, mode, stats["median"]),
                      width="stretch")
    summary = pd.DataFrame({"Показатель": ["Всего", "Среднее", "Медиана", "10-й перцентиль", "90-й перцентиль",
                                           "Минимум", "Максимум"],
                            "Значение": [stats["count"], stats["mean"], stats["median"], stats["p10"], stats["p90"],
                                         stats["min"], stats["max"]]})
    right.dataframe(summary, hide_index=True, width="stretch",
                    column_config={"Значение": st.column_config.NumberColumn(format="%.2f")})
    with st.expander("Интервалы гистограммы"):
        st.dataframe(bins[["label", "count"]].rename(columns={"label": unit, "count": noun.capitalize()}),
                     hide_index=True, width="stretch")

# --- пиковые часы ------------------------------------------------------------------
st.subheader("Пиковые часы")
peak = q.peak_hours(lessons)
top_day, top_time = peak.stack().idxmax()
st.caption(f"Сколько групп в среднем занимается в каждый слот недели. Пик — {top_day}, {top_time}: "
           f"{peak.loc[top_day, top_time]:.1f} групп. Фильтр по институту в боковой панели покажет пиковые "
           "часы одного института.")
st.plotly_chart(heatmap(peak, "Групп на занятиях: день × время", "групп", mode), width="stretch")
with st.expander("Таблица"):
    st.dataframe(peak.round(1), width="stretch")

# --- аудиторный фонд ---------------------------------------------------------------
st.subheader("Загрузка аудиторного фонда")
st.caption("Доля занятых слотов недели: занятые пары / (аудитории корпуса × слоты недели). Фонд — аудитории, "
           "которые хоть раз встречаются в выборке: кабинетов без занятий стенд не знает, поэтому реальная "
           "загрузка может быть ниже.")
occ = q.room_fund_occupancy(lessons, rooms)
if occ.empty:
    st.info("В выборке нет занятий с распознанной аудиторией.")
    st.stop()
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(occ, "building", "occupancy", "Занятость фонда по корпусам", "% занятых слотов", mode,
                        top=len(occ)), width="stretch")
right.dataframe(ru(occ), hide_index=True, width="stretch",
                column_config={"Занято, %": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
                               "Занято пар": st.column_config.NumberColumn(format="%.1f")})
building = st.selectbox("Корпус", occ["building"].tolist())
free = q.free_rooms(lessons, rooms, building)
st.plotly_chart(heatmap(free, f"{building}: свободных аудиторий в слот", "свободно", mode), width="stretch")
with st.expander("Таблица"):
    st.dataframe(free.round(1), width="stretch")
