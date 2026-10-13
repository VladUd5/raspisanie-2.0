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


# --- прод -----------------------------------------------------------------------

def tz_name() -> str:
    return os.environ.get("TZ_NAME", "Europe/Saratov")


def env_date(name: str) -> str:
    """Дата из окружения «YYYY-MM-DD» или «MM-DD» (каждый год); пустая — не задана."""
    return os.environ.get(name, "").strip()


def feedback_db_path() -> Path:
    return Path(os.environ.get("FEEDBACK_DB_PATH", data_dir() / "feedback.db"))


def status_path() -> Path:
    return data_dir() / "status.json"


def request_path() -> Path:
    """Файл-запрос «проверить сайт сейчас»: создаёт версия руководства, забирает collector."""
    return data_dir() / "collect.request"


def collect_times() -> list[str]:
    return [t.strip() for t in os.environ.get("COLLECT_TIMES", "03:00,13:00").split(",") if t.strip()]


def publish_min_ratio() -> float:
    return float(os.environ.get("PUBLISH_MIN_RATIO", "0.7"))


def major_change_ratio() -> float:
    return float(os.environ.get("MAJOR_CHANGE_RATIO", "0.3"))


def change_badge_days() -> int:
    return int(os.environ.get("CHANGE_BADGE_DAYS", "7"))


def reports_per_hour() -> int:
    return int(os.environ.get("REPORTS_PER_HOUR", "5"))


def site_title() -> str:
    return os.environ.get("SITE_TITLE", "Расписание занятий — Вавиловский университет")


def public_url() -> str:
    """Публичный адрес студенческой версии (для ссылок в календаре); пустой — относительные."""
    return os.environ.get("PUBLIC_URL", "").rstrip("/")


def staff_base_path() -> str:
    return os.environ.get("STAFF_BASE_PATH", "rukovodstvo").strip("/")
