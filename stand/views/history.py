from datetime import datetime

import streamlit as st

import collector
from config import collect_schedule_text
from labels import ru
from semester import semester_for, today, tz
from ui import data, status

st.title("История сборов")
st.caption(f"Сбор расписания с сайта вуза идёт автоматически {collect_schedule_text()} (COLLECT_DAYS, "
           "COLLECT_TIMES в .env) и по кнопке «Проверить сайт сейчас». Версия, которая ничем не отличается "
           "от прошлой, не сохраняется.")

st_ = collector.read_status()
with st.container(border=True):
    st.markdown(f"**Состояние:** {status.checked_text()}.")
    if st_:
        st.caption(f"Последняя проверка: {st_.get('checked_at', '')[:16].replace('T', ' ')} ({st_.get('reason', '')}). "
                   f"{st_.get('message', '')}")
    status.collect_button("collect_history")

with st.container(border=True):
    st.markdown("**Даты семестров** — по графикам учебного процесса; в `.env` на сервере их можно задать вручную, "
                "тогда они главнее")
    sem = semester_for(today())
    st.caption(" · ".join(status.semester_lines() or ["Семестры этого учебного года ещё неизвестны"]) + ". "
               + (f"Сейчас идёт семестр {sem[0]:%d.%m.%Y}–{sem[1]:%d.%m.%Y}." if sem else
                  "Сегодня — между семестрами или вне учебного года."))

snaps = data.snapshots()
if snaps.empty:
    st.info("Сборов ещё не было.")
    st.stop()
view = snaps.assign(published=snaps["published"].map({1: "да", 0: "нет"}).fillna("обрабатывается"),
                    note=snaps["note"].fillna(""),
                    collected_at=[datetime.fromisoformat(x).astimezone(tz()).strftime("%d.%m.%Y %H:%M")
                                  for x in snaps["collected_at"]])
view = view[["collected_at", "lessons_cnt", "groups_cnt", "published", "note", "file_name"]]
st.dataframe(ru(view).rename(columns={"published": "Опубликован", "note": "Примечание"}), hide_index=True,
             width="stretch")
