"""Кэшируемое чтение данных из SQLite.

Ключ кэша — (путь к БД, время изменения файла БД, …): новая загрузка снапшота
меняет файл и автоматически инвалидирует кэш. Параметры без подчёркивания —
Streamlit не хэширует аргументы, имя которых начинается с «_».
"""
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from analytics import current as cur
from analytics import queries as q
from config import db_path
from etl.load import connect


@dataclass
class Frames:
    lessons: pd.DataFrame
    teachers: pd.DataFrame
    rooms: pd.DataFrame


def db_key() -> tuple[str, float]:
    """В режиме WAL запись сначала попадает в файл -wal: версия — по обоим файлам."""
    p = db_path()
    wal = p.with_name(p.name + "-wal")
    return str(p), max(x.stat().st_mtime if x.exists() else 0.0 for x in (p, wal))


def conn():
    return connect(db_path())


@st.cache_data(show_spinner=False)
def _snapshots(db: str, version: float) -> pd.DataFrame:
    c = connect(db)
    try:
        return q.snapshots(c)
    finally:
        c.close()


@st.cache_data(show_spinner="Читаю данные снапшота…")
def _frames(db: str, version: float, snapshot_id: int) -> Frames:
    c = connect(db)
    try:
        return Frames(q.lessons_frame(c, snapshot_id), q.teachers_frame(c, snapshot_id), q.rooms_frame(c, snapshot_id))
    finally:
        c.close()


@st.cache_data(show_spinner=False)
def _quality(db: str, version: float, snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = connect(db)
    try:
        return q.cells_quality_frame(c, snapshot_id), q.service_cells(c, snapshot_id)
    finally:
        c.close()


@st.cache_data(show_spinner=False)
def _spellings(db: str, version: float, snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = connect(db)
    try:
        return q.spellings_frame(c, snapshot_id), q.rule_audit_frame(c, snapshot_id)
    finally:
        c.close()


@st.cache_data(show_spinner="Читаю актуальное расписание…")
def _current(db: str, version: float) -> tuple[Frames, int, str] | None:
    c = connect(db)
    try:
        s = cur.load(c)
    finally:
        c.close()
    if s is None:
        return None
    return Frames(s.lessons, s.teachers, s.rooms), s.snapshot_id, s.collected_at


@st.cache_data(show_spinner=False)
def _changes(db: str, version: float) -> pd.DataFrame:
    c = connect(db)
    try:
        return cur.changes(c)
    finally:
        c.close()


def current() -> tuple[Frames, int, str] | None:
    """Актуальное расписание (последний опубликованный снапшот + архив недель заочников),
    id последнего опубликованного снапшота и время его сбора; None — данных нет."""
    return _current(*db_key())


def changes() -> pd.DataFrame:
    return _changes(*db_key())


def snapshots() -> pd.DataFrame:
    return _snapshots(*db_key())


def frames(snapshot_id: int) -> Frames:
    return _frames(*db_key(), snapshot_id)


def quality(snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quality(*db_key(), snapshot_id)


def spellings(snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _spellings(*db_key(), snapshot_id)


CHANGE_KINDS = {"added": "добавлено", "removed": "отменено", "changed": "изменено", "moved": "перенесено",
                "week_published": "новая неделя сессии", "week_removed": "неделя снята с сайта",
                "major_update": "новое расписание формы"}
