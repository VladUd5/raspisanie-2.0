"""Лабораторный стенд «Расписание 2.0»: сбор → очистка → анализ."""
import streamlit as st

from config import db_path, snapshots_dir
from etl.load import connect, ensure_loaded
from ui import filters

st.set_page_config(page_title="Расписание 2.0", page_icon="📅", layout="wide")


def _load_new_snapshots() -> list[tuple[str, str]]:
    """На каждом запуске: новые файлы в data/snapshots (положенные руками или
    оставшиеся от прерванного сбора) попадают в БД без перезапуска стенда.
    Если новых файлов нет, это один SELECT и glob."""
    conn = connect(db_path())
    try:
        loaded, errors = ensure_loaded(conn, snapshots_dir())
    finally:
        conn.close()
    if loaded:
        st.cache_data.clear()
    return errors


for name, err in _load_new_snapshots():
    st.warning(f"Снапшот `{name}` не загружен: {err}")

# Страницы лежат в views/, а не в pages/: папку pages/ рядом с точкой входа
# Streamlit подхватывает сам (старый режим многостраничности), и тогда прямая
# ссылка на страницу открывает её без app.py — без фильтров в боковой панели.
pages = st.navigation({
    "Расписание": [
        st.Page("views/overview.py", title="Обзор и пайплайн", icon="🔄", default=True),
        st.Page("views/teachers.py", title="Преподаватели", icon="👩‍🏫"),
        st.Page("views/rooms.py", title="Аудитории", icon="🚪"),
        st.Page("views/disciplines.py", title="Дисциплины", icon="📚"),
        st.Page("views/groups.py", title="Группы", icon="👥"),
        st.Page("views/export.py", title="Данные и экспорт", icon="⬇️"),
    ],
    "Аналитика": [
        st.Page("views/infographics.py", title="Инфографика", icon="📊"),
        st.Page("views/quality.py", title="Качество данных", icon="🧹"),
        st.Page("views/spellings.py", title="Словарь написаний", icon="🔤"),
    ],
})
st.session_state["ctx"] = filters.sidebar()
pages.run()
