"""Графики учебного процесса: список файлов, распознавание сетки, черновики и подтверждённые сессии."""
from datetime import date

import numpy as np
from PIL import Image

import kug
from feedback import store

EDUOP = """<table><tr itemprop="eduOp"><td itemprop="eduCode">35.03.10</td><td itemprop="eduName">Ландшафтная архитектура</td>
<td itemprop="educationShedule"><div><div></div><div class="cascade-lvl-1"><div class="cascade-lvl-1"><div>Очная:</div>
<div class="cascade-lvl-2"><a href="/f/Grafik_B-LA_1-4kurs_och_2026-2027.pdf" title="График_Б-ЛА_1-4курс_оч_2026-2027">x</a>
<a href="/f/old.pdf" title="График_Б-ЛА_1-4курс_оч_2025-2026">старый</a></div></div>
<div class="cascade-lvl-1"><div>Заочная:</div><div class="cascade-lvl-2">
<a href="/f/zo.pdf" title="График_Б-ЛА_1-5курс_зо_2026-2027">y</a></div></div></div></div></td></tr>
<tr itemprop="eduOp"><td itemprop="eduCode">09.02.07</td><td itemprop="eduName">Колледж</td>
<td itemprop="educationShedule"><div>Очная:</div><a href="/f/spo.pdf" title="График 1-3 курсов 2026-2027">z</a></td></tr></table>"""


def test_parse_index_current_year_codes_courses_forms():
    files = kug.parse_index(EDUOP, 2026)
    assert [(f.url, f.code, f.courses, f.form) for f in files] == [
        ("/f/Grafik_B-LA_1-4kurs_och_2026-2027.pdf", "Б-ЛА", [1, 2, 3, 4], "Очная"),
        ("/f/zo.pdf", "Б-ЛА", [1, 2, 3, 4, 5], "Заочная"),
        ("/f/spo.pdf", "", [1, 2, 3], "Очная")]
    assert files[0].program == "35.03.10 Ландшафтная архитектура"


def test_group_key_and_academic_year():
    assert kug.group_key("Б-ЛА-301") == ("Б-ЛА", 3)
    assert kug.group_key("М-ЗК-УЗИК-101") == ("М-ЗК-УЗИК", 1)
    assert kug.group_key("Сборная") is None
    assert kug.academic_year(date(2027, 1, 10)) == 2026 and kug.academic_year(date(2026, 9, 1)) == 2026


def test_sessions_from_marks():
    weeks = ["......"] * 52
    weeks[16] = "....ЭЭ"            # неделя 17: 21–26.12.2026, пт и сб
    weeks[17] = "ЭЭЭ==="
    weeks[19] = "ЭЭЭЭКК"            # неделя 20: 11.01.2027
    weeks[40] = "ЭЭЭ..."            # летняя
    got = kug.sessions(weeks, 2026)
    assert got == [(date(2026, 12, 25), date(2027, 1, 14)), (date(2027, 6, 7), date(2027, 6, 9))]
    assert kug.session_name(got[0][0]) == "Зимняя сессия" and kug.session_name(got[1][0]) == "Летняя сессия"


def _synthetic_scan(marks: dict) -> np.ndarray:
    """Таблица как на графике: шапка, 52 недели, 2 курса по 6 дней; в клетки вставлены образцы «Э»/«К»."""
    tE, tK = np.load(kug.TEMPLATES)
    W, Hh = 3300, 2300
    g = np.full((Hh, W), 255, np.uint8)
    left, x0, cw = 200, 400, 52
    xs = [x0 + i * cw for i in range(53)]
    ys_head = [600, 650, 700, 750]
    block_h = 210
    blocks = [(750, 750 + block_h), (750 + block_h, 750 + 2 * block_h)]
    right = xs[-1]
    for y in ys_head + [b for _, b in blocks]:
        g[y:y + 3, left:right + 3] = 0
    for x in [left] + xs:
        g[600:blocks[-1][1] + 3, x:x + 3] = 0
    for ci, (top, bot) in enumerate(blocks):
        rh = (bot - top) / 6
        for w in {w for (c, w, _d) in marks if c == ci + 1}:   # линии дней — только в размеченных неделях
            for d in range(1, 6):
                y = int(top + d * rh)
                g[y:y + 2, xs[w - 1]:xs[w] + 3] = 0
        for (c, w, d), ch in marks.items():
            if c != ci + 1:
                continue
            t = tE if ch == "Э" else tK
            glyph = (np.asarray(Image.fromarray((t * 255).astype(np.uint8)).resize((22, 26))) > 110)
            gy = int(top + d * rh + (rh - 26) / 2)
            gx = xs[w - 1] + (cw - 22) // 2
            g[gy:gy + 26, gx:gx + 22][glyph] = 0
    return g


