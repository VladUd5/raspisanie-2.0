"""Настройки стенда. Читаются из переменных окружения при каждом обращении,
чтобы тесты и Docker могли подменять пути."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", ROOT / "data"))


def snapshots_dir() -> Path:
    return Path(os.environ.get("SNAPSHOTS_DIR", data_dir() / "snapshots"))


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", data_dir() / "schedule.db"))


def parser_url() -> str:
    return os.environ.get("PARSER_URL", "http://localhost:8080")


def schedule_url() -> str:
    return os.environ.get("SCHEDULE_URL", "www.vavilovsar.ru/ucheba/raspisanie-zanyatii")


def collect_timeout_s() -> int:
    return int(os.environ.get("COLLECT_TIMEOUT_S", "900"))
