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
DEMO = sorted((ROOT / "data" / "snapshots").glob("*.json"))
APP = str(ROOT / "stand" / "app.py")
PAGES = ["overview", "teachers", "rooms", "disciplines", "groups", "quality", "export"]

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
    assert shares[:4] > (0.9, 0.9, 0.9, 0.85)
    assert shares[4] < 0.2
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
