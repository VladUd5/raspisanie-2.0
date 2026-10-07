"""Кэшируемое чтение данных из SQLite.

Ключ кэша — (путь к БД, время изменения файла БД, …): новая загрузка снапшота
меняет файл и автоматически инвалидирует кэш. Параметры без подчёркивания —
Streamlit не хэширует аргументы, имя которых начинается с «_».
"""
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from analytics import queries as q
from config import db_path
from etl.load import connect


@dataclass
class Frames:
    lessons: pd.DataFrame
    teachers: pd.DataFrame
    rooms: pd.DataFrame


def db_key() -> tuple[str, float]:
    p = db_path()
    return str(p), (p.stat().st_mtime if p.exists() else 0.0)


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


def snapshots() -> pd.DataFrame:
    return _snapshots(*db_key())


def frames(snapshot_id: int) -> Frames:
    return _frames(*db_key(), snapshot_id)


def quality(snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quality(*db_key(), snapshot_id)


def spellings(snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _spellings(*db_key(), snapshot_id)
