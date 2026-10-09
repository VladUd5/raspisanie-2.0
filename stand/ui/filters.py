"""Сквозные фильтры в боковой панели. Выбор хранится в st.session_state и
действует на всех страницах."""
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from analytics.queries import Filters
from charts.common import LESSON_TYPES
from labels import DAYS, WEEK_TYPES
from ui import data

KEYS = ["f_buildings", "f_institutes", "f_forms", "f_groups", "f_session", "f_days", "f_weeks", "f_types"]


@dataclass
class Context:
    snapshot_id: int | None
    filters: Filters


def _multiselect(label: str, options: list, key: str, **kw) -> list:
    if key in st.session_state:   # значения, которых больше нет среди вариантов, убираем
        st.session_state[key] = [v for v in st.session_state[key] if v in options]
    return st.sidebar.multiselect(label, options, key=key, placeholder="все", **kw)


DEFAULT_FORM = "Очная"


def _reset() -> None:
    """Вернуть фильтры к умолчанию (очная форма, остальное — «все»)."""
    for k in [*KEYS, "f_full"]:
        st.session_state.pop(k, None)


ALL_WEEKS = "все недели вместе"


def week_label(monday: str) -> str:
    """«2026-09-28» → «28.09–03.10»."""
    d = pd.Timestamp(monday)
    return f"{d:%d.%m}–{d + pd.Timedelta(days=5):%d.%m}"


def _session_week(sub: pd.DataFrame) -> str | None:
    """Неделя сессии заочки: показывается, если в выборке есть датированные занятия.
    По умолчанию — последняя неделя: недели сессии смешивать нельзя, как и с неделей очников."""
    weeks = sorted({w for w in sub["session_week"] if w}, reverse=True)
    if not weeks:
        st.session_state.pop("f_session", None)
        return None
    options = weeks + [ALL_WEEKS]
    if st.session_state.get("f_session") not in options:
        st.session_state["f_session"] = weeks[0]
    choice = st.sidebar.selectbox("Неделя сессии (заочники)", options, key="f_session",
                                  format_func=lambda w: w if w == ALL_WEEKS else week_label(w),
                                  help="Заочное расписание выкладывается по неделям сессии. Занятия из "
                                       "файлов без дат видны только в режиме «все недели вместе».")
    return None if choice == ALL_WEEKS else choice


def sidebar() -> Context:
    snaps = data.snapshots()
    if snaps.empty:
        st.sidebar.info("Данных пока нет: соберите их на странице «Обзор».")
        return Context(None, Filters())

    ids = snaps["id"].tolist()
    if "pending_snapshot" in st.session_state:          # только что собранный снапшот
        st.session_state["snapshot_id"] = st.session_state.pop("pending_snapshot")
    if st.session_state.get("snapshot_id") not in ids:
        st.session_state["snapshot_id"] = ids[0]
    names = {r.id: f"{r.collected_at} · {r.lessons_cnt} занятий" for r in snaps.itertuples()}
    sid = st.sidebar.selectbox("Снапшот", ids, format_func=names.get, key="snapshot_id")

    lessons = data.frames(sid).lessons
    st.sidebar.caption("Фильтры действуют на всех страницах")
    sub = lessons
    chosen = {}
    for key, label, col in [("f_buildings", "Корпус", "cell_building"), ("f_institutes", "Институт", "institute"),
                            ("f_forms", "Форма обучения", "study_form"), ("f_groups", "Группа", "group_name")]:
        options = sorted(sub[col].dropna().unique())
        if key == "f_forms" and key not in st.session_state and DEFAULT_FORM in options:
            # у заочников расписание сессионное: смешивать его с неделей очников нельзя
            st.session_state[key] = [DEFAULT_FORM]
        chosen[key] = _multiselect(label, options, key)
        if chosen[key]:
            sub = sub[sub[col].isin(chosen[key])]
    session = _session_week(sub)
    present_days = [d for d in DAYS if d in set(lessons["day"])]
    days = _multiselect("День недели", present_days, "f_days")
    weeks = _multiselect("Неделя", list(WEEK_TYPES), "f_weeks", format_func=WEEK_TYPES.get)
    types = _multiselect("Тип занятия", [t for t in LESSON_TYPES if t in set(lessons["lesson_type"])], "f_types")
    full = st.sidebar.toggle("Верхнюю/нижнюю неделю считать полной парой", key="f_full",
                             help="Занятие только по верхней или только по нижней неделе идёт раз в две недели "
                                  "и считается как 0.5 пары.")
    st.sidebar.button("Сбросить фильтры", on_click=_reset)
    st.sidebar.caption("По умолчанию — очная форма: её неделю нельзя смешивать с расписанием заочников. "
                       "У заочной формы нагрузка считается внутри выбранной недели сессии.")
    return Context(sid, Filters(
        buildings=tuple(chosen["f_buildings"]), institutes=tuple(chosen["f_institutes"]),
        study_forms=tuple(chosen["f_forms"]), groups=tuple(chosen["f_groups"]), days=tuple(days),
        week_types=tuple(weeks), lesson_types=tuple(types), full_weeks=full,
        session_weeks=(session,) if session else ()))


def current() -> Context:
    """Контекст строит app.py; если страницу исполнили без него — строим сами."""
    if "ctx" not in st.session_state:
        st.session_state["ctx"] = sidebar()
    return st.session_state["ctx"]


def filtered(ctx: Context) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from analytics.queries import apply_filters
    f = data.frames(ctx.snapshot_id)
    return apply_filters(f.lessons, ctx.filters), f.teachers, f.rooms


def need_data(ctx: Context) -> bool:
    """True, если показывать нечего (страница сама выводит подсказку)."""
    if ctx.snapshot_id is None:
        st.info("Данных пока нет. Откройте «Обзор» и нажмите «Собрать данные», "
                "или положите снапшот в data/snapshots/.")
        return True
    return False
