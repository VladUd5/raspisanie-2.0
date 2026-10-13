"""Статус данных для версии руководства: когда проверяли сайт вуза, что пошло не так."""
from datetime import datetime

from collector import read_status
from semester import semester_for, today


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
    if semester_for(today()) is None:
        out.append("Сегодня не попадает ни в один семестр: проверьте даты в .env (SPRING_START / SPRING_END, "
                   "AUTUMN_START / AUTUMN_END). Пока даты не заданы, студенты видят обе недели, "
                   "а календарь очников пуст.")
    return out
