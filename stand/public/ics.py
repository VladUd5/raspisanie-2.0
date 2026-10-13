"""Подписка на календарь (RFC 5545).

Очники: занятия с 14 дней назад до конца текущего семестра, верхняя/нижняя неделя
разворачиваются в даты. Заочники: датированные занятия архива с 14 дней назад. UID постоянный —
изменённое занятие обновляется в календаре на месте, а не дублируется. Отменённые за последние
дни датированные занятия отдаются со STATUS:CANCELLED.
"""
import hashlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from public.week import TYPE_SHORT, Lesson, _change_for, expand
from semester import now, semester_for, tz

PAST_DAYS = 14
TTL = "PT6H"


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Строки длиннее 75 октетов переносятся (продолжение начинается с пробела)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def _vtimezone(name: str, at: datetime) -> list[str]:
    off = at.utcoffset()
    sign = "+" if off >= timedelta(0) else "-"
    mins = abs(int(off.total_seconds())) // 60
    o = f"{sign}{mins // 60:02d}{mins % 60:02d}"
    return ["BEGIN:VTIMEZONE", f"TZID:{name}", "BEGIN:STANDARD", "DTSTART:19700101T000000",
            f"TZOFFSETFROM:{o}", f"TZOFFSETTO:{o}", f"TZNAME:{at.tzname()}", "END:STANDARD", "END:VTIMEZONE"]


def occurrences(items: pd.DataFrame, rows: pd.DataFrame, today: date) -> list[tuple[date, Lesson]]:
    """Очники — до конца текущего семестра, заочники — все будущие даты; с PAST_DAYS дней назад."""
    start = today - timedelta(days=PAST_DAYS)
    sem = semester_for(today)
    end = sem[1] if sem is not None else start - timedelta(days=1)
    return expand(items, rows, start, end, dated_until=date.max)


def calendar(name: str, items: pd.DataFrame, rows: pd.DataFrame, changes: pd.DataFrame, page_url: str,
             uid_scope: str, subgroup: int | None = None) -> str:
    at = now()
    tzname = str(tz())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//raspisanie//RU", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(name)}", f"X-WR-TIMEZONE:{tzname}",
             f"REFRESH-INTERVAL;VALUE=DURATION:{TTL}", f"X-PUBLISHED-TTL:{TTL}", *_vtimezone(tzname, at)]
    events = occurrences(items, rows, at.date())
    for c in _cancelled_dated(changes, rows, at.date()):
        events.append(c)
    for d, les in sorted(events, key=lambda x: (x[0], x[1].time_from)):
        if subgroup and les.subgroup not in (0, subgroup):
            continue
        uid = hashlib.sha1("|".join([uid_scope, d.isoformat(), les.time_from, str(les.subgroup),
                                     les.discipline if not les.cancelled else ""]).encode()).hexdigest()
        t_from = les.time_from.replace(":", "")
        t_to = (les.time_to or _plus90(les.time_from)).replace(":", "")
        title = f"{TYPE_SHORT.get(les.lesson_type, les.lesson_type.upper() or 'ЗАН')} · {les.discipline or 'занятие'}"
        if les.cancelled:
            title = f"ОТМЕНЕНО · {les.discipline}"
        desc = []
        if les.teachers:
            desc.append("Преподаватель: " + ", ".join(les.teachers))
        if len(les.groups) > 1 or uid_scope.startswith("t:") or uid_scope.startswith("r:"):
            desc.append("Группы: " + ", ".join(les.groups))
        if les.subgroup:
            desc.append(f"Подгруппа {les.subgroup}")
        ch = les.change or _change_for(changes, les, d)
        if ch and ch.get("kind") in ("changed", "moved"):
            desc.append(f"Изменено {ch['day'][8:10]}.{ch['day'][5:7]}: было {ch['before']}")
        desc.append(page_url)
        lines += ["BEGIN:VEVENT", f"UID:{uid}@raspisanie", f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID={tzname}:{d:%Y%m%d}T{t_from}00", f"DTEND;TZID={tzname}:{d:%Y%m%d}T{t_to}00",
                  f"SUMMARY:{_esc(title)}"]
        if les.rooms:
            lines.append(f"LOCATION:{_esc('; '.join(f'{b}, ауд. {r}' for b, r in les.rooms))}")
        lines.append(f"DESCRIPTION:{_esc(chr(10).join(desc))}")
        lines.append("STATUS:CANCELLED" if les.cancelled else "STATUS:CONFIRMED")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def _plus90(t: str) -> str:
    h, m = map(int, t.split(":"))
    m += 90
    return f"{h + m // 60:02d}:{m % 60:02d}"


def _cancelled_dated(changes: pd.DataFrame, rows: pd.DataFrame, today: date) -> list[tuple[date, Lesson]]:
    if changes is None or changes.empty:
        return []
    c = changes[(changes["kind"] == "removed") & (changes["date"] != "") & (changes["date"] >= today.isoformat())
                & changes["group_name"].isin(set(rows["group_name"]))]
    out = []
    for r in c.itertuples():
        les = Lesson(r.time_from, "", "", r.before.split(": ", 1)[-1].split(" · ")[0], (), (), (r.group_name,),
                     int(r.subgroup or 0), date=r.date, cancelled=True)
        out.append((date.fromisoformat(r.date), les))
    return out
