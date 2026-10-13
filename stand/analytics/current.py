"""Актуальное расписание — то, что видят студенты и руководство.

- Недатированные занятия (очники, очно-заочники, заочники без дат) — из последнего
  опубликованного снапшота.
- Датированные (заочники) — архив недель: для (группа, неделя сессии) берутся все опубликованные
  снапшоты, где эта неделя есть; для каждой даты — последний из них, собранный не позже этой даты
  (по часовому поясу сайта), а если такого нет — самый ранний. Будущие даты получают самую
  свежую версию, прошедшие — ту, что была на день занятия; переделки недели не суммируются.
  Неделя, которой уже нет на сайте вуза, остаётся из архива.
"""
import sqlite3
from dataclasses import dataclass

import pandas as pd

from analytics import queries as q
from etl.history import collected_date

WEEK_KEY = ["institute", "study_form", "group_name", "session_week"]


@dataclass
class Schedule:
    lessons: pd.DataFrame
    teachers: pd.DataFrame
    rooms: pd.DataFrame
    snapshot_id: int          # последний опубликованный
    collected_at: str


def published(conn: sqlite3.Connection) -> pd.DataFrame:
    """Опубликованные снапшоты от старых к новым, с днём сбора по часовому поясу сайта."""
    s = q.snapshots(conn)
    s = s[s["published"] == 1].iloc[::-1].reset_index(drop=True)
    return s.assign(day=[collected_date(c).isoformat() for c in s["collected_at"]], order=range(len(s)))


def load(conn: sqlite3.Connection) -> Schedule | None:
    pub = published(conn)
    if pub.empty:
        return None
    latest = pub.iloc[-1]
    parts = []
    for r in pub.itertuples():
        les = q.lessons_frame(conn, int(r.id))
        if r.id != latest.id:
            les = les[les["date"] != ""]
        parts.append(les.assign(_snap=r.id, _order=r.order, _day=r.day))
    allp = pd.concat(parts, ignore_index=True)
    undated = allp[(allp["_snap"] == latest.id) & (allp["date"] == "")]
    dated = allp[allp["date"] != ""]
    if not dated.empty:
        cand = dated[WEEK_KEY + ["_snap", "_order", "_day"]].drop_duplicates()
        dates = dated[WEEK_KEY + ["date"]].drop_duplicates()
        x = dates.merge(cand, on=WEEK_KEY)
        x["_known"] = x["_day"] <= x["date"]
        x = x.sort_values("_order")
        known = x[x["_known"]].groupby(WEEK_KEY + ["date"])["_snap"].last()
        earliest = x.groupby(WEEK_KEY + ["date"])["_snap"].first()
        pick = known.reindex(earliest.index).fillna(earliest).astype(int).rename("_pick").reset_index()
        dated = dated.merge(pick, on=WEEK_KEY + ["date"])
        dated = dated[dated["_snap"] == dated["_pick"]].drop(columns="_pick")
    lessons = pd.concat([undated, dated], ignore_index=True)
    snaps = sorted(set(lessons["_snap"]))
    ids = set(lessons["lesson_id"])
    teachers = pd.concat([q.teachers_frame(conn, int(s)) for s in snaps] or [q.teachers_frame(conn, -1)],
                         ignore_index=True)
    rooms = pd.concat([q.rooms_frame(conn, int(s)) for s in snaps] or [q.rooms_frame(conn, -1)], ignore_index=True)
    lessons = lessons.drop(columns=["_order", "_day"]).rename(columns={"_snap": "snapshot_id"})
    return Schedule(lessons.reset_index(drop=True), teachers[teachers["lesson_id"].isin(ids)].reset_index(drop=True),
                    rooms[rooms["lesson_id"].isin(ids)].reset_index(drop=True), int(latest.id), str(latest.collected_at))


def changes(conn: sqlite3.Connection, since: str = "") -> pd.DataFrame:
    """Изменения опубликованных снапшотов, новые сверху; since — день сбора «YYYY-MM-DD» и позже."""
    df = pd.read_sql_query(
        """SELECT c.*, s.collected_at FROM changes c JOIN snapshots s ON s.id = c.snapshot_id""", conn)
    if df.empty:
        return df.assign(day=pd.Series(dtype=str))
    df["day"] = [collected_date(x).isoformat() for x in df["collected_at"]]
    if since:
        df = df[df["day"] >= since]
    return df.sort_values(["collected_at", "group_name", "date", "day_idx", "time_from"],
                          ascending=[False, True, True, True, True]).reset_index(drop=True)
