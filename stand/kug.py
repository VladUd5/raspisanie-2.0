"""Календарные учебные графики (КУГ) с сайта вуза → даты сессий по группам.

Графики лежат в /sveden/education/eduop как PDF-сканы: таблица «курс × неделя × день» с
отметками «Э» (сессия), «К» (каникулы), «=» (праздники), У/П/Н/Д (практики, НИР, ВКР); пустая клетка —
теоретическое обучение. Текста в файлах нет, поэтому сетка таблицы находится по линиям, а знак в
каждой клетке сравнивается с образцами «Э» и «К» (kug_templates.npy, вырезаны из графика того же
шаблона); прочие буквы различать не нужно — для расписания все они «не теория».

Из отметок курса получаются периоды: теория, сессия, каникулы, практика. Результат — черновик:
учебный отдел проверяет его в версии для руководства («Сессии»), на сайт для студентов попадают
только подтверждённые периоды. Праздники берутся не отсюда (знак «=» мелкий и распознаётся не
везде), а из производственного календаря — academic.py.

Сопоставление с группами: в названии ссылки — код группы, курсы и форма
(«График_Б-ЛА_1-4курс_оч_2026-2027»); группа «Б-ЛА-301» → код «Б-ЛА», курс 3 (первая цифра номера).
"""
import html as html_lib
import io
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import numpy as np

from semester import monday, now

TEMPLATES = Path(__file__).with_name("kug_templates.npy")
DPI = 300
FORM_WORDS = {"оч": "Очная", "очная": "Очная", "зо": "Заочная", "заочная": "Заочная", "озо": "Очно-заочная",
              "оз": "Очно-заочная", "очно-заочная": "Очно-заочная"}
CODE = re.compile(r"(?<![А-ЯЁA-Z])([БМС]-[А-ЯЁ]+(?:-[А-ЯЁ]+)*)")
# вид периода по отметке клетки; «=» (праздник) продолжает соседний период
KINDS = {".": "theory", "Э": "session", "К": "vacation", "x": "practice"}
KIND_TITLE = {"theory": "Теоретическое обучение", "session": "Сессия", "vacation": "Каникулы",
              "practice": "Практика, НИР, ВКР"}
NOISE_DAYS = 2           # кусок «x» короче — шум распознавания внутри соседнего периода


@dataclass
class KugFile:
    url: str
    title: str
    program: str           # «35.03.10 Ландшафтная архитектура»
    form: str              # Очная / Заочная / Очно-заочная
    code: str              # «Б-ЛА» или «» — тогда код вводят вручную
    courses: list[int]


# ── список графиков ─────────────────────────────────────────────────────────────────────────

def academic_year(d: date) -> int:
    """Учебный год по дате: 2026 для 01.09.2026 – 31.08.2027."""
    return d.year if d.month >= 9 else d.year - 1


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_index(page: str, year: int) -> list[KugFile]:
    """Графики на учебный год year из /sveden/education/eduop."""
    years = (f"{year}-{year + 1}", f"{year}/{year + 1}", f"{year}_{year + 1}")
    out, seen = [], set()
    for row in re.findall(r'<tr[^>]*itemprop="eduOp"[^>]*>(.*?)</tr>', page, re.S):
        def prop(name):
            m = re.search(r'itemprop="%s"[^>]*>(.*?)</td>' % name, row, re.S)
            return _clean(m.group(1)) if m else ""
        cell = re.search(r'itemprop="educationShedule"[^>]*>(.*?)</td>', row, re.S)
        if not cell:
            continue
        form = ""
        for m in re.finditer(r"<div>\s*([А-Яа-яЁё-]+)\s*:\s*</div>|<a [^>]*href=\"([^\"]+\.pdf)\"[^>]*title=\"([^\"]*)\"",
                             cell.group(1)):
            if m.group(1):
                form = FORM_WORDS.get(m.group(1).lower(), form)
                continue
            url, title = m.group(2), html_lib.unescape(m.group(3))
            if url in seen or not any(y in title or y in url for y in years):
                continue
            seen.add(url)
            out.append(KugFile(url, title, f"{prop('eduCode')} {prop('eduName')}".strip(), _form(title) or form,
                               _code(title), _courses(title)))
    return out


def _code(title: str) -> str:
    m = CODE.search(title.replace("ё", "е"))
    return m.group(1) if m else ""


def _courses(title: str) -> list[int]:
    m = re.search(r"(\d)\s*(?:-\s*(\d))?\s*_?\s*курс", title)
    if not m:
        return []
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return list(range(a, b + 1))


