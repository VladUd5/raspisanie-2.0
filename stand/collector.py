"""Сбор по расписанию (контейнер collector) — единственный писатель schedule.db в проде.

    python collector.py run    — цикл: сбор в COLLECT_TIMES (по часовому поясу сайта) и по запросу
                                 «проверить сайт сейчас» из версии для руководства
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
from config import (collect_timeout_s, db_path, feedback_db_path, kug_request_path, parser_url, request_path,
                    schedule_url, snapshots_dir, status_path)
from etl.collect import CollectError, collect
from etl.load import connect, ensure_loaded, read_snapshot
from semester import now

MIN_REQUEST_INTERVAL = timedelta(minutes=10)   # «проверить сейчас» не чаще
# Пульс цикла: проверка здоровья контейнера (healthcheck.py file) перезапускает collector, если файл
# долго не обновлялся — цикл завис (сбор ограничен COLLECT_TIMEOUT_S, поэтому порог с запасом).
HEARTBEAT = Path("/tmp/collector.alive")


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


def next_run(after: datetime, times: list[str]) -> datetime:
    """Ближайшее время сбора строго после after (в его часовом поясе)."""
    cands = []
    for day in (0, 1):
        for t in times:
            h, m = map(int, t.split(":"))
            dt = (after + timedelta(days=day)).replace(hour=h, minute=m, second=0, microsecond=0)
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
    """Графики учебного процесса: новые файлы на сайте вуза → черновики сессий (feedback.db)."""
    from feedback import store
    conn = store.connect(feedback_db_path())
    try:
        return kug.refresh(conn, directory.site_base(), kug.http_get(), force=force)
    except Exception as e:                                       # noqa: BLE001 — сайт недоступен и т. п.
        return f"Графики учебного процесса не проверены: {e}"
    finally:
        conn.close()


def _backup() -> None:
    try:
        print(backup.run(), flush=True)
    except Exception as e:                            # noqa: BLE001 — копия не должна останавливать сбор
        print(f"резервная копия не сделана: {e}", flush=True)


def run_forever(times: list[str], poll_s: float = 15) -> None:
    HEARTBEAT.touch()
    errors = load_db()
    for name, err in errors:
        print(f"снапшот {name} не загружен: {err}", flush=True)
    msg = directory.refresh()
    if msg:
        print(msg, flush=True)
    refresh_kug_background()                          # при старте: только новые файлы, в фоне
    last_kug = now().date()
    _backup()                                         # при старте — если за сегодня копии ещё нет
    due = next_run(now(), times)
    print(f"collector: сбор в {', '.join(times)}; ближайший {due:%d.%m %H:%M}", flush=True)
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
            due = next_run(now(), times)
            msg = directory.refresh()                    # не чаще раза в сутки
            if msg:
                print(msg, flush=True)
            if last_kug != now().date():                  # раз в сутки: только новые файлы
                refresh_kug_background()
                last_kug = now().date()
            _backup()                                     # раз в сутки (за день — один архив)
        time.sleep(poll_s)


if __name__ == "__main__":
    from config import collect_times
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
        run_forever(collect_times())
