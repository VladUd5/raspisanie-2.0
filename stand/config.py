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


def backup_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR", data_dir() / "backups"))


def backup_keep_days() -> int:
    return max(1, int(os.environ.get("BACKUP_KEEP_DAYS", "14")))


def feedback_db_path() -> Path:
    return Path(os.environ.get("FEEDBACK_DB_PATH", data_dir() / "feedback.db"))


def status_path() -> Path:
    return data_dir() / "status.json"


def request_path() -> Path:
    """Файл-запрос «проверить сайт сейчас»: создаёт версия руководства, забирает collector."""
    return data_dir() / "collect.request"


def collect_times() -> list[str]:
    return [t.strip() for t in os.environ.get("COLLECT_TIMES", "03:00").split(",") if t.strip()]


DAY_CODES = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6,
             "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DAY_NAMES = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]


def collect_days() -> list[int]:
    """Дни сбора расписания (0 — понедельник): COLLECT_DAYS=пн,чт (или mon,thu; «каждый» — все дни)."""
    raw = os.environ.get("COLLECT_DAYS", "пн,чт").strip().lower()
    if raw in ("каждый", "все", "daily", "*"):
        return list(range(7))
    days = sorted({DAY_CODES[x.strip()] for x in raw.split(",") if x.strip() in DAY_CODES})
    return days or [0, 3]


def collect_schedule_text() -> str:
    """«в понедельник и четверг в 03:00» — для подписей в версии для руководства."""
    days = collect_days()
    when = "каждый день" if len(days) == 7 else "в " + " и ".join(
        filter(None, [", ".join(DAY_NAMES[d] for d in days[:-1]), DAY_NAMES[days[-1]]]))
    return f"{when} в {', '.join(collect_times())}"


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


def kug_request_path() -> Path:
    """Запрос «проверить графики учебного процесса» из версии для руководства."""
    return data_dir() / "kug.request"
