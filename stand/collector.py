"""Сбор по расписанию (контейнер collector) — единственный писатель schedule.db в проде.

    python collector.py run    — цикл: сбор расписания в COLLECT_DAYS и COLLECT_TIMES (по умолчанию
                                 пн и чт в 03:00, по часовому поясу сайта) и по кнопке «Проверить сайт
                                 сейчас» в версии для руководства; раз в сутки — справочник кафедр,
                                 графики учебного процесса и резервная копия
    python collector.py once   — один сбор сейчас
    python collector.py load   — только привести БД к папке снапшотов
    python collector.py backup — резервная копия data/ (сама делается раз в сутки)

Сбор, совпавший с последним сохранённым снапшотом, не сохраняется: в status.json пишется только
время проверки. Так в data/snapshots остаются лишь версии, которые чем-то отличаются, и их можно
хранить бессрочно (архив недель заочников).
"""
import json
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import backup
import directory
import kug
from config import (collect_schedule_text, collect_timeout_s, db_path, feedback_db_path, kug_request_path,
                    parser_url, request_path, schedule_url, snapshots_dir, status_path)
from etl.collect import CollectError, collect
from etl.load import connect, ensure_loaded, read_snapshot
from semester import now

MIN_REQUEST_INTERVAL = timedelta(minutes=10)   # «проверить сейчас» не чаще
# Пульс цикла: проверка здоровья контейнера (healthcheck.py file) перезапускает collector, если файл
# долго не обновлялся — цикл завис (сбор ограничен COLLECT_TIMEOUT_S, поэтому порог с запасом).
HEARTBEAT = Path("/tmp/collector.alive")
# версия разбора графиков: поменялась — все графики распознаются заново (подтверждённое не трогается)
KUG_PARSE = "periods-1"


