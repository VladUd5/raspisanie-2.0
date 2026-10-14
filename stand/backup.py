"""Резервная копия того, что нельзя восстановить с сайта вуза: feedback.db (сообщения пользователей,
проверенные даты сессий, коды групп у графиков) и архив снапшотов (недели заочников, снятые с сайта).
schedule.db не копируется — стенд пересобирает её из снапшотов, directory.json — с сайта вуза.

Архив data/backups/ГГГГ-ММ-ДД.tar.gz; collector делает его раз в сутки, хранятся последние
BACKUP_KEEP_DAYS. Вручную: python collector.py backup. Восстановление — README, «Резервные копии».
"""
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from config import backup_dir, backup_keep_days, feedback_db_path, snapshots_dir
from semester import now


def archive_path(day=None) -> Path:
    return backup_dir() / f"{(day or now().date()).isoformat()}.tar.gz"


def run() -> str:
    """Делает архив за сегодня (если его ещё нет) и удаляет старые. → строка для журнала."""
    target = archive_path()
    if target.exists():
        return f"резервная копия за сегодня уже есть: {target.name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with tempfile.TemporaryDirectory() as td, tarfile.open(tmp, "w:gz") as tar:
        fb = feedback_db_path()
        if fb.exists():
            copy = Path(td) / fb.name
            src, dst = sqlite3.connect(fb, timeout=30), sqlite3.connect(copy)
            try:
                src.backup(dst)          # целостная копия, даже если сайт в этот момент пишет в базу
            finally:
                src.close()
                dst.close()
            tar.add(copy, arcname=fb.name)
        snaps = sorted(snapshots_dir().glob("*.json"))
        for p in snaps:
            tar.add(p, arcname=f"snapshots/{p.name}")
    tmp.replace(target)
    old = sorted(backup_dir().glob("*.tar.gz"))[:-backup_keep_days()]
    for p in old:
        p.unlink(missing_ok=True)
    return f"резервная копия {target.name}: {target.stat().st_size // 1024} КБ, снапшотов {len(snaps)}" + \
        (f", удалено старых {len(old)}" if old else "")