def _form(title: str) -> str:
    m = re.search(r"курс[а-я]*_(озо|оз|оч|зо)(?:_|$|\b)", title.lower())
    return FORM_WORDS.get(m.group(1), "") if m else ""


def group_key(group_name: str) -> tuple[str, int] | None:
    """«Б-ЛА-301» → («Б-ЛА», 3); без номера в конце — None."""
    parts = group_name.replace("ё", "е").split("-")
    if len(parts) < 2 or not parts[-1][:1].isdigit():
        return None
    return "-".join(parts[:-1]), int(parts[-1][0])


# ── распознавание скана ─────────────────────────────────────────────────────────────────────

def render(pdf_bytes: bytes) -> np.ndarray:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    return np.asarray(pdf[0].render(scale=DPI / 72, grayscale=True).to_pil().convert("L"))


def _runs(profile, thr, gap=3):
    out = []
    for i, v in enumerate(profile):
        if v > thr:
            if out and i - out[-1][1] <= gap:
                out[-1][1] = i
            else:
                out.append([i, i])
    return out


def deskew(g: np.ndarray) -> np.ndarray:
    """Повернуть скан так, чтобы линии таблицы стали горизонтальными (подбор угла ±1.5°)."""
    from PIL import Image
    img = Image.fromarray(g)
    small = img.resize((img.width // 4, img.height // 4))
    best, best_a = -1.0, 0.0
    for ang in np.arange(-1.5, 1.51, 0.1):
        score = float(np.var((np.asarray(small.rotate(ang, fillcolor=255)) < 150).sum(1)))
        if score > best:
            best, best_a = score, ang
    return np.asarray(img.rotate(best_a, fillcolor=255)) if abs(best_a) > 0.05 else g


def grid(g: np.ndarray):
    """→ (маска тёмного, линии недель, блоки курсов [(верх, низ)])."""
    a = g < 150
    h = a.shape[0]
    v0 = _runs(a.sum(0), 0.15 * h)
    if len(v0) < 20:
        return a, [], []
    left, right = v0[0][0], v0[-1][1]
    hl = _runs(a[:, left:right].sum(1), 0.6 * (right - left))
    if len(hl) < 3:
        return a, [], []
    top, bottom = hl[0][0], hl[-1][1]
    vl = _runs(a[top:bottom].sum(0), 0.5 * (bottom - top))
    blocks = [(hl[i][1] + 1, hl[i + 1][0] - 1) for i in range(len(hl) - 1)
              if hl[i + 1][0] - hl[i][1] > max(60, 0.25 * (bottom - top) / len(hl))]
    return a, vl[-53:] if len(vl) >= 53 else [], blocks


def _glyph(cell: np.ndarray):
    from PIL import Image
    c = cell.copy()
    c[c.sum(1) > 0.6 * c.shape[1]] = False
    c[:, c.sum(0) > 0.6 * c.shape[0]] = False
    ys, xs = np.nonzero(c)
    if len(ys) < 25:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    if (y1 - y0 + 1) < 0.55 * (x1 - x0 + 1) or (y1 - y0) < 8:
        return "flat"
    sub = c[y0:y1 + 1, x0:x1 + 1]
    return np.asarray(Image.fromarray((sub * 255).astype(np.uint8)).resize((16, 20), Image.BILINEAR)) / 255.0


def _corr(a, b) -> float:
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9))


def _mark(gl, templates) -> str:
    if gl is None:
        return "."
    if isinstance(gl, str):
        return "="
    e, k = _corr(gl, templates[0]), _corr(gl, templates[1])
    return "Э" if e > 0.55 and e > k else ("К" if k > 0.55 else "x")


def marks(g: np.ndarray, templates: np.ndarray | None = None) -> list[list[str]]:
    """Скан → по курсам (сверху вниз) 52 строки по 6 знаков (пн…сб): «Э», «К», «=», «x», «.»."""
    templates = np.load(TEMPLATES) if templates is None else templates
    a, weeks, blocks = grid(deskew(g))
    if not weeks:
        return []
    out = []
    for top, bot in blocks:
        course = []
        for wi in range(52):
            col = a[top:bot, weeks[wi][1] + 3:weeks[wi + 1][0] - 3]
            if col.shape[1] < 8:
                course.append("......")
                continue
            if len(_runs(col.sum(1), 0.7 * col.shape[1], gap=2)) < 3:     # объединённая клетка на неделю
                m = _mark(_glyph(col[3:-3]), templates)
                course.append(m * 6 if m in ("Э", "К", "x") else "......")     # «x» — У, П, Д… на всю неделю
                continue
            rh = (bot - top) / 6
            course.append("".join(_mark(_glyph(col[int(d * rh) + 3:int((d + 1) * rh) - 3]), templates)
                                  for d in range(6)))
        out.append(course)
    return out


