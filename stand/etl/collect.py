"""Сбор: запрос к парсеру и сохранение ответа снапшотом с датой."""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

LOCK_NAME = ".collect.lock"


class CollectError(Exception):
    """Понятное пользователю сообщение о том, почему сбор не удался."""


def collect(parser_url: str, schedule_url: str, snapshots_dir: Path, timeout_s: int = 900) -> Path:
    """Один сбор за раз: парсер на каждый запрос очищает свою папку с PDF, и два
    параллельных обхода испортили бы друг другу файлы. Блокировка старше
    таймаута считается брошенной."""
    snapshots_dir = Path(snapshots_dir)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    lock = snapshots_dir / LOCK_NAME
    if lock.exists() and time.time() - lock.stat().st_mtime > timeout_s:
        lock.unlink(missing_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as e:
        raise CollectError("Сбор уже идёт (запущен в другой вкладке или другим пользователем). "
                           "Дождитесь его окончания.") from e
    os.close(fd)
    try:
        return _collect(parser_url, schedule_url, snapshots_dir, timeout_s)
    finally:
        lock.unlink(missing_ok=True)


def _collect(parser_url: str, schedule_url: str, snapshots_dir: Path, timeout_s: int) -> Path:
    try:
        resp = requests.get(f"{parser_url.rstrip('/')}/getschedule",
                            params={"urlSchedule": schedule_url}, timeout=timeout_s)
    except requests.ConnectionError as e:
        raise CollectError(f"Парсер недоступен по адресу {parser_url}. Запущен ли контейнер parser?") from e
    except requests.Timeout as e:
        raise CollectError(f"Парсер не ответил за {timeout_s // 60} мин.") from e
    if resp.status_code != 200:
        raise CollectError(f"Парсер вернул HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        buildings = resp.json()
    except ValueError as e:
        raise CollectError("Парсер вернул не JSON.") from e
    if not isinstance(buildings, list) or not buildings:
        raise CollectError("Парсер вернул пустой результат: на сайте не найдено ни одного расписания.")

    now = datetime.now().astimezone()   # со смещением: в контейнере это UTC, и это видно
    path = snapshots_dir / f"{now:%Y-%m-%d_%H%M%S}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"collected_at": now.isoformat(timespec="seconds"),
                               "source_url": schedule_url, "buildings": buildings}, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(path)
    return path