def read_status(path: Path | None = None) -> dict:
    try:
        return json.loads(Path(path or status_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_status(update: dict) -> dict:
    status = {**read_status(), **update}
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return status


def _canonical(buildings) -> str:
    return json.dumps(buildings, ensure_ascii=False, sort_keys=True)


def same_as_previous(new: Path) -> bool:
    """Тот же ответ парсера, что и в последнем сохранённом снапшоте."""
    older = sorted(p for p in new.parent.glob("*.json") if p.name < new.name)
    if not older:
        return False
    try:
        return _canonical(read_snapshot(older[-1])["buildings"]) == _canonical(read_snapshot(new)["buildings"])
    except (OSError, ValueError):
        return False


def load_db() -> list[tuple[str, str]]:
    conn = connect(db_path())
    try:
        _, errors = ensure_loaded(conn, snapshots_dir())
    finally:
        conn.close()
    return errors


def run_once(reason: str = "по расписанию") -> dict:
    checked = now().isoformat(timespec="seconds")
    try:
        path = collect(parser_url(), schedule_url(), snapshots_dir(), collect_timeout_s())
    except CollectError as e:
        return _write_status({"checked_at": checked, "ok": False, "reason": reason,
                              "message": f"Сбор не удался: {e} На сайте осталась прошлая версия."})
    if same_as_previous(path):
        path.unlink(missing_ok=True)
        return _write_status({"checked_at": checked, "ok": True, "reason": reason, "last_success_at": checked,
                              "message": "Расписание на сайте вуза не изменилось."})
    errors = load_db()
    if errors:
        msg = "; ".join(f"{n}: {e}" for n, e in errors)
        return _write_status({"checked_at": checked, "ok": False, "reason": reason,
                              "message": f"Данные собраны, но не загружены: {msg}"})
    return _write_status({"checked_at": checked, "ok": True, "reason": reason, "last_success_at": checked,
                          "message": f"Загружена новая версия расписания ({path.name})."})


def next_run(after: datetime, times: list[str], days: list[int] | None = None) -> datetime:
    """Ближайшее время сбора строго после after (в его часовом поясе) в один из дней недели days."""
    days = list(range(7)) if days is None else days
    cands = []
    for day in range(8):
        d = after + timedelta(days=day)
        if d.weekday() not in days:
            continue
        for t in times:
            h, m = map(int, t.split(":"))
            dt = d.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt > after:
                cands.append(dt)
    return min(cands)


def request_collect() -> bool:
    """Запрос «проверить сайт сейчас» (из версии для руководства). False — недавно уже проверяли."""
    last = read_status().get("checked_at")
    if last and now() - datetime.fromisoformat(last) < MIN_REQUEST_INTERVAL:
        return False
    path = request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")
    return True


_kug_lock = threading.Lock()


def refresh_kug_background(force: bool = False) -> None:
    """Распознавание графиков идёт минуты — в отдельном потоке, чтобы не задерживать сбор расписания."""
    def job():
        if not _kug_lock.acquire(blocking=False):
            return
        try:
            print(refresh_kug(force), flush=True)
        finally:
            _kug_lock.release()
    threading.Thread(target=job, daemon=True).start()


def refresh_kug(force: bool = False) -> str:
    """Графики учебного процесса: новые и обновлённые на сайте вуза файлы → черновики периодов (feedback.db).
    Один раз после перехода на периоды (теория, каникулы, практика) все графики разбираются заново."""
    from feedback import store
    conn = store.connect(feedback_db_path())
    try:
        once = conn.execute("SELECT value FROM meta WHERE key = 'kug_parse'").fetchone()
        force = force or not once or once[0] != KUG_PARSE
        msg = kug.refresh(conn, directory.site_base(), kug.http_get(), force=force, head=kug.http_head())
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('kug_parse', ?)", (KUG_PARSE,))
        return msg
    except Exception as e:                                       # noqa: BLE001 — сайт недоступен и т. п.
        return f"Графики учебного процесса не проверены: {e}"
    finally:
        conn.close()


def _backup() -> None:
    try:
        print(backup.run(), flush=True)
    except Exception as e:                            # noqa: BLE001 — копия не должна останавливать сбор
        print(f"резервная копия не сделана: {e}", flush=True)


DAILY_HOUR = 4          # ежедневные задачи — после 04:00 (не в полночь и не вместе со сбором в 03:00)


def _daily() -> None:
    """Раз в сутки: справочник кафедр, графики учебного процесса (новые и заменённые), резервная копия."""
    msg = directory.refresh()                         # сам решает, пора ли (не чаще раза в сутки)
    if msg:
        print(msg, flush=True)
    refresh_kug_background()
    _backup()


def run_forever(times: list[str], days: list[int] | None = None, poll_s: float = 15) -> None:
    HEARTBEAT.touch()
    errors = load_db()
    for name, err in errors:
        print(f"снапшот {name} не загружен: {err}", flush=True)
    _daily()                                          # при старте; дальше — раз в сутки
    last_daily = now().date()
    due = next_run(now(), times, days)
    print(f"collector: сбор расписания {collect_schedule_text()}; ближайший {due:%d.%m %H:%M}; "
          f"справочник, графики и резервная копия — ежедневно после {DAILY_HOUR:02d}:00", flush=True)
    while True:
        HEARTBEAT.touch()
        kreq = kug_request_path()
        if kreq.exists():
            kreq.unlink(missing_ok=True)
            refresh_kug_background()
        req = request_path()
        if req.exists():
            req.unlink(missing_ok=True)
            print("collector: сбор по запросу", flush=True)
            print(run_once("по запросу")["message"], flush=True)
        elif now() >= due:
            print(run_once()["message"], flush=True)
            due = next_run(now(), times, days)
        if last_daily != now().date() and now().hour >= DAILY_HOUR:
            _daily()
            last_daily = now().date()
        time.sleep(poll_s)


if __name__ == "__main__":
    from config import collect_days, collect_times
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "once":
        print(run_once("вручную")["message"])
    elif cmd == "directory":
        print(directory.refresh(0))
    elif cmd == "kug":
        print(refresh_kug(force="--all" in sys.argv))
    elif cmd == "backup":
        print(backup.run())
    elif cmd == "load":
        for name, err in load_db():
            print(f"снапшот {name} не загружен: {err}")
    else:
        run_forever(collect_times(), collect_days())