def sessions(course_marks: list[str], year: int, max_gap: int = 12) -> list[tuple[date, date]]:
    """Дни с «Э» → периоды сессий. Неделя 1 — та, где 1 сентября; разрыв больше max_gap дней — новая сессия."""
    start = monday(date(year, 9, 1))
    days = [start + timedelta(weeks=w, days=d) for w, s in enumerate(course_marks) for d, ch in enumerate(s)
            if ch == "Э"]
    out: list[list[date]] = []
    for d in days:
        if out and (d - out[-1][1]).days <= max_gap:
            out[-1][1] = d
        else:
            out.append([d, d])
    return [(a, b) for a, b in out]


def periods(course_marks: list[str], year: int) -> list[tuple[str, date, date]]:
    """Отметки курса → [(вид, начало, конец)] по KINDS, с 1 сентября. Воскресений в графике нет:
    период может кончиться в субботу, а следующий начаться в понедельник."""
    first = date(year, 9, 1)
    start = monday(first)
    days = [(start + timedelta(weeks=w, days=d), ch) for w, s in enumerate(course_marks) for d, ch in enumerate(s)]
    days = [(d, ch) for d, ch in days if d >= first]
    seq = []
    for d, ch in days:                                   # праздник — часть того периода, где он стоит
        seq.append((d, ch if ch in KINDS else (seq[-1][1] if seq else ".")))
    runs: list[list] = []                                # [вид-отметка, начало, конец, дней]
    for d, ch in seq:
        if runs and runs[-1][0] == ch:
            runs[-1][2], runs[-1][3] = d, runs[-1][3] + 1
        else:
            runs.append([ch, d, d, 1])
    for i, r in enumerate(runs):                         # короткий «x» — шум: берёт вид соседа
        if r[0] == "x" and r[3] <= NOISE_DAYS:
            r[0] = runs[i - 1][0] if i else (runs[i + 1][0] if i + 1 < len(runs) else ".")
    for i, r in enumerate(runs):                         # день-два «теории» посреди сессии или практики —
        if r[0] == "." and r[3] <= NOISE_DAYS and 0 < i < len(runs) - 1 \
                and runs[i - 1][0] != "." and runs[i + 1][0] != ".":   # нераспознанный «=» или пропуск
            r[0] = runs[i - 1][0]
    out: list[list] = []
    for ch, a, b, _n in runs:
        if out and out[-1][0] == ch:
            out[-1][2] = b
        else:
            out.append([ch, a, b])
    return [(KINDS[ch], a, b) for ch, a, b in out]


def session_name(start: date) -> str:
    return "Зимняя сессия" if start.month in (11, 12, 1, 2, 3) else "Летняя сессия"


# ── хранение и обновление ───────────────────────────────────────────────────────────────────

def save_file(conn: sqlite3.Connection, f: KugFile, status: str, message: str) -> None:
    with conn:
        conn.execute("""INSERT INTO kug_files (url, title, program, form, code, courses, status, message, checked_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(url) DO UPDATE SET title=excluded.title, program=excluded.program,
                          form=excluded.form, code=CASE WHEN kug_files.code_manual = 1 THEN kug_files.code
                          ELSE excluded.code END, courses=excluded.courses, status=excluded.status,
                          message=excluded.message, checked_at=excluded.checked_at""",
                     (f.url, f.title, f.program, f.form, f.code, ",".join(map(str, f.courses)), status, message,
                      now().isoformat(timespec="seconds")))


def _norm(p: tuple) -> tuple[str, date, date]:
    return p if len(p) == 3 else ("session", *p)          # (начало, конец) — сессия


def save_drafts(conn: sqlite3.Connection, url: str, found: dict[int, list[tuple]], alongside: bool = False) -> int:
    """Черновики периодов по курсам: [(вид, начало, конец)] или [(начало, конец)] — сессии.
    Подтверждённые и исправленные вручную строки не трогаем. alongside — график на сайте обновился:
    у курсов с подтверждёнными периодами новый черновик кладётся рядом, если он от них отличается."""
    n = 0
    with conn:
        conn.execute("DELETE FROM sessions WHERE file_url = ? AND status = 'draft'", (url,))
        for course, found_periods in found.items():
            new = sorted({_norm(p) for p in found_periods}, key=lambda x: (x[1], x[0]))
            kept = {(k, date.fromisoformat(a), date.fromisoformat(b)) for k, a, b in conn.execute(
                "SELECT kind, start_date, end_date FROM sessions WHERE file_url = ? AND course = ? "
                "AND status != 'draft'", (url, course))}
            if kept and (not alongside or set(new) == kept):
                continue
            for kind, a, b in new:
                conn.execute("""INSERT INTO sessions (file_url, course, kind, start_date, end_date, status, source,
                                updated_at) VALUES (?, ?, ?, ?, ?, 'draft', 'auto', ?)""",
                             (url, course, kind, a.isoformat(), b.isoformat(), now().isoformat(timespec="seconds")))
                n += 1
    return n


