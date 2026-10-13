import io
from datetime import timedelta

import pandas as pd
import streamlit as st

from semester import today
from ui import data

st.title("Изменения в расписании")
st.caption("Что поменялось на сайте вуза между проверками. Прошедшие даты не сравниваются — это история. "
           "Новая неделя сессии заочников — одна строка «новая неделя», а не поштучные добавления.")

ch = data.changes()
if ch.empty:
    st.info("Изменений пока нет: нужно хотя бы две опубликованные версии расписания.")
    st.stop()

days = st.segmented_control("Период", [7, 14, 30, 90, 365], default=14, format_func=lambda d: f"{d} дн.",
                            required=True)
ch = ch[ch["day"] >= (today() - timedelta(days=days)).isoformat()]
c1, c2, c3, c4 = st.columns(4)
inst = c1.multiselect("Институт", sorted({x for x in ch["institute"] if x}), placeholder="все")
forms = c2.multiselect("Форма", sorted({x for x in ch["study_form"] if x}), placeholder="все")
kinds = c3.multiselect("Что", list(data.CHANGE_KINDS), format_func=data.CHANGE_KINDS.get, placeholder="всё")
text = c4.text_input("Группа, преподаватель, аудитория")
if inst:
    ch = ch[ch["institute"].isin(inst)]
if forms:
    ch = ch[ch["study_form"].isin(forms)]
if kinds:
    ch = ch[ch["kind"].isin(kinds)]
if text:
    t = text.casefold()
    ch = ch[[t in f"{g} {te} {r}".casefold() for g, te, r in zip(ch["group_name"], ch["teachers"], ch["rooms"])]]

table = pd.DataFrame({
    "Обнаружено": [f"{d[8:10]}.{d[5:7]}.{d[:4]}" for d in ch["day"]],
    "Что": ch["kind"].map(data.CHANGE_KINDS),
    "Группа": ch["group_name"], "Форма": ch["study_form"], "Институт": ch["institute"],
    "Было": ch["before"], "Стало": ch["after"], "Преподаватели": ch["teachers"], "Аудитории": ch["rooms"]})
st.caption(f"Найдено: {len(table)}")
st.dataframe(table, hide_index=True, width="stretch", height=560)
buf = io.BytesIO()
table.to_excel(buf, index=False, sheet_name="Изменения")
st.download_button("Скачать Excel", buf.getvalue(), "izmeneniya.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