def test_marks_on_synthetic_grid():
    m = {(1, 17, 4): "Э", (1, 17, 5): "Э", (1, 20, 0): "Э", (1, 20, 4): "К", (2, 22, 2): "Э"}
    out = kug.marks(_synthetic_scan(m))
    assert len(out) == 2
    assert out[0][16] == "....ЭЭ" and out[0][19][0] == "Э" and out[0][19][4] != "Э"     # «К» не сессия
    assert out[1][21][2] == "Э" and set(out[1][0]) == {"."}


def test_drafts_never_overwrite_confirmed(tmp_path):
    conn = store.connect(tmp_path / "f.db")
    f = kug.KugFile("/f/a.pdf", "График_Б-ЛА_1-4курс_оч_2026-2027", "П", "Очная", "Б-ЛА", [1, 2])
    kug.save_file(conn, f, "ok", "")
    assert kug.save_drafts(conn, f.url, {1: [(date(2026, 12, 25), date(2027, 1, 14))],
                                         2: [(date(2027, 1, 18), date(2027, 1, 30))]}) == 2
    with conn:
        conn.execute("UPDATE sessions SET status = 'confirmed', start_date = '2026-12-24' WHERE course = 1")
    kug.save_drafts(conn, f.url, {1: [(date(2026, 12, 1), date(2026, 12, 2))], 2: [(date(2027, 1, 19), date(2027, 1, 30))]})
    rows = conn.execute("SELECT course, start_date, status FROM sessions ORDER BY course").fetchall()
    assert [tuple(r) for r in rows] == [(1, "2026-12-24", "confirmed"), (2, "2027-01-19", "draft")]
    # на сайт — только подтверждённые
    assert kug.for_group(conn, "Б-ЛА-101", "Очная")["periods"][0][:2] == (date(2026, 12, 24), date(2027, 1, 14))
    assert kug.for_group(conn, "Б-ЛА-201", "Очная")["periods"] == []
    assert kug.for_group(conn, "Б-ЛА-201", "Очная", confirmed_only=False)["periods"]
    assert kug.for_group(conn, "Б-ЛА-201", "Заочная")["file"] == ""


def test_refresh_skips_files_without_group_code(tmp_path, monkeypatch):
    conn = store.connect(tmp_path / "f.db")
    pdfs = {}
    def get(url):
        if url.endswith("/sveden/education/eduop"):
            return EDUOP.encode()
        pdfs[url] = True
        raise OSError("нет файла")
    msg = kug.refresh(conn, "https://site", get, today=date(2026, 10, 13))
    assert "без кода группы 1" in msg and "не прочитано 2" in msg
    st = dict(conn.execute("SELECT url, status FROM kug_files").fetchall())
    assert st == {"/f/Grafik_B-LA_1-4kurs_och_2026-2027.pdf": "error", "/f/zo.pdf": "error", "/f/spo.pdf": "skipped"}
    assert "https://site/f/spo.pdf" not in pdfs


def test_for_group_picks_file_with_its_course(tmp_path):
    conn = store.connect(tmp_path / "f.db")
    first = kug.KugFile("/f/1.pdf", "График_Б-ПИ_1курс_оч_2026-2027", "П", "Очная", "Б-ПИ", [1])
    rest = kug.KugFile("/f/23.pdf", "График_Б-ПИ_2-3курс_оч_2026-2027", "П", "Очная", "Б-ПИ", [2, 3])
    kug.save_file(conn, first, "ok", "")
    kug.save_file(conn, rest, "ok", "")
    assert kug.for_group(conn, "Б-ПИ-101", "Очная")["file"] == "/f/1.pdf"
    assert kug.for_group(conn, "Б-ПИ-301", "Очная")["file"] == "/f/23.pdf"
