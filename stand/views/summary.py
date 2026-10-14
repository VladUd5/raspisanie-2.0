from datetime import timedelta

import pandas as pd
import streamlit as st

from analytics import queries as q
from config import feedback_db_path, public_url
from feedback import store as feedback
from semester import today, week_type_on
from ui import data, filters, status

st.title("Сводка")
wt = {"numerator": "верхняя неделя", "denominator": "нижняя неделя"}.get(week_type_on(today()), "вне семестра")
head, btn = st.columns([4, 1], vertical_alignment="bottom")
head.caption(f"Сегодня {today():%d.%m.%Y}, {wt} · {status.checked_text()}")
with btn:
    status.collect_button("collect_summary")

changes = data.changes()
week_ago = (today() - timedelta(days=7)).isoformat()
recent = changes[changes["day"] >= week_ago] if not changes.empty else changes
alerts = status.warnings(data.snapshots(), recent)

ctx = filters.current()
if filters.need_data(ctx):
    st.stop()
lessons, teachers, rooms = filters.filtered(ctx)

conn = feedback.connect(feedback_db_path())
try:
    counts = feedback.counts(conn)
    fresh = feedback.list_reports(conn, ("new",))[:5]
finally:
    conn.close()

with st.container(border=True):
    if alerts:
        st.markdown("**Требует внимания**")
        for a in alerts:
            st.warning(a, icon=":material/warning:")
    else:
        st.markdown(":material/check_circle: **Проблем не найдено.** Последний сбор опубликован, даты семестра заданы.")

load = q.teacher_load(lessons, teachers, rooms)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Изменений за 7 дней", len(recent), border=True)
c2.metric("Новых сообщений", counts["new"], help=f"В работе: {counts['in_progress']}", border=True)
c3.metric("Средняя нагрузка", f"{load['hours'].mean():.1f} ч" if not load.empty else "—",
          help="Часов в неделю на преподавателя по выборке; медиана "
               + (f"{load['hours'].median():.1f}" if not load.empty else "—"), border=True)
c4.metric("Преподавателей", len(load), border=True)

counts_all = q.overview_counts(lessons, teachers, rooms)
cols = st.columns(4)
for col, (key, label) in zip(cols, [("institutes", "Институтов"), ("groups", "Групп"), ("rooms", "Аудиторий"),
                                    ("disciplines", "Дисциплин")]):
    col.metric(label, counts_all[key], border=True)
st.caption("Цифры — по фильтрам в боковой панели (по умолчанию — очная форма).")

left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("Что изменилось за неделю")
    if recent.empty:
        st.caption("Изменений не было.")
    else:
        by_kind = recent.groupby("kind").size().rename(index=data.CHANGE_KINDS).sort_values(ascending=False)
        st.dataframe(pd.DataFrame({"Что": by_kind.index, "Сколько": by_kind.values}), hide_index=True,
                     width="stretch",
                     column_config={"Сколько": st.column_config.ProgressColumn(
                         format="%d", min_value=0, max_value=int(by_kind.max()))})
    st.page_link("views/changes.py", label="Все изменения", icon=":material/arrow_forward:")
with right:
    st.subheader("Новые сообщения")
    if not fresh:
        st.caption("Новых сообщений нет.")
    for r in fresh:
        with st.container(border=True):
            where = r["group_name"] or r["teacher"] or r["room"] or ""
            st.markdown(f"**{feedback.KINDS.get(r['kind'], r['kind'])}** · {where}")
            st.caption(f"{r['created_at'][:16].replace('T', ' ')} · {(r['text'] or '—')[:140]}")
    st.page_link("views/reports.py", label="Все сообщения", icon=":material/arrow_forward:")

if public_url():
    st.caption(f"Сайт для студентов и преподавателей: {public_url()}")