def confirm_drafts(conn: sqlite3.Connection, url: str) -> None:
    """«Подтвердить черновик как есть»: по курсам, где есть черновик, он заменяет подтверждённое."""
    with conn:
        conn.execute("""DELETE FROM sessions WHERE file_url = ? AND status != 'draft' AND course IN
                        (SELECT course FROM sessions WHERE file_url = ? AND status = 'draft')""", (url, url))
        conn.execute("UPDATE sessions SET status = 'confirmed', updated_at = ? WHERE file_url = ? AND status = 'draft'",
                     (now().isoformat(timespec="seconds"), url))


def refresh(conn: sqlite3.Connection, base: str, get: Callable[[str], bytes], today: date | None = None,
            force: bool = False, head: Callable[[str], str] | None = None) -> str:
    """Скачать список графиков на текущий учебный год и распознать новые файлы. head(адрес) → версия
    файла на сайте (ETag и Last-Modified): изменилась у уже разобранного — он распознаётся заново."""
    year = academic_year(today or now().date())
    files = parse_index(get(f"{base}/sveden/education/eduop").decode("utf-8", "replace"), year)
    known = {r[0] for r in conn.execute("SELECT url FROM kug_files WHERE status IN ('ok', 'empty', 'skipped')")}
    versions = dict(conn.execute("SELECT url, version FROM kug_files").fetchall())
    manual = {r[0]: r[1] for r in conn.execute("SELECT url, code FROM kug_files WHERE code_manual = 1")}
    templates = np.load(TEMPLATES)
    done = drafts = failed = skipped = updated = 0
    for f in files:
        f.code = manual.get(f.url, f.code)
        version = _version(head, base + f.url)
        changed = bool(version and versions.get(f.url) and version != versions[f.url])
        if f.url in known and not force and f.url not in manual and not changed:
            if version and not versions.get(f.url):       # разобран до того, как версии стали запоминать
                set_version(conn, f.url, version)
            continue
        if not f.code:                                   # колледж и т. п.: другой шаблон, группы не сопоставить
            save_file(conn, f, "skipped", "в названии нет кода группы — впишите его, если график нужен")
            skipped += 1
            continue
        try:
            found_marks = marks(render(get(base + f.url)), templates)
        except Exception as e:                                       # noqa: BLE001 — один файл не ломает остальные
            save_file(conn, f, "error", f"не удалось прочитать: {e}")
            failed += 1
            continue
        if not found_marks or len(found_marks) > 6:
            save_file(conn, f, "error", "таблица графика не найдена на скане" if not found_marks else
                      f"на скане {len(found_marks)} блоков — не похоже на график вуза")
            failed += 1
            continue
        courses = f.courses if len(f.courses) == len(found_marks) else list(range(1, len(found_marks) + 1))
        found = {c: periods(m, year) for c, m in zip(courses, found_marks)}
        save_holidays(conn, f.url, {d for m in found_marks for d in marked_days(m, year, "=")})
        n = save_drafts(conn, f.url, found, alongside=changed)
        n_sessions = sum(k == "session" for ps in found.values() for k, _a, _b in ps)
        if len(f.courses) != len(found_marks) and f.courses:
            msg = f"на скане {len(found_marks)} курса(ов), в названии — {len(f.courses)}: проверьте номера курсов"
        else:
            msg = f"распознано периодов: {sum(map(len, found.values()))}, из них сессий: {n_sessions}"
        if changed:
            msg = (f"график на сайте обновлён {now():%d.%m.%Y} — сверьте периоды. " if n else
                   f"график на сайте обновлён {now():%d.%m.%Y}, периоды те же. ") + msg
            updated += 1
        save_file(conn, f, "ok" if n_sessions else "empty", msg)
        if version:
            set_version(conn, f.url, version)
        done += 1
        drafts += n
    return f"Графики учебного процесса: файлов {len(files)}, разобрано {done}, черновиков {drafts}" + \
        (f", обновлено на сайте {updated}" if updated else "") + \
        (f", не прочитано {failed}" if failed else "") + (f", без кода группы {skipped}" if skipped else "") + "."


