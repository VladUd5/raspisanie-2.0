"""Справочник кафедр и преподавателей с официального сайта вуза.

Источники — только то, что вуз публикует сам:
  • /sveden/struct/ — кафедры: заведующий, адрес, телефон, почта, страница кафедры;
  • /sveden/employees/pps/index.html — преподаватели: ФИО, должность, учёная степень и звание;
  • страницы кафедр — состав (ФИО полностью), контакты (у части кафедр — рабочая почта
    преподавателей), список закреплённых аудиторий (преподавательская).

Результат — data/directory.json; обновляет collector раз в сутки (python collector.py directory —
вручную). Если сайт недоступен, остаётся прошлый файл. Преподаватель из расписания («Иванов И.И.»
или только фамилия) находится по фамилии и инициалам; совпадение по одной фамилии — только если
она в справочнике одна.
"""
import html as html_lib
import json
import os
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import data_dir, schedule_url
from semester import now

UA = "raspisanie-stand/1.0 (schedule site of Vavilov University)"   # только ASCII: заголовок HTTP
POST_RANK = ["заведующ", "профессор", "доцент", "старший преподаватель", "преподаватель", "ассистент"]
DEGREE_SHORT = {"кандидат": "канд.", "доктор": "д-р", "сельскохозяйственных": "с.-х.", "технических": "техн.",
                "экономических": "экон.", "биологических": "биол.", "ветеринарных": "ветеринар.",
                "педагогических": "пед.", "филологических": "филол.", "исторических": "ист.",
                "философских": "филос.", "юридических": "юрид.", "физико-математических": "физ.-мат.",
                "химических": "хим.", "географических": "геогр.", "социологических": "социол.",
                "психологических": "психол.", "политических": "полит."}
FULL_NAME = re.compile(r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s+([А-ЯЁ][а-яё]+)\s+"
                       r"([А-ЯЁ][а-яё]+(?:вич|вна|ична|чна|оглы|кызы))")
EMAIL_AFTER_NAME = re.compile(r"([А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)\s*[-–—:]?\s*"
                              r"([\w.+-]+@[\w-]+(?:\.[\w-]+)+)")


def directory_path() -> Path:
    return Path(os.environ.get("DIRECTORY_PATH", data_dir() / "directory.json"))


def site_base() -> str:
    host = schedule_url().split("://")[-1].split("/")[0]
    return f"https://{host}"


# ── разбор страниц ──────────────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def page_text(page: str) -> str:
    """Основной текст страницы построчно: от заголовка h1 до подвала."""
    i = page.find("<h1")
    body = page[i:] if i >= 0 else page
    j = body.find("<footer")
    body = body[:j] if j > 0 else body
    text = html_lib.unescape(re.sub(r"<[^>]+>", "\n", body))
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\xa0]+", " ", text)).strip()


def parse_struct(page: str) -> list[dict]:
    """Кафедры из /sveden/struct/."""
    out = []
    for row in re.findall(r'<tr[^>]*itemprop="structOrgUprav"[^>]*>(.*?)</tr>', page, re.S):
        def prop(name):
            m = re.search(r'itemprop="%s"[^>]*>(.*?)</td>' % name, row, re.S)
            return _clean(m.group(1)) if m else ""
        if "кафедр" not in prop("post").lower():
            continue
        site = re.search(r'itemprop="site".*?>\s*(https?://[^<\s]+)\s*<', row, re.S)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        phone = _clean(cells[-1]) if cells else ""
        out.append({"name": prop("name"), "head": prop("fio"), "email": prop("email"),
                    "phone": phone if re.search(r"\d", phone) else "", "address": prop("addressStr"),
                    "site": site.group(1) if site else ""})
    return out


