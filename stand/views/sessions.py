from datetime import date

import pandas as pd
import streamlit as st

import kug
from config import feedback_db_path, kug_request_path
from directory import site_base
from feedback import store
from semester import now

STATUS = {"draft": "черновик", "confirmed": "подтверждено", "rejected": "отклонено"}
FILE_STATUS = {"ok": "распознан", "empty": "сессий не найдено", "error": "не прочитан"}

st.title("Сессии")
st.caption("Даты сессий берутся из календарных учебных графиков на сайте вуза (сканы PDF). Программа распознаёт "
           "в них отметки «Э» и предлагает черновик; на сайт для студентов попадают только подтверждённые даты. "
           "Проверьте черновик по скану, поправьте даты, если нужно, и нажмите «Сохранить».")

conn = store.connect(feedback_db_path())
files = pd.read_sql_query("SELECT * FROM kug_files ORDER BY program, form, title", conn)
sess = pd.read_sql_query("SELECT * FROM sessions ORDER BY file_url, course, start_date", conn)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Графиков", len(files), border=True)
c2.metric("Черновиков на проверку", int((sess["status"] == "draft").sum()) if not sess.empty else 0, border=True)
c3.metric("Подтверждено", int((sess["status"] == "confirmed").sum()) if not sess.empty else 0, border=True)
c4.metric("Не прочитано", int((files["status"] == "error").sum()) if not files.empty else 0, border=True)

left, right = st.columns([3, 1])
with right:
    if st.button("Проверить графики на сайте вуза", icon=":material/refresh:"):
        path = kug_request_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")
        st.success("Запрос отправлен: новые графики будут разобраны в течение нескольких минут.")
with left:
    show = st.segmented_control("Показать", ["На проверку", "Подтверждённые", "Без кода группы", "Все"],
                                default="На проверку", required=True)
    text = st.text_input("Программа или код группы", placeholder="например, Б-ЛА или Агрономия")

if files.empty:
    st.info("Графики ещё не загружались. Нажмите «Проверить графики на сайте вуза» — collector разберёт их "
            "в фоне (несколько минут).")
    st.stop()


@st.cache_data(ttl=3600, show_spinner="Загружаю скан…")
def _preview(url: str) -> bytes:
    return kug.preview_png(kug.http_get()(site_base() + url))


def _keep(f) -> bool:
    rows = sess[sess["file_url"] == f.url]
    if text and text.casefold() not in f"{f.program} {f.code} {f.title}".casefold():
        return False
    if show == "На проверку":
        return (rows["status"] == "draft").any() or f.status == "error"
    if show == "Подтверждённые":
        return (rows["status"] == "confirmed").any()
    if show == "Без кода группы":
        return not f.code
    return True


shown = [f for f in files.itertuples() if _keep(f)]
st.caption(f"Графиков в списке: {len(shown)}")
for f in shown[:60]:
    rows = sess[sess["file_url"] == f.url]
    n_draft = int((rows["status"] == "draft").sum())
    head = f"{f.code or '— код не определён —'} · {f.form} · {f.program} · {FILE_STATUS.get(f.status, f.status)}" + \
           (f" · черновиков: {n_draft}" if n_draft else "")
    with st.expander(head, expanded=False):
        st.markdown(f"[{f.title}]({site_base()}{f.url}) · {f.message or ''}")
        code = st.text_input("Код групп (как в начале названия группы, например «Б-ЛА»)", f.code or "",
                             key=f"code_{f.url}")
        table = pd.DataFrame({
            "Курс": rows["course"].astype(int) if not rows.empty else pd.Series(dtype=int),
            "Начало": pd.to_datetime(rows["start_date"]).dt.date if not rows.empty else pd.Series(dtype=object),
            "Конец": pd.to_datetime(rows["end_date"]).dt.date if not rows.empty else pd.Series(dtype=object),
            "Статус": rows["status"].map(STATUS) if not rows.empty else pd.Series(dtype=str)})
        edited = st.data_editor(
            table, num_rows="dynamic", hide_index=True, key=f"ed_{f.url}", width="stretch",
            column_config={"Курс": st.column_config.NumberColumn(min_value=1, max_value=6, step=1, required=True),
                           "Начало": st.column_config.DateColumn(format="DD.MM.YYYY", required=True),
                           "Конец": st.column_config.DateColumn(format="DD.MM.YYYY", required=True),
                           "Статус": st.column_config.SelectboxColumn(options=list(STATUS.values()),
                                                                      default="подтверждено", required=True)})
        b1, b2, b3 = st.columns(3)
        if b1.button("Сохранить", key=f"save_{f.url}", type="primary"):
            back = {v: k for k, v in STATUS.items()}
            bad = [r for r in edited.itertuples() if pd.isna(r.Начало) or pd.isna(r.Конец) or r.Конец < r.Начало]
            if bad:
                st.error("Проверьте даты: конец сессии не может быть раньше начала, пустые даты не сохраняются.")
            else:
                with conn:
                    conn.execute("UPDATE kug_files SET code = ?, code_manual = ? WHERE url = ?",
                                 (code.strip(), int(code.strip() != (f.code or "")), f.url))
                    conn.execute("DELETE FROM sessions WHERE file_url = ?", (f.url,))
                    for r in edited.itertuples():
                        conn.execute("""INSERT INTO sessions (file_url, course, start_date, end_date, status, source,
                                        updated_at) VALUES (?, ?, ?, ?, ?, 'manual', ?)""",
                                     (f.url, int(r.Курс), date.isoformat(r.Начало), date.isoformat(r.Конец),
                                      back.get(r.Статус, "confirmed"), now().isoformat(timespec="seconds")))
                st.rerun()
        if n_draft and b2.button("Подтвердить черновик как есть", key=f"ok_{f.url}"):
            with conn:
                conn.execute("UPDATE sessions SET status = 'confirmed', updated_at = ? WHERE file_url = ? "
                             "AND status = 'draft'", (now().isoformat(timespec="seconds"), f.url))
            st.rerun()
        if b3.toggle("Показать скан", key=f"img_{f.url}"):
            try:
                st.image(_preview(f.url), width="stretch")
            except Exception as e:                             # noqa: BLE001
                st.warning(f"Скан не загрузился: {e}")
if len(shown) > 60:
    st.caption("Показаны первые 60 — уточните поиск.")
conn.close()