def _version(head: Callable[[str], str] | None, url: str) -> str:
    if head is None:
        return ""
    try:
        return head(url)
    except Exception:                                     # noqa: BLE001 — нет версии — как раньше, по адресу
        return ""


def marked_days(course_marks: list[str], year: int, mark: str) -> list[date]:
    """Дни с отметкой mark с 1 сентября (в понедельник перед ним в графике стоит сноска «*»)."""
    first = date(year, 9, 1)
    start = monday(first)
    days = [start + timedelta(weeks=w, days=d) for w, s in enumerate(course_marks) for d, ch in enumerate(s)
            if ch == mark]
    return [d for d in days if d >= first]


def save_holidays(conn: sqlite3.Connection, url: str, days: set[date]) -> None:
    """Дни «=» графика — голоса за праздник (переносы выходных); сами праздники — academic.py."""
    with conn:
        conn.execute("DELETE FROM kug_holidays WHERE file_url = ?", (url,))
        conn.executemany("INSERT INTO kug_holidays (file_url, day) VALUES (?, ?)", [(url, d.isoformat()) for d in days])


def set_version(conn: sqlite3.Connection, url: str, version: str) -> None:
    with conn:
        conn.execute("UPDATE kug_files SET version = ? WHERE url = ?", (version, url))


def http_get(timeout: float = 60) -> Callable[[str], bytes]:
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "raspisanie-stand/1.0 (schedule site of Vavilov University)"

    def get(url: str) -> bytes:
        r = s.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    return get


def http_head(timeout: float = 30) -> Callable[[str], str]:
    """Версия файла на сайте без скачивания: «ETag|Last-Modified» (пусто — сервер их не отдаёт)."""
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "raspisanie-stand/1.0 (schedule site of Vavilov University)"

    def head(url: str) -> str:
        r = s.head(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        v = f"{r.headers.get('ETag', '')}|{r.headers.get('Last-Modified', '')}"
        return "" if v == "|" else v
    return head


# ── чтение для сайта ────────────────────────────────────────────────────────────────────────

def for_group(conn: sqlite3.Connection, group_name: str, study_form: str, confirmed_only: bool = True) -> dict:
    """Сессии группы: {"file": url или "", "title": …, "periods": [(start, end, name)]}."""
    key = group_key(group_name)
    if key is None:
        return {"file": "", "title": "", "periods": []}
    code, course = key
    cands = conn.execute("SELECT url, title, courses FROM kug_files WHERE code = ? AND form = ? "
                         "ORDER BY checked_at DESC", (code, study_form)).fetchall()
    # у направления бывает несколько файлов («1 курс», «2-4 курс») — нужен тот, где есть курс группы
    f = next((c for c in cands if str(course) in (c["courses"] or "").split(",")), cands[0] if cands else None)
    if f is None:
        return {"file": "", "title": "", "periods": []}
    q = "SELECT start_date, end_date FROM sessions WHERE file_url = ? AND course = ? AND kind = 'session'"
    q += " AND status = 'confirmed'" if confirmed_only else " AND status != 'rejected'"
    periods = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in
               conn.execute(q + " ORDER BY start_date", (f["url"], course))]
    return {"file": f["url"], "title": f["title"],
            "periods": [(a, b, session_name(a)) for a, b in periods]}


def all_periods(conn: sqlite3.Connection, confirmed_only: bool = True) -> dict[tuple, list[tuple[str, date, date]]]:
    """Периоды всех курсов: {(код, форма, курс): [(вид, начало, конец)]} — по тому же файлу, что и
    for_group (самый свежий, где есть курс)."""
    files = conn.execute("SELECT url, code, form, courses FROM kug_files WHERE code != '' "
                         "ORDER BY checked_at DESC").fetchall()
    q = "SELECT file_url, course, kind, start_date, end_date FROM sessions WHERE status "
    q += "= 'confirmed'" if confirmed_only else "!= 'rejected'"
    by_file: dict = {}
    for url, course, kind, a, b in conn.execute(q + " ORDER BY start_date"):
        by_file.setdefault((url, course), []).append((kind, date.fromisoformat(a), date.fromisoformat(b)))
    out: dict = {}
    for f in files:
        listed = [int(c) for c in (f["courses"] or "").split(",") if c]
        for (url, course), ps in by_file.items():
            key = (f["code"], f["form"], course)
            if url == f["url"] and key not in out and (course in listed or not listed):
                out[key] = ps
    return out


def preview_png(pdf_bytes: bytes, width: int = 1600) -> bytes:
    """Картинка скана для проверки в версии для руководства."""
    from PIL import Image
    img = Image.fromarray(render(pdf_bytes))
    img = img.resize((width, int(img.height * width / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
