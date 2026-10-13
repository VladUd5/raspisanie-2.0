import streamlit as st

import collector
from config import collect_times, env_date
from labels import ru
from semester import semester_for, today
from ui import data, status

st.title("История сборов")
st.caption(f"Сбор с сайта вуза идёт автоматически: каждый день в {', '.join(collect_times())}. "
           "Версия, которая ничем не отличается от прошлой, не сохраняется.")

st_ = collector.read_status()
with st.container(border=True):
    st.markdown(f"**Состояние:** {status.checked_text()}.")
    if st_:
        st.caption(f"Последняя проверка: {st_.get('checked_at', '')[:16].replace('T', ' ')} ({st_.get('reason', '')}). "
                   f"{st_.get('message', '')}")
    if st.button("Проверить сайт сейчас"):
        if collector.request_collect():
            st.success("Запрос отправлен. Обход сайта занимает несколько минут — обновите страницу позже.")
        else:
            st.info("Сайт проверяли меньше 10 минут назад. Попробуйте позже.")

with st.container(border=True):
    st.markdown("**Даты семестров** (задаются в файле `.env` на сервере)")
    sem = semester_for(today())
    st.caption(f"Осень: {env_date('AUTUMN_START') or '09-01'} – {env_date('AUTUMN_END') or '12-31'} · "
               f"весна: {env_date('SPRING_START') or 'не задана'} – {env_date('SPRING_END') or '06-30'}. "
               + (f"Сейчас идёт семестр {sem[0]:%d.%m.%Y}–{sem[1]:%d.%m.%Y}." if sem else
                  "Сегодня не попадает ни в один семестр."))

snaps = data.snapshots()
if snaps.empty:
    st.info("Сборов ещё не было.")
    st.stop()
view = snaps.assign(published=snaps["published"].map({1: "да", 0: "нет"}).fillna("обрабатывается"))
view = view[["collected_at", "lessons_cnt", "groups_cnt", "published", "note", "file_name"]]
st.dataframe(ru(view).rename(columns={"published": "Опубликован", "note": "Примечание"}), hide_index=True,
             width="stretch")
