import streamlit as st

from analytics import queries as q
from charts.common import bar_h
from config import collect_timeout_s, parser_url, schedule_url, snapshots_dir
from etl.collect import CollectError, collect
from etl.load import load_snapshot
from labels import ru
from ui import data, filters, theme

st.title("Расписание 2.0")
st.caption("Лабораторный стенд: сквозной цикл **сбор → очистка → анализ** на расписании Вавиловского университета")

with st.container(border=True):
    st.markdown(f"**Сбор.** Парсер `{parser_url()}` обходит `{schedule_url()}`, скачивает PDF и отдаёт JSON. "
                "Полный обход занимает несколько минут.")
    if st.button("Собрать данные с сайта", type="primary"):
        try:
            with st.status("Парсер обходит сайт вуза…", expanded=True) as status:
                path = collect(parser_url(), schedule_url(), snapshots_dir(), collect_timeout_s())
                # загрузка сразу после сбора, без вызовов st.* между ними: если пользователь
                # прервёт выполнение страницы, снапшот уже будет в БД
                conn = data.conn()
                try:
                    new_id = load_snapshot(conn, path)
                finally:
                    conn.close()
                status.write(f"Снапшот `{path.name}` сохранён и загружен в БД.")
                status.update(label="Готово", state="complete")
            st.cache_data.clear()
            # виджет «Снапшот» уже создан в сайдбаре — выбор применится на следующем запуске
            st.session_state["pending_snapshot"] = new_id
            st.rerun()
        except CollectError as e:
            st.error(f"Сбор не удался: {e} Ранее собранные снапшоты по-прежнему доступны.")

ctx = filters.current()
if filters.need_data(ctx):
    st.stop()

lessons, teachers, rooms = filters.filtered(ctx)
snap = data.snapshots().set_index("id").loc[ctx.snapshot_id]
quality, service, _ = data.quality(ctx.snapshot_id)

st.subheader("Пайплайн выбранного снапшота")
c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.markdown("**1 · Сбор**")
    st.metric("Ячеек расписания из PDF", f"{snap.cells_cnt:,}".replace(",", " "))
    st.caption(f"Собран {snap.collected_at}, файл `{snap.file_name}`")
with c2.container(border=True):
    st.markdown("**2 · Очистка**")
    st.metric("Занятий после разбора", f"{snap.lessons_cnt:,}".replace(",", " "))
    st.caption(f"Служебных строк отброшено: {snap.service_cnt}. "
               f"Требуют проверки: {100 * quality['needs_review'].mean():.1f}% занятий.")
with c3.container(border=True):
    st.markdown("**3 · Анализ**")
    counts = q.overview_counts(lessons, teachers, rooms)
    st.metric("Занятий в текущей выборке", f"{counts['lessons']:,}".replace(",", " "))
    st.caption("Учитываются фильтры из боковой панели")

cols = st.columns(5)
for col, (key, label) in zip(cols, [("institutes", "Институтов"), ("groups", "Групп"), ("teachers", "Преподавателей"),
                                    ("rooms", "Аудиторий"), ("disciplines", "Дисциплин")]):
    col.metric(label, counts[key])

by_inst = q.lessons_by_institute(lessons)
left, right = st.columns([3, 2])
left.plotly_chart(bar_h(by_inst, "institute", "count", "Занятий по институтам", "занятий", theme.mode()),
                  width="stretch")
right.dataframe(ru(by_inst), hide_index=True, width="stretch")

shift = q.day_shift_warnings(lessons)
if not shift.empty:
    st.warning(f"У {len(shift)} групп есть занятия в воскресенье — возможно, парсер сдвинул дни недели "
               "(см. «Ограничения» в README).")
    st.dataframe(ru(shift), hide_index=True)

st.subheader("История снапшотов")
st.dataframe(ru(data.snapshots().drop(columns=["id"])), hide_index=True, width="stretch")
