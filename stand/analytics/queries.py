"""Агрегаты для отчётов. Чистые функции над DataFrame, без Streamlit.

Поточная лекция для нескольких групп приходит от парсера отдельной ячейкой в
каждой группе. Чтобы не засчитать её преподавателю или аудитории N раз,
нагрузка считается по уникальным событиям: одинаковые (кто/где, день, время,
тип недели, тип занятия, дисциплина) — это одно событие.

Загруженность слота «день × время» у преподавателя и аудитории не больше одной
пары в неделю: числитель + знаменатель как раз дают 1, а наложения (ошибки
расписания, сессии заочников в «тот же» день) срезаются пропорционально.
"""
import sqlite3
from dataclasses import dataclass

import pandas as pd

from etl.locations import ADJACENT
from labels import DAYS

SLOT_KEY = ["day_idx", "time_from", "week_type", "lesson_type", "discipline"]


@dataclass(frozen=True)
class Filters:
    buildings: tuple[str, ...] = ()
    institutes: tuple[str, ...] = ()
    study_forms: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    days: tuple[str, ...] = ()
    week_types: tuple[str, ...] = ()
    lesson_types: tuple[str, ...] = ()
    full_weeks: bool = False   # числитель/знаменатель и разрезанные ячейки — полной парой


# --- чтение -------------------------------------------------------------------

def snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    """Новые сверху. Время сбора может быть записано в разных поясах (в контейнере —
    UTC), поэтому сортировка по разобранному времени, а не по строке."""
    df = pd.read_sql_query("SELECT * FROM snapshots", conn)
    when = pd.to_datetime(df["collected_at"], utc=True, errors="coerce", format="ISO8601")
    return df.assign(_when=when).sort_values(["_when", "id"], ascending=False).drop(columns="_when").reset_index(drop=True)


def lessons_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT l.id AS lesson_id, l.cell_id, c.building AS cell_building, c.institute, c.study_form,
                  c.group_name, c.day, c.day_idx, c.time_from, c.time_to, c.duration_h, c.week_type,
                  l.week_factor, l.lesson_type, COALESCE(d.name, '—') AS discipline, l.subgroup,
                  l.building AS lesson_building, c.subject_raw
           FROM lessons l JOIN cells c ON c.id = l.cell_id
           LEFT JOIN disciplines d ON d.id = l.discipline_id
           WHERE l.snapshot_id = ?""", conn, params=(snapshot_id,))


def teachers_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT lt.lesson_id, t.full_name AS teacher FROM lesson_teachers lt
           JOIN teachers t ON t.id = lt.teacher_id WHERE t.snapshot_id = ?""", conn, params=(snapshot_id,))


