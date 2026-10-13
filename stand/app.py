"""Расписание: версия для руководства (нагрузка, аудитории, изменения, сообщения пользователей)."""
import sqlite3

import streamlit as st

from config import db_path, feedback_db_path, site_title, snapshots_dir
from feedback import store as feedback
from etl.load import connect, ensure_loaded
from ui import filters

st.set_page_config(page_title=f"{site_title()} · руководство", page_icon="📅", layout="wide")


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


n_new = _new_reports()
pages = st.navigation({
    "Расписание": [
        st.Page("views/summary.py", title="Сводка", icon="🏠", default=True),
        st.Page("views/teachers.py", title="Преподаватели", icon="👩‍🏫"),
        st.Page("views/rooms.py", title="Аудитории", icon="🚪"),
        st.Page("views/disciplines.py", title="Дисциплины", icon="📚"),
        st.Page("views/groups.py", title="Группы", icon="👥"),
        st.Page("views/infographics.py", title="Инфографика", icon="📊"),
        st.Page("views/changes.py", title="Изменения", icon="🔁"),
        st.Page("views/reports.py", title=f"Сообщения ({n_new})" if n_new else "Сообщения", icon="✉️"),
        st.Page("views/export.py", title="Выгрузка", icon="⬇️"),
    ],
    "Служебное": [
        st.Page("views/history.py", title="История сборов", icon="🕓"),
        st.Page("views/quality.py", title="Качество данных", icon="🧹"),
        st.Page("views/spellings.py", title="Словарь написаний", icon="🔤"),
    ],
})
st.session_state["ctx"] = filters.sidebar()
pages.run()
