from datetime import timedelta

import streamlit as st

from analytics import queries as q
from config import feedback_db_path
from feedback import store as feedback
from semester import today
from ui import data, filters, status

st.title("Сводка")
st.caption(f"Актуальное расписание: {status.checked_text()}.")

changes = data.changes()
week_ago = (today() - timedelta(days=7)).isoformat()
recent = changes[changes["day"] >= week_ago] if not changes.empty else changes
for w in status.warnings(data.snapshots(), recent):
    st.warning(w)

ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)

conn = feedback.connect(feedback_db_path())
try:
    counts = feedback.counts(conn)
finally:
    conn.close()

c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.metric("Изменений за 7 дней", len(recent))
    st.page_link("views/changes.py", label="Открыть изменения", icon="🔁")
with c2.container(border=True):
    st.metric("Новых сообщений", counts["new"], help=f"В работе: {counts['in_progress']}")
    st.page_link("views/reports.py", label="Открыть сообщения", icon="✉️")
with c3.container(border=True):
    load = q.teacher_load(lessons, teachers, rooms)
    st.metric("Преподавателей в выборке", len(load))
    if not load.empty:
        st.caption(f"В среднем {load['hours'].mean():.1f} ч в неделю, медиана {load['hours'].median():.1f}")

counts_all = q.overview_counts(lessons, teachers, rooms)
cols = st.columns(5)
for col, (key, label) in zip(cols, [("institutes", "Институтов"), ("groups", "Групп"), ("teachers", "Преподавателей"),
                                    ("rooms", "Аудиторий"), ("disciplines", "Дисциплин")]):
    col.metric(label, counts_all[key])
st.caption("Цифры — по фильтрам в боковой панели (по умолчанию — очная форма).")

if not recent.empty:
    st.subheader("Что изменилось за неделю")
    by_kind = recent.groupby("kind").size().rename(index=data.CHANGE_KINDS)
    st.dataframe(by_kind.rename("Сколько").reset_index().rename(columns={"kind": "Что"}), hide_index=True)
