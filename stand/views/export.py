import io

import pandas as pd
import streamlit as st

from analytics import queries as q
from labels import WEEK_TYPES, ru
from ui import filters

st.title("Данные и экспорт")
st.caption("Все занятия текущей выборки после очистки — одна строка на занятие. Выгрузка учитывает фильтры.")
ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)

tt = teachers.groupby("lesson_id")["teacher"].apply(", ".join).rename("teachers")
rr = rooms.assign(r=rooms["room_building"] + " · " + rooms["room"]).groupby("lesson_id")["r"].apply(", ".join).rename("rooms")
table = lessons.merge(tt, on="lesson_id", how="left").merge(rr, on="lesson_id", how="left")
table["week_type"] = table["week_type"].map(WEEK_TYPES)
table = table.sort_values(["institute", "group_name", "date", "day_idx", "time_from"])   # дни — по порядку недели
table = table[["cell_building", "institute", "study_form", "group_name", "subgroup", "day", "date", "time_from", "time_to",
               "week_type", "lesson_type", "discipline", "teachers", "rooms", "hours", "subject_raw"]]
table = table.pipe(ru)
st.dataframe(table, hide_index=True, width="stretch", height=560)

c1, c2 = st.columns(2)
c1.download_button("Скачать CSV", table.to_csv(index=False).encode("utf-8-sig"), "raspisanie.csv", "text/csv")

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    table.to_excel(xw, sheet_name="Занятия", index=False)
    ru(q.teacher_load(lessons, teachers, rooms)).to_excel(xw, sheet_name="Преподаватели", index=False)
    ru(q.room_load(lessons, rooms)).to_excel(xw, sheet_name="Аудитории", index=False)
    ru(q.discipline_summary(lessons, teachers)).to_excel(xw, sheet_name="Дисциплины", index=False)
c2.download_button("Скачать Excel (4 листа)", buf.getvalue(), "raspisanie.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
