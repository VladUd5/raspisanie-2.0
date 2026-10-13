from datetime import datetime, timedelta

import pytest

from feedback import store


@pytest.fixture
def conn(tmp_path):
    return store.connect(tmp_path / "f.db")


def test_migrations_idempotent(tmp_path):
    store.connect(tmp_path / "f.db").close()
    c = store.connect(tmp_path / "f.db")
    assert c.execute("PRAGMA user_version").fetchone()[0] == len(store.MIGRATIONS)


def test_add_and_status_log(conn):
    rid = store.add_report(conn, {"kind": "room", "text": " ауд. 314 занята ", "group_name": "Г-1"}, "1.2.3.4")
    r = store.list_reports(conn)[0]
    assert r["id"] == rid and r["text"] == "ауд. 314 занята" and r["status"] == "new"
    store.set_status(conn, rid, "fixed", "поправили в PDF")
    assert store.counts(conn)["fixed"] == 1
    assert [x["action"] for x in store.log(conn, rid)] == ["created", "status", "note"]
    with pytest.raises(ValueError):
        store.set_status(conn, rid, "deleted")


def test_text_trimmed_and_unknown_kind(conn):
    store.add_report(conn, {"kind": "hack", "text": "x" * 5000}, "ip")
    r = store.list_reports(conn)[0]
    assert r["kind"] == "other" and len(r["text"]) == store.MAX_TEXT


def test_rate_limit_per_ip_per_hour(conn):
    t = datetime(2026, 10, 13, 12, 0).astimezone()
    for i in range(3):
        assert store.add_report(conn, {"text": str(i)}, "ip", per_hour=3, at=t)
    assert store.add_report(conn, {"text": "4"}, "ip", per_hour=3, at=t) is None
    assert store.add_report(conn, {"text": "other ip"}, "ip2", per_hour=3, at=t)
    assert store.add_report(conn, {"text": "later"}, "ip", per_hour=3, at=t + timedelta(hours=1, minutes=1))
    assert "ip" not in {r[0] for r in conn.execute("SELECT ip_hash FROM rate")}   # только хэш
