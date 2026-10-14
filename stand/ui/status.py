"""Статус данных для версии руководства: когда проверяли сайт вуза, что пошло не так."""
from datetime import datetime

from collector import read_status
from semester import semesters, semester_for, today


def checked_text() -> str:
    st_ = read_status()
    ts = st_.get("last_success_at")
    if not ts:
        return "сайт вуза ещё не проверялся"
    t = datetime.fromisoformat(ts)
    return f"сайт вуза проверен {t:%d.%m.%Y в %H:%M}"


def warnings(snaps, changes) -> list[str]:
    """Что требует внимания: ошибка последнего сбора, неполный сбор, снятая неделя, нет дат семестра."""
    out = []
    st_ = read_status()
    if st_ and not st_.get("ok", True):
        out.append(f"Последняя проверка {st_.get('checked_at', '')[:16].replace('T', ' ')}: {st_.get('message', '')}")
    if snaps is not None and not snaps.empty:
        last = snaps.iloc[0]
        if last.get("published") == 0:
            out.append(last.get("note") or "Последний сбор не опубликован.")
    if changes is not None and not changes.empty:
        removed = changes[changes["kind"] == "week_removed"]
        if len(removed):
            groups = ", ".join(sorted(set(removed["group_name"]))[:10])
            out.append(f"С сайта вуза сняты недели сессии ({len(removed)}): {groups}. "
                       "Студенты видят последнюю сохранённую версию.")
    if semester_for(today()) is None and not near_semester():
        out.append("Сегодня не попадает ни в один семестр, и рядом семестров нет: графики учебного процесса на "
                   "новый учебный год ещё не разобраны или даты не заданы в .env (SPRING_START / SPRING_END, "
                   "AUTUMN_START / AUTUMN_END). Пока дат нет, студенты видят обе недели, а календарь очников пуст.")
    return out


def near_semester(days: int = 45) -> bool:
    """Сессия и каникулы между семестрами — норма: семестр кончился или начнётся в ближайшие days дней."""
    t = today()
    sems = semesters(t.year) + semesters(t.year - 1) + semesters(t.year + 1)
    return any(-days <= (a - t).days <= days or -days <= (t - b).days <= days for a, b in sems)


def semester_lines() -> list[str]:
    """Семестры этого учебного года и откуда они взяты — для «Истории сборов»."""
    from config import env_date
    from semester import _graph_semesters
    t = today()
    year = t.year if t.month >= 8 else t.year - 1
    graph = set(_graph_semesters())
    out = []
    for a, b in sorted(semesters(year) + semesters(year + 1)):
        if not (date_in_year(a, year)):
            continue
        src = "по графикам учебного процесса" if (a, b) in graph else (
            "из .env" if env_date("SPRING_START" if a.month < 8 else "AUTUMN_START") else "по умолчанию")
        name = "Весна" if a.month < 8 else "Осень"
        out.append(f"{name}: {a:%d.%m.%Y} – {b:%d.%m.%Y} ({src})")
    return out


def date_in_year(d, year: int) -> bool:
    """Дата относится к учебному году year (1 августа year – 31 июля year+1)."""
    from datetime import date
    return date(year, 8, 1) <= d < date(year + 1, 8, 1)


def collect_button(key: str) -> None:
    """Ручной сбор с сайта вуза — только в версии для руководства."""
    import streamlit as st
    import collector
    if st.button("Проверить сайт сейчас", key=key, icon=":material/sync:",
                 help="Скачать расписание с сайта вуза, не дожидаясь планового сбора"):
        if collector.request_collect():
            st.success("Запрос отправлен. Обход сайта занимает несколько минут — обновите страницу позже.")
        else:
            st.info("Сайт проверяли меньше 10 минут назад. Попробуйте позже.")
