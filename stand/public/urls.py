"""Адреса страниц. Имена кодируются целиком (в них бывают «/», пробелы и точки)."""
from urllib.parse import quote


def _q(s: str) -> str:
    return quote(s, safe="")


def group_url(name: str) -> str:
    return f"/g/{_q(name)}"


def teacher_url(name: str) -> str:
    return f"/t/{_q(name)}"


def room_url(building: str, room: str) -> str:
    return f"/r/{_q(building)}/{_q(room)}"