def parse_pps(page: str) -> list[dict]:
    """Преподаватели из /sveden/employees/pps/: ФИО, должность, степень, звание."""
    body = page[page.find("<tbody"):] if "<tbody" in page else page
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        c = [_clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(c) < 7 or not FULL_NAME.search(c[1]):
            continue
        out.append({"full_name": c[1], "post": c[2], "degree": c[5], "title": c[6]})
    return out


def department_links(page: str, site: str) -> dict[str, list[str]]:
    """Подстраницы кафедры: состав, контакты, закреплённые аудитории (адреса у кафедр разные)."""
    slug = site.rstrip("/").rsplit("/", 1)[-1]
    links = sorted(set(re.findall(r'href="(https?://[^"]*/kafedry/%s/[^"]+)"' % re.escape(slug), page)))
    def pick(*words):
        return [u for u in links if any(w in urllib.parse.unquote(u).lower() for w in words)]
    return {"staff": pick("prepodavat", "sostav", "sotrudn", "kollektiv"), "contacts": pick("kontakt"),
            "rooms": pick("auditor")}


def parse_names(text: str) -> list[str]:
    return sorted({" ".join(m) for m in FULL_NAME.findall(text)})


def parse_emails(text: str) -> dict[str, str]:
    """«Лялина Е.В. - lyalinaev@…» → {"Лялина Е.В.": "lyalinaev@…"}."""
    flat = re.sub(r"\s+", " ", text)
    return {norm_name(n): e for n, e in EMAIL_AFTER_NAME.findall(flat)}


def teacher_rooms(text: str) -> list[str]:
    """Номера аудиторий из строк о преподавательской / комнатах преподавателей."""
    out = []
    for line in text.splitlines():
        if "преподавател" in line.lower():
            out += [x for x in re.findall(r"\b\d{3}[а-яА-Я]?\b", line) if x not in out]
    return out


def short_degree(degree: str) -> str:
    d = (degree or "").strip()
    if not d or d.lower() in ("нет", "не имеет", "-", "—"):
        return ""
    words = [DEGREE_SHORT.get(w.lower(), w.lower()) for w in d.split()]
    return " ".join(words)


def norm_name(name: str) -> str:
    """«Иванов  И. И.» → «Иванов И.И.»; ё → е."""
    s = re.sub(r"\s+", " ", (name or "").replace("ё", "е").replace("Ё", "Е")).strip()
    return re.sub(r"([А-ЯA-Z])\.\s+(?=[А-ЯA-Z]\.)", r"\1.", s)


def short_name(full: str) -> str:
    p = full.replace("ё", "е").split()
    return f"{p[0]} {p[1][0]}.{p[2][0]}." if len(p) >= 3 else norm_name(full)


def _rank(post: str) -> int:
    p = post.lower()
    return next((i for i, w in enumerate(POST_RANK) if w in p), len(POST_RANK))


# ── сборка ──────────────────────────────────────────────────────────────────────────────────

def fetch(get: Callable[[str], str] | None = None, base: str | None = None, pause: float = 0.3) -> dict:
    """Обойти сайт и собрать справочник. get(url) -> html (для тестов)."""
    base = base or site_base()
    if get is None:
        import requests
        session = requests.Session()
        session.headers["User-Agent"] = UA

        def get(url):
            time.sleep(pause)
            r = session.get(url, timeout=40)
            r.raise_for_status()
            r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
            return r.text
    departments = parse_struct(get(f"{base}/sveden/struct/"))
    staff = parse_pps(get(f"{base}/sveden/employees/pps/index.html"))
    people: dict[str, dict] = {}
    for p in staff:                                      # один человек бывает в списке дважды
        old = people.get(p["full_name"])
        if old is None or _rank(p["post"]) < _rank(old["post"]):
            people[p["full_name"]] = {**p, "department": "", "email": ""}
    by_short: dict[str, list[str]] = {}
    for full in people:
        by_short.setdefault(short_name(full), []).append(full)
    for dep in departments:
        dep.update(teacher_rooms=[], staff_count=0)
        if not dep["site"]:
            continue
        try:
            links = department_links(get(dep["site"]), dep["site"])
            staff_text = "\n".join(page_text(get(u)) for u in links["staff"][:2])
            contacts = "\n".join(page_text(get(u)) for u in links["contacts"][:1])
            rooms = "\n".join(page_text(get(u)) for u in links["rooms"][:1])
        except Exception:                                # noqa: BLE001 — одна кафедра не ломает справочник
            continue
        dep["teacher_rooms"] = teacher_rooms(rooms) or teacher_rooms(contacts)
        emails = parse_emails(contacts + "\n" + staff_text)
        names = parse_names(staff_text)
        dep["staff_count"] = len(names)
        for full in names:
            # на страницах кафедр бывают опечатки в отчестве: сверяем по фамилии и инициалам
            same = by_short.get(short_name(full), [])
            key = full if full in people else (same[0] if len(same) == 1 else full)
            person = people.setdefault(key, {"full_name": full, "post": "", "degree": "", "title": "",
                                             "department": "", "email": ""})
            if not person["department"]:
                person["department"] = dep["name"]
            person["email"] = person["email"] or emails.get(short_name(full), "")
    return {"fetched_at": now().isoformat(timespec="seconds"), "source": base,
            "departments": departments, "people": sorted(people.values(), key=lambda p: p["full_name"])}


def save(data: dict, path: Path | None = None) -> None:
    path = path or directory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def refresh(max_age_h: float = 24, path: Path | None = None) -> str:
    """Для collector: обновить справочник, если он старше max_age_h часов."""
    path = path or directory_path()
    if path.exists():
        try:
            age = now() - datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["fetched_at"])
            if age.total_seconds() < max_age_h * 3600:
                return ""
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    try:
        data = fetch()
    except Exception as e:                               # noqa: BLE001
        return f"Справочник кафедр не обновлён: {e}"
    if not data["people"]:
        return "Справочник кафедр не обновлён: на сайте вуза не нашлось преподавателей."
    save(data, path)
    found = sum(1 for p in data["people"] if p["department"])
    return f"Справочник кафедр обновлён: {len(data['departments'])} кафедр, {len(data['people'])} преподавателей, " \
           f"с кафедрой — {found}."


# ── поиск ───────────────────────────────────────────────────────────────────────────────────

class Directory:
    def __init__(self, data: dict):
        self.data = data
        self.departments = {d["name"]: d for d in data.get("departments", [])}
        self._by_short: dict[str, list[dict]] = {}
        self._by_surname: dict[str, list[dict]] = {}
        for p in data.get("people", []):
            self._by_short.setdefault(short_name(p["full_name"]), []).append(p)
            self._by_surname.setdefault(p["full_name"].replace("ё", "е").split()[0], []).append(p)

    def person(self, name: str) -> dict | None:
        """Преподаватель из расписания → запись справочника с кафедрой (или None)."""
        n = norm_name(name)
        hits = self._by_short.get(n) or (self._by_surname.get(n) if " " not in n else None) or []
        if len(hits) != 1:
            return None
        p = dict(hits[0])
        p["dept"] = self.departments.get(p["department"])
        p["subtitle"] = ", ".join(x for x in (p["post"].capitalize() if p["post"] else "",
                                              short_degree(p["degree"])) if x)
        return p


_cache: dict = {"key": None, "dir": None}


def get(path: Path | None = None) -> Directory | None:
    """Справочник из файла; перечитывается, когда файл меняется."""
    path = path or directory_path()
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return None
    if _cache["key"] != key:
        try:
            _cache["dir"] = Directory(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            _cache["dir"] = None
        _cache["key"] = key
    return _cache["dir"]