def rooms_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT lr.lesson_id, r.building AS room_building, r.name AS room FROM lesson_rooms lr
           JOIN rooms r ON r.id = lr.room_id WHERE r.snapshot_id = ?""", conn, params=(snapshot_id,))


def cells_quality_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    """Одна строка на занятие с исходным текстом и всеми флагами качества."""
    return pd.read_sql_query(
        """SELECT c.institute, c.group_name, c.day, c.time_from, c.subject_raw, c.lessons_in_cell,
                  l.lesson_type, COALESCE(d.name, '') AS discipline,
                  (SELECT GROUP_CONCAT(t.full_name, ', ') FROM lesson_teachers lt JOIN teachers t ON t.id = lt.teacher_id
                   WHERE lt.lesson_id = l.id) AS teachers,
                  (SELECT GROUP_CONCAT(r.name, ', ') FROM lesson_rooms lr JOIN rooms r ON r.id = lr.room_id
                   WHERE lr.lesson_id = l.id) AS rooms,
                  q.*
           FROM lessons l JOIN cells c ON c.id = l.cell_id JOIN quality q ON q.lesson_id = l.id
           LEFT JOIN disciplines d ON d.id = l.discipline_id
           WHERE l.snapshot_id = ?""", conn, params=(snapshot_id,))


def service_cells(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT institute, group_name, day, time_from, subject_raw FROM cells WHERE snapshot_id = ? AND is_service = 1",
        conn, params=(snapshot_id,))


def spellings_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT kind, spelling, canonical, source, confidence, error_kinds, note, lessons AS uses, score"
        " FROM spellings WHERE snapshot_id = ?", conn, params=(snapshot_id,))


def rule_audit_frame(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT kind, tp, fp, fn FROM rule_audit WHERE snapshot_id = ?",
                           conn, params=(snapshot_id,))
    df["precision"] = (100 * df["tp"] / (df["tp"] + df["fp"])).fillna(100.0).round(1)
    df["recall"] = (100 * df["tp"] / (df["tp"] + df["fn"])).fillna(100.0).round(1)
    return df


# --- фильтры и часы -------------------------------------------------------------

def apply_filters(lessons: pd.DataFrame, f: Filters) -> pd.DataFrame:
    mask = pd.Series(True, index=lessons.index)
    for col, values in [("cell_building", f.buildings), ("institute", f.institutes),
                        ("study_form", f.study_forms), ("group_name", f.groups), ("day", f.days),
                        ("week_type", f.week_types), ("lesson_type", f.lesson_types)]:
        if values:
            mask &= lessons[col].isin(values)
    out = lessons[mask].copy()
    out["hours"] = out["duration_h"] * (1.0 if f.full_weeks else out["week_factor"])
    out["per_week"] = 1.0 if f.full_weeks else out["week_factor"]
    return out


def _events(df: pd.DataFrame, who: list[str]) -> pd.DataFrame:
    return df.drop_duplicates(subset=who + SLOT_KEY)


def _occupancy(df: pd.DataFrame, who: list[str]) -> pd.DataFrame:
    """Уникальные события, у которых per_week/hours срезаны так, чтобы сумма по
    слоту (кто/где, день, время) не превышала одной пары в неделю."""
    ev = _events(df, who).copy()
    if ev.empty:
        return ev
    total = ev.groupby(who + ["day_idx", "time_from"])["per_week"].transform("sum")
    scale = (1.0 / total).clip(upper=1.0)
    ev["per_week"] = ev["per_week"] * scale
    ev["hours"] = ev["per_week"] * ev["duration_h"]
    return ev


# --- преподаватели --------------------------------------------------------------

def teacher_load(lessons: pd.DataFrame, teachers: pd.DataFrame, rooms: pd.DataFrame) -> pd.DataFrame:
    """Недельная нагрузка каждого преподавателя по всем институтам и формам в выборке."""
    df = lessons.merge(teachers, on="lesson_id")
    if df.empty:
        return pd.DataFrame(columns=["teacher", "hours", "lessons", "disciplines", "groups", "rooms"])
    ev = _occupancy(df, ["teacher"])
    out = ev.groupby("teacher").agg(hours=("hours", "sum"), lessons=("per_week", "sum"))
    out["disciplines"] = df.groupby("teacher")["discipline"].nunique()
    out["groups"] = df.groupby("teacher")["group_name"].nunique()
    room_counts = df.merge(rooms, on="lesson_id").groupby("teacher").apply(
        lambda g: len(set(zip(g["room_building"], g["room"]))), include_groups=False)
    out["rooms"] = room_counts.reindex(out.index).fillna(0).astype(int)
    return out.reset_index().sort_values(["hours", "teacher"], ascending=[False, True], ignore_index=True)


def teacher_heatmap(lessons: pd.DataFrame, teachers: pd.DataFrame, teacher: str) -> pd.DataFrame:
    df = lessons.merge(teachers[teachers["teacher"] == teacher], on="lesson_id")
    return _day_time_pivot(_occupancy(df, ["teacher"]))


def teacher_by_type(lessons: pd.DataFrame, teachers: pd.DataFrame, teacher: str) -> pd.DataFrame:
    df = lessons.merge(teachers[teachers["teacher"] == teacher], on="lesson_id")
    ev = _occupancy(df, ["teacher"])
    return ev.groupby("lesson_type", as_index=False)["hours"].sum().sort_values("hours", ascending=False)


def teacher_schedule(lessons: pd.DataFrame, teachers: pd.DataFrame, rooms: pd.DataFrame, teacher: str) -> pd.DataFrame:
    """Занятия преподавателя на неделю: одна строка на событие, группы потока — через запятую."""
    df = lessons.merge(teachers[teachers["teacher"] == teacher], on="lesson_id")
    if df.empty:
        return pd.DataFrame(columns=["day", "time_from", "week_type", "lesson_type", "discipline", "groups", "rooms", "hours"])
    room_txt = _room_text(rooms)
    df = df.merge(room_txt, on="lesson_id", how="left")
    out = df.groupby(SLOT_KEY + ["day"], as_index=False, dropna=False).agg(
        groups=("group_name", lambda s: ", ".join(sorted(set(s)))),
        rooms=("rooms", lambda s: ", ".join(sorted({x for x in s if isinstance(x, str)}))),
        hours=("hours", "max"))
    return out.sort_values(["day_idx", "time_from"])[
        ["day", "time_from", "week_type", "lesson_type", "discipline", "groups", "rooms", "hours"]]


# --- аудитории ------------------------------------------------------------------

def _rooms_scope(lessons: pd.DataFrame, rooms: pd.DataFrame, scope: str) -> pd.DataFrame:
    df = lessons.merge(rooms, on="lesson_id")
    if scope == "main":
        df = df[df["room_building"] != ADJACENT]
    elif scope == "adjacent":
        df = df[df["room_building"] == ADJACENT]
    df = df.copy()
    df["room_label"] = df["room_building"] + " · " + df["room"]
    return df


def room_load(lessons: pd.DataFrame, rooms: pd.DataFrame, scope: str = "all") -> pd.DataFrame:
    df = _rooms_scope(lessons, rooms, scope)
    if df.empty:
        return pd.DataFrame(columns=["room_label", "room_building", "room", "hours", "lessons", "disciplines", "groups"])
    ev = _occupancy(df, ["room_label"])
    out = ev.groupby(["room_label", "room_building", "room"]).agg(hours=("hours", "sum"), lessons=("per_week", "sum"))
    out["disciplines"] = df.groupby(["room_label", "room_building", "room"])["discipline"].nunique()
    out["groups"] = df.groupby(["room_label", "room_building", "room"])["group_name"].nunique()
    return out.reset_index().sort_values(["hours", "room_label"], ascending=[False, True], ignore_index=True)


def room_discipline_matrix(lessons: pd.DataFrame, rooms: pd.DataFrame, scope: str = "all") -> pd.DataFrame:
    """Часы в неделю: строки — аудитории, столбцы — дисциплины (без занятий, где
    дисциплина не распознана)."""
    df = _rooms_scope(lessons, rooms, scope)
    df = df[df["discipline"] != "—"]
    if df.empty:
        return pd.DataFrame()
    ev = _occupancy(df, ["room_label"])
    m = ev.pivot_table(index="room_label", columns="discipline", values="hours", aggfunc="sum", fill_value=0.0)
    return m.loc[m.sum(axis=1).sort_values(ascending=False).index, m.sum().sort_values(ascending=False).index]


def room_heatmap(lessons: pd.DataFrame, rooms: pd.DataFrame, room_label: str) -> pd.DataFrame:
    df = _rooms_scope(lessons, rooms, "all")
    return _day_time_pivot(_occupancy(df[df["room_label"] == room_label], ["room_label"]))


# --- дисциплины и группы -----------------------------------------------------------

def discipline_summary(lessons: pd.DataFrame, teachers: pd.DataFrame) -> pd.DataFrame:
    tt = teachers.groupby("lesson_id")["teacher"].apply(lambda s: ", ".join(sorted(s))).rename("teachers_key")
    df = lessons.merge(tt, on="lesson_id", how="left").fillna({"teachers_key": ""})
    if df.empty:
        return pd.DataFrame(columns=["discipline", "hours", "lessons", "teachers", "groups"])
    ev = _events(df, ["teachers_key"])
    out = ev.groupby("discipline").agg(hours=("hours", "sum"), lessons=("per_week", "sum"))
    out["teachers"] = df.merge(teachers, on="lesson_id").groupby("discipline")["teacher"].apply(
        lambda s: ", ".join(sorted(set(s))))
    out["groups"] = df.groupby("discipline")["group_name"].nunique()
    out = out.fillna({"teachers": ""})
    return out.reset_index().sort_values(["hours", "discipline"], ascending=[False, True], ignore_index=True)


def discipline_by_type(lessons: pd.DataFrame, teachers: pd.DataFrame, disciplines: list[str]) -> pd.DataFrame:
    tt = teachers.groupby("lesson_id")["teacher"].apply(lambda s: ", ".join(sorted(s))).rename("teachers_key")
    df = lessons[lessons["discipline"].isin(disciplines)].merge(tt, on="lesson_id", how="left")
    ev = _events(df.fillna({"teachers_key": ""}), ["teachers_key"])
    return ev.groupby(["discipline", "lesson_type"], as_index=False)["hours"].sum()


def group_grid(lessons: pd.DataFrame, teachers: pd.DataFrame, rooms: pd.DataFrame, group: str) -> pd.DataFrame:
    """Сетка день × время с текстом занятий для одной группы."""
    df = lessons[lessons["group_name"] == group]
    if df.empty:
        return pd.DataFrame()
    tt = teachers.groupby("lesson_id")["teacher"].apply(", ".join).rename("teachers")
    df = df.merge(tt, on="lesson_id", how="left").merge(_room_text(rooms), on="lesson_id", how="left")
    week = {"numerator": " [числ.]", "denominator": " [знам.]", "both": ""}

    def text(r) -> str:
        parts = [f"{r.lesson_type}: {r.discipline}{week[r.week_type]}"]
        if isinstance(r.teachers, str):
            parts.append(r.teachers)
        if isinstance(r.rooms, str):
            parts.append(f"ауд. {r.rooms}")
        return " · ".join(parts)

    df = df.assign(text=df.apply(text, axis=1)).sort_values(["day_idx", "time_from", "week_type"])
    grid = df.pivot_table(index="time_from", columns="day_idx", values="text", aggfunc=" ║ ".join)
    grid.columns = [DAYS[i] if i < len(DAYS) else "?" for i in grid.columns]
    return grid.fillna("")


def group_daily_load(lessons: pd.DataFrame, group: str) -> pd.DataFrame:
    df = lessons[lessons["group_name"] == group]
    out = df.groupby(["day_idx", "day"], as_index=False)["hours"].sum().sort_values("day_idx")
    return out[["day", "hours"]]


# --- обзор и качество ---------------------------------------------------------------

def overview_counts(lessons: pd.DataFrame, teachers: pd.DataFrame, rooms: pd.DataFrame) -> dict[str, int]:
    ids = set(lessons["lesson_id"])
    return {
        "institutes": lessons["institute"].nunique(),
        "groups": lessons[["institute", "study_form", "group_name"]].drop_duplicates().shape[0],
        "lessons": len(lessons),
        "disciplines": lessons.loc[lessons["discipline"] != "—", "discipline"].nunique(),
        "teachers": teachers.loc[teachers["lesson_id"].isin(ids), "teacher"].nunique(),
        "rooms": rooms.loc[rooms["lesson_id"].isin(ids), ["room_building", "room"]].drop_duplicates().shape[0],
    }


def lessons_by_institute(lessons: pd.DataFrame) -> pd.DataFrame:
    return (lessons.groupby("institute", as_index=False).size().rename(columns={"size": "count"})
            .sort_values("count", ascending=False))


QUALITY_FIELDS = {"has_type": "тип занятия", "has_discipline": "дисциплина",
                  "has_teacher": "преподаватель", "has_room": "аудитория"}
FLAG_FIELDS = {"discipline_fuzzy": "дисциплина склеена fuzzy", "teacher_surname_only": "преподаватель без инициалов",
               "split_cell": "ячейка разрезана", "suspicious_group": "подозрительная группа",
               "truncated": "оборванная ячейка", "unverified_name": "написание не проверено",
               "needs_review": "требует проверки"}


def quality_shares(q: pd.DataFrame) -> pd.DataFrame:
    """Доля занятий (в %) с распознанным полем и с каждым флагом."""
    rows = [("распознано", label, 100 * q[col].mean()) for col, label in QUALITY_FIELDS.items()]
    rows += [("флаг", label, 100 * q[col].mean()) for col, label in FLAG_FIELDS.items()]
    return pd.DataFrame(rows, columns=["kind", "field", "share"])


def teacher_conflicts(lessons: pd.DataFrame, teachers: pd.DataFrame) -> pd.DataFrame:
    """Слоты, где у преподавателя в одну неделю стоят разные занятия одновременно.

    Занятия из одной разрезанной ячейки — чередование, а не наложение: считаются
    только слоты, где события пришли из разных ячеек.
    """
    df = lessons.merge(teachers, on="lesson_id")
    ev = _events(df, ["teacher"])
    if ev.empty:
        return pd.DataFrame(columns=["teacher", "day", "time_from", "week_type", "events", "disciplines", "groups"])
    g = ev.groupby(["teacher", "day_idx", "day", "time_from", "week_type"], as_index=False).agg(
        events=("lesson_id", "size"), cells=("cell_id", "nunique"),
        disciplines=("discipline", lambda s: ", ".join(sorted(set(s)))),
        groups=("group_name", lambda s: ", ".join(sorted(set(s)))))
    g = g[(g["events"] > 1) & (g["cells"] > 1)].sort_values(["events", "teacher"], ascending=[False, True])
    return g.drop(columns=["day_idx", "cells"]).reset_index(drop=True)


def day_shift_warnings(lessons: pd.DataFrame) -> pd.DataFrame:
    """Группы с занятиями в воскресенье — признак сдвига дней недели в парсере."""
    bad = lessons[lessons["day_idx"] >= 6]
    return bad[["institute", "study_form", "group_name"]].drop_duplicates()


# --- вспомогательное ---------------------------------------------------------------

def _room_text(rooms: pd.DataFrame) -> pd.DataFrame:
    return rooms.groupby("lesson_id")["room"].apply(lambda s: ", ".join(s)).rename("rooms").reset_index()


def _day_time_pivot(ev: pd.DataFrame) -> pd.DataFrame:
    if ev.empty:
        return pd.DataFrame()
    p = ev.pivot_table(index="day_idx", columns="time_from", values="hours", aggfunc="sum", fill_value=0.0)
    p.index = [DAYS[i] if i < len(DAYS) else "?" for i in p.index]
    return p[sorted(p.columns)]
