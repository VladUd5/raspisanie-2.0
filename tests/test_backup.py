import sqlite3
import tarfile
from datetime import date

import pytest

import backup


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKUP_KEEP_DAYS", "3")
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / "2026-10-09_150932.json").write_text("{}")
    conn = sqlite3.connect(tmp_path / "feedback.db")
    conn.execute("CREATE TABLE sessions (id INTEGER, start_date TEXT)")
    conn.execute("INSERT INTO sessions VALUES (1, '2027-01-11')")
    conn.commit()
    conn.close()
    (tmp_path / "schedule.db").write_text("пересобирается из снапшотов")
    return tmp_path


def test_archive_has_feedback_and_snapshots_only(data):
    msg = backup.run()
    arc = backup.archive_path()
    assert arc.exists() and "снапшотов 1" in msg
    with tarfile.open(arc) as tar:
        assert sorted(tar.getnames()) == ["feedback.db", "snapshots/2026-10-09_150932.json"]
        tar.extract("feedback.db", data / "restored", filter="data")
    rows = sqlite3.connect(data / "restored" / "feedback.db").execute("SELECT * FROM sessions").fetchall()
    assert rows == [(1, "2027-01-11")]


def test_once_a_day_and_old_ones_removed(data, monkeypatch):
    backup.run()
    assert "уже есть" in backup.run()
    for d in (1, 2, 3, 4):
        monkeypatch.setattr(backup, "now", lambda d=d: __import__("datetime").datetime(2026, 11, d))
        backup.run()
    left = sorted(p.name for p in (data / "backups").glob("*.tar.gz"))
    assert left == ["2026-11-02.tar.gz", "2026-11-03.tar.gz", "2026-11-04.tar.gz"]
    assert not list((data / "backups").glob("*.tmp"))
    assert backup.archive_path(date(2026, 11, 4)).name == "2026-11-04.tar.gz"
