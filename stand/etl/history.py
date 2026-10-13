"""Публикация снапшотов и журнал изменений.

Снапшоты обрабатываются по времени сбора. Снапшот, в котором занятий заметно меньше, чем в
последнем опубликованном (сайт вуза лёг, PDF не скачались), не публикуется: студенты продолжают
видеть прошлую версию, руководство — предупреждение. Каждый опубликованный снапшот сравнивается
с предыдущим опубликованным; изменения пишутся в таблицу changes.
"""
import sqlite3
from datetime import date

import pandas as pd

from analytics import queries as q
from config import major_change_ratio, publish_min_ratio
from etl import diff


def collected_date(collected_at: str) -> date:
    """День сбора по часовому поясу сайта (в контейнере время пишется в UTC)."""
    from semester import tz
    ts = pd.Timestamp(collected_at)
    if ts.tzinfo is None:
        ts = ts.tz_localize(tz())
    return ts.tz_convert(tz()).date()


def _ordered(conn: sqlite3.Connection) -> pd.DataFrame:
    """Снапшоты от старых к новым (q.snapshots сортирует новые сверху)."""
    return q.snapshots(conn).iloc[::-1].reset_index(drop=True)


def reset(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM changes")
    conn.execute("UPDATE snapshots SET published = NULL, note = NULL")


def slots_of(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return diff.slots(q.lessons_frame(conn, snapshot_id), q.teachers_frame(conn, snapshot_id),
                      q.rooms_frame(conn, snapshot_id))


def refresh(conn: sqlite3.Connection, min_ratio: float | None = None, major_ratio: float | None = None) -> int:
    """Обработать снапшоты без статуса. Если среди них есть более ранний, чем уже обработанные
    (файл положили задним числом), всё пересчитывается. → сколько снапшотов обработано."""
    min_ratio = publish_min_ratio() if min_ratio is None else min_ratio
    major_ratio = major_change_ratio() if major_ratio is None else major_ratio
    snaps = _ordered(conn)
    pending = snaps["published"].isna()
    if not pending.any():
        return 0
    first_pending = pending.idxmax()
    if (~pending[first_pending:]).any():
        conn.execute("BEGIN IMMEDIATE")
        reset(conn)
        conn.commit()
        snaps = _ordered(conn)
        first_pending = 0
    prev = None   # последний опубликованный до обрабатываемого
    for r in snaps.iloc[:first_pending].itertuples():
        if r.published == 1:
            prev = r
    done = 0
    for r in snaps.iloc[first_pending:].itertuples():
        conn.execute("BEGIN IMMEDIATE")
        try:
            if prev is not None and r.lessons_cnt < min_ratio * prev.lessons_cnt:
                conn.execute("UPDATE snapshots SET published = 0, note = ? WHERE id = ?",
                             (f"Сбор выглядит неполным: {r.lessons_cnt} занятий против {prev.lessons_cnt} "
                              "в прошлой версии. Не опубликован, на сайте осталась прошлая версия.", r.id))
            else:
                if prev is not None:
                    ch = diff.compare(slots_of(conn, prev.id), slots_of(conn, r.id),
                                      collected_date(r.collected_at), major_ratio)
                    _insert_changes(conn, ch.assign(snapshot_id=r.id, prev_snapshot_id=prev.id))
                conn.execute("UPDATE snapshots SET published = 1, note = NULL WHERE id = ?", (r.id,))
                prev = r
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        done += 1
    return done


def _insert_changes(conn: sqlite3.Connection, ch: pd.DataFrame) -> None:
    """Своя вставка, а не DataFrame.to_sql: та коммитит сама и разорвала бы транзакцию."""
    if ch.empty:
        return
    cols = list(ch.columns)
    rows = [tuple(None if pd.isna(v) else (int(v) if hasattr(v, "item") and isinstance(v.item(), int) else v)
                  for v in row) for row in ch.itertuples(index=False)]
    conn.executemany(f"INSERT INTO changes ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
