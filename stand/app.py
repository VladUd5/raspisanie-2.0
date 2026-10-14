"""Расписание: версия для руководства (нагрузка, аудитории, изменения, сообщения пользователей)."""
import sqlite3
from pathlib import Path

import streamlit as st

from config import db_path, feedback_db_path, site_title, snapshots_dir
from feedback import store as feedback
from etl.load import connect, ensure_loaded
from ui import filters

STATIC = Path(__file__).parent / "static"
st.set_page_config(page_title=f"{site_title()} · руководство", page_icon=str(STATIC / "icon.svg"), layout="wide")
st.logo(str(STATIC / "logo.svg"), icon_image=str(STATIC / "icon.svg"), size="large")
st.html("<style>[data-testid=stMainBlockContainer]{padding-top:2.5rem}</style>")


def _load_new_snapshots() -> list[str]:
    """На каждом запуске: новые файлы в data/snapshots (положенные руками или
    оставшиеся от прерванного сбора) попадают в БД без перезапуска стенда.
    Если новых файлов нет, это пара SELECT и glob. → предупреждения для показа."""
    try:
        conn = connect(db_path())
        try:
            loaded, errors = ensure_loaded(conn, snapshots_dir())
        finally:
            conn.close()
    except sqlite3.Error as e:   # БД занята дольше таймаута или недоступна на запись: показываем что есть
        return [f"Новые снапшоты не загружены в базу ({e}). Обновите страницу позже; "
                "если повторяется — см. «Если что-то не работает» в README."]
    if loaded:
        st.cache_data.clear()
    return [f"Снапшот `{name}` не загружен: {err}" for name, err in errors]


for warning in _load_new_snapshots():
    st.warning(warning)

# Страницы лежат в views/, а не в pages/: папку pages/ рядом с точкой входа
# Streamlit подхватывает сам (старый режим многостраничности), и тогда прямая
# ссылка на страницу открывает её без app.py — без фильтров в боковой панели.
def _new_reports() -> int:
    try:
        conn = feedback.connect(feedback_db_path())
        try:
            return feedback.counts(conn)["new"]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _draft_sessions() -> int:
    try:
        conn = feedback.connect(feedback_db_path())
        try:
            return conn.execute("SELECT COUNT(*) FROM sessions WHERE status = 'draft'").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


n_new = _new_reports()
n_drafts = _draft_sessions()
pages = st.navigation({
    "Расписание": [
        st.Page("views/summary.py", title="Сводка", icon=":material/space_dashboard:", default=True),
        st.Page("views/teachers.py", title="Преподаватели", icon=":material/person:"),
        st.Page("views/rooms.py", title="Аудитории", icon=":material/meeting_room:"),
        st.Page("views/disciplines.py", title="Дисциплины", icon=":material/menu_book:"),
        st.Page("views/groups.py", title="Группы", icon=":material/groups:"),
        st.Page("views/infographics.py", title="Инфографика", icon=":material/insights:"),
        st.Page("views/changes.py", title="Изменения", icon=":material/published_with_changes:"),
        st.Page("views/reports.py", title=f"Сообщения ({n_new})" if n_new else "Сообщения", icon=":material/mail:"),
        st.Page("views/sessions.py", title=f"Сессии ({n_drafts})" if n_drafts else "Сессии", icon=":material/event:"),
        st.Page("views/export.py", title="Выгрузка", icon=":material/download:"),
    ],
    "Служебное": [
        st.Page("views/history.py", title="История сборов", icon=":material/history:"),
        st.Page("views/quality.py", title="Качество данных", icon=":material/rule:"),
        st.Page("views/spellings.py", title="Словарь написаний", icon=":material/spellcheck:"),
    ],
}, expanded=True)  # иначе Streamlit сворачивает хвост меню под английскую кнопку «View N more»
st.session_state["ctx"] = filters.sidebar()
pages.run()
