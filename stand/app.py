"""Лабораторный стенд «Расписание 2.0»: сбор → очистка → анализ."""
import streamlit as st

from config import db_path, snapshots_dir
from etl.load import connect, ensure_loaded
from ui import filters

st.set_page_config(page_title="Расписание 2.0", page_icon="📅", layout="wide")


@st.cache_resource(show_spinner="Первичная загрузка снапшотов…")
def _bootstrap(db: str, snaps: str) -> list[tuple[str, str]]:
    conn = connect(db)
    try:
        return ensure_loaded(conn, snaps)[1]
    finally:
        conn.close()


for name, err in _bootstrap(str(db_path()), str(snapshots_dir())):
    st.warning(f"Снапшот `{name}` не загружен: {err}")

# Страницы лежат в views/, а не в pages/: папку pages/ рядом с точкой входа
# Streamlit подхватывает сам (старый режим многостраничности), и тогда прямая
# ссылка на страницу открывает её без app.py — без фильтров в боковой панели.
pages = st.navigation([
    st.Page("views/overview.py", title="Обзор и пайплайн", icon="🔄", default=True),
    st.Page("views/teachers.py", title="Преподаватели", icon="👩‍🏫"),
    st.Page("views/rooms.py", title="Аудитории", icon="🚪"),
    st.Page("views/disciplines.py", title="Дисциплины", icon="📚"),
    st.Page("views/groups.py", title="Группы", icon="👥"),
    st.Page("views/quality.py", title="Качество данных", icon="🧹"),
    st.Page("views/export.py", title="Данные и экспорт", icon="⬇️"),
])
st.session_state["ctx"] = filters.sidebar()
pages.run()
