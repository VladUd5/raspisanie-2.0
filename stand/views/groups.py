import streamlit as st

from analytics import queries as q
from charts.common import bar_h
from labels import ru
from ui import filters, ranking, theme

st.title("Группы")
st.caption("Сколько пар в неделю у групп и расписание выбранной группы сеткой «день × время» после очистки. "
           "Числитель и знаменатель — по половине пары; параллельные подгруппы в одном слоте — одна пара.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)
groups = q.group_options(lessons["group_name"])
if not groups:
    st.info("В выборке нет групп.")
    st.stop()
load = q.group_load(lessons)
stats = load.groupby("study_form")["pairs"].agg(["count", "mean", "median"])
st.caption(" · ".join(f"{form}: {int(r['count'])} групп, в среднем {r['mean']:.1f} пары в неделю "
                      f"(медиана {r['median']:.1f})" for form, r in stats.iterrows()))
top, ascending = ranking.controls("groups", "групп", 50, 20)
load = q.rank(load, "pairs", "group_name", ascending)
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(load, "group_name", "pairs", ranking.title(top, ascending, "групп", "парам в неделю"),
                        "пар в неделю", theme.mode(), top=top), width="stretch")
right.dataframe(ru(load), hide_index=True, width="stretch", height=520,
                column_config={"Пар в неделю": st.column_config.NumberColumn(format="%.1f"),
                               "Часов в неделю": st.column_config.NumberColumn(format="%.2f")})

st.subheader("Неделя одной группы")
group = st.selectbox("Группа", groups, format_func=lambda g: g or "(пустое имя)")
st.dataframe(q.group_grid(lessons, teachers, rooms, group), width="stretch")
daily = q.group_daily_load(lessons, group)
st.plotly_chart(bar_h(daily.iloc[::-1], "day", "hours", f"{group}: часов по дням", "часов", theme.mode(), top=7),
                width="stretch")
