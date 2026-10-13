import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import collector
from etl.collect import CollectError


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def fake_collect(buildings):
    counter = iter(range(100))

    def collect(parser_url, schedule_url, snapshots_dir, timeout_s):
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        p = snapshots_dir / f"2026-10-13_0300{next(counter):02d}.json"
        p.write_text(json.dumps({"collected_at": "2026-10-13T03:00:00+04:00", "buildings": buildings},
                                ensure_ascii=False))
        return p
    return collect


def test_unchanged_collection_is_not_kept(env, monkeypatch, mini_buildings):
    monkeypatch.setattr(collector, "collect", fake_collect(mini_buildings))
    first = collector.run_once()
    assert first["ok"] and "новая версия" in first["message"]
    second = collector.run_once()
    assert second["ok"] and "не изменилось" in second["message"]
    assert len(list((env / "snapshots").glob("*.json"))) == 1
    assert collector.read_status()["last_success_at"]


def test_failed_collection_writes_status(env, monkeypatch):
    def boom(*a):
        raise CollectError("Парсер недоступен.")
    monkeypatch.setattr(collector, "collect", boom)
    st = collector.run_once()
    assert not st["ok"] and "Парсер недоступен" in st["message"]


def test_next_run():
    tz = ZoneInfo("Europe/Saratov")
    at = datetime(2026, 10, 13, 12, 0, tzinfo=tz)
    assert collector.next_run(at, ["03:00", "13:00"]) == datetime(2026, 10, 13, 13, 0, tzinfo=tz)
    assert collector.next_run(at.replace(hour=14), ["03:00", "13:00"]) == datetime(2026, 10, 14, 3, 0, tzinfo=tz)


def test_request_throttled(env, monkeypatch, mini_buildings):
    assert collector.request_collect()
    monkeypatch.setattr(collector, "collect", fake_collect(mini_buildings))
    collector.run_once()
    assert not collector.request_collect()           # только что проверяли
