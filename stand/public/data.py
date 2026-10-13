"""Данные студенческой версии: актуальное расписание в памяти процесса.

Перечитывается, когда меняется schedule.db (в режиме WAL запись сначала попадает в файл -wal,
поэтому смотрим на время изменения обоих файлов). Чтение базы — только здесь.
"""
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from analytics import current
from config import change_badge_days, db_path
from etl.load import connect
from semester import today


@dataclass
class Data:
    items: pd.DataFrame              # одна строка на занятие группы: teachers — кортеж, rooms — кортеж (корпус, номер)
    changes: pd.DataFrame            # изменения за последние CHANGE_BADGE_DAYS дней
    all_changes: pd.DataFrame        # все изменения (страница «Изменения»)
    snapshot_id: int
    collected_at: str
    index: list[dict] = field(default_factory=list)   # для поиска: kind, label, url, hint, norm


def _items(s: current.Schedule) -> pd.DataFrame:
    les = s.lessons
    tt = s.teachers.groupby("lesson_id")["teacher"].apply(lambda x: tuple(sorted(set(x)))).rename("teachers")
    rr = s.rooms.groupby("lesson_id").apply(
        lambda g: tuple(sorted(set(zip(g["room_building"], g["room"])))), include_groups=False).rename("rooms")
    df = les.merge(tt, on="lesson_id", how="left").merge(rr, on="lesson_id", how="left")
    df["teachers"] = [t if isinstance(t, tuple) else () for t in df["teachers"]]
    df["rooms"] = [r if isinstance(r, tuple) else () for r in df["rooms"]]
    df["subgroup"] = pd.to_numeric(df["subgroup"], errors="coerce").fillna(0).astype(int)
    df["discipline"] = df["discipline"].replace("—", "")
    return df[df["group_name"].str.strip() != ""].reset_index(drop=True)


def norm(s: str) -> str:
    """Для поиска: регистр, ё, пробелы, точки и дефисы не важны."""
    return re.sub(r"[\s.\-_,]", "", (s or "").casefold().replace("ё", "е"))


def _index(items: pd.DataFrame) -> list[dict]:
    from public.urls import group_url, room_url, teacher_url
    out = []
    for g, part in items.groupby("group_name"):
        hint = ", ".join(sorted({f"{f.lower()}" for f in part["study_form"]}))
        out.append({"kind": "группа", "label": g, "url": group_url(g), "hint": hint})
    for t in sorted({t for ts in items["teachers"] for t in ts}):
        out.append({"kind": "преподаватель", "label": t, "url": teacher_url(t), "hint": ""})
    for b, r in sorted({x for rs in items["rooms"] for x in rs}):
        out.append({"kind": "аудитория", "label": f"{b}, {r}", "url": room_url(b, r), "hint": ""})
    for e in out:
        e["norm"] = norm(e["label"])
    return out


def search(index: list[dict], q: str, limit: int = 12) -> list[dict]:
    n = norm(q)
    if not n:
        return []
    order = {"группа": 0, "преподаватель": 1, "аудитория": 2}
    scored = []
    for e in index:
        if e["norm"].startswith(n):
            score = 300
        elif n in e["norm"]:
            score = 200
        elif len(n) >= 3:
            score = fuzz.partial_ratio(n, e["norm"])
            if score < 80:
                continue
        else:
            continue
        scored.append((-score, order[e["kind"]], len(e["label"]), e["label"], e))
    return [e for *_, e in sorted(scored, key=lambda x: x[:4])[:limit]]


class Store:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._lock = threading.Lock()
        self._key = None
        self._data: Data | None = None

    @property
    def path(self) -> Path:
        return Path(self._path or db_path())

    def _mtime(self):
        p = self.path
        return tuple(x.stat().st_mtime if x.exists() else 0 for x in (p, p.with_name(p.name + "-wal")))

    def get(self) -> Data | None:
        key = self._mtime()
        if key[0] == 0:
            return None
        with self._lock:
            if key != self._key:
                self._data = self._load()
                self._key = key
            return self._data

    def _load(self) -> Data | None:
        try:
            conn = connect(self.path)
        except sqlite3.Error:
            return self._data
        try:
            s = current.load(conn)
            if s is None:
                return None
            ch = current.changes(conn)
        except sqlite3.Error:
            return self._data
        finally:
            conn.close()
        items = _items(s)
        if not ch.empty:                                     # строки без группы — мусор старого разбора
            ch = ch[(ch["group_name"].str.strip() != "") | ~ch["kind"].isin(["added", "removed", "changed", "moved"])]
            ch = ch.reset_index(drop=True)
        since = (today() - timedelta(days=change_badge_days())).isoformat()
        recent = ch[ch["day"] >= since] if not ch.empty else ch
        return Data(items, recent, ch, s.snapshot_id, s.collected_at, _index(items))


def week_options(items: pd.DataFrame) -> list[date]:
    """Недели сессии с занятиями (понедельники)."""
    return sorted({date.fromisoformat(w) for w in items["session_week"] if w})
