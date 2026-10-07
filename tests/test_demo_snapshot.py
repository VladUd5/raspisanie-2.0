"""Настоящий снапшот с сайта вуза из data/snapshots: грузится, разбирается не хуже
порогов и открывается на всех страницах. Пропускается, если снапшота нет."""
import shutil
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from analytics import queries as q
from etl.load import connect, load_snapshot

ROOT = Path(__file__).parent.parent
# Словарь написаний проверен на этом снапшоте; новые сборы рядом с ним тест не трогают.
DEMO = [p for p in [ROOT / "data" / "snapshots" / "2026-10-07_144819.json"] if p.exists()]
APP = str(ROOT / "stand" / "app.py")
PAGES = ["overview", "teachers", "rooms", "disciplines", "groups", "quality", "spellings", "export"]

# Сверка автоправил со словарём (точность, полнота): замер 2026-10-07 минус 1 п.п.
AUDIT_FLOORS = {"discipline": (0.94, 0.73), "teacher": (0.96, 0.81)}

pytestmark = pytest.mark.skipif(not DEMO, reason="нет демо-снапшота в data/snapshots")


def test_demo_snapshot_loads_with_reasonable_quality(tmp_path):
    conn = connect(tmp_path / "t.db")
    started = time.monotonic()
    load_snapshot(conn, DEMO[-1])
    assert time.monotonic() - started < 30
    cells, lessons = conn.execute("SELECT cells_cnt, lessons_cnt FROM snapshots").fetchone()
    assert cells > 3000 and lessons > 3000
    shares = conn.execute("SELECT AVG(has_type), AVG(has_discipline), AVG(has_teacher), AVG(has_room),"
                          " AVG(needs_review) FROM quality").fetchone()
    # поэлементно: сравнение кортежей лексикографическое и проверяло бы только первое поле
    assert all(s > floor for s, floor in zip(shares[:4], (0.9, 0.9, 0.9, 0.94))), shares
    assert shares[4] < 0.2
    audit = {k: (tp, fp, fn) for k, tp, fp, fn in conn.execute("SELECT kind, tp, fp, fn FROM rule_audit")}
    for kind, (min_precision, min_recall) in AUDIT_FLOORS.items():
        tp, fp, fn = audit[kind]
        assert tp / (tp + fp) >= min_precision and tp / (tp + fn) >= min_recall, (kind, audit[kind])
    started = time.monotonic()
    q.cells_quality_frame(conn, 1)            # без индексов по lesson_id — секунды
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_on_demo(tmp_path, monkeypatch, page):
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    shutil.copy(DEMO[-1], snaps / DEMO[-1].name)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.switch_page(f"views/{page}.py")
    at.run()
    assert not at.exception, at.exception


def test_demo_snapshot_names_are_all_verified(tmp_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, DEMO[-1])
    left = conn.execute("SELECT kind, spelling FROM spellings WHERE kind IN ('discipline', 'teacher')"
                        " AND source NOT IN ('словарь', 'словарь?')").fetchall()
    assert left == []
