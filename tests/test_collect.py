import json
import os
import time

import pytest
import requests

from etl import collect as collect_mod
from etl.collect import LOCK_NAME, CollectError, collect


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _patch(monkeypatch, result):
    def fake_get(url, params, timeout):
        assert url == "http://parser:8080/getschedule"
        assert params == {"urlSchedule": "www.vavilovsar.ru/ucheba/raspisanie-zanyatii"}
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(collect_mod.requests, "get", fake_get)


def test_saves_wrapped_snapshot(tmp_path, monkeypatch, mini_buildings):
    _patch(monkeypatch, FakeResponse(payload=mini_buildings))
    path = collect("http://parser:8080/", "www.vavilovsar.ru/ucheba/raspisanie-zanyatii", tmp_path)
    data = json.loads(path.read_text())
    assert data["buildings"] == mini_buildings
    assert data["source_url"] == "www.vavilovsar.ru/ucheba/raspisanie-zanyatii"
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("result,message", [
    (requests.ConnectionError(), "недоступен"),
    (requests.Timeout(), "не ответил"),
    (FakeResponse(status=500, text="boom"), "HTTP 500"),
    (FakeResponse(payload=None), "не JSON"),
    (FakeResponse(payload=[]), "пустой"),
])
def test_errors_are_explained(tmp_path, monkeypatch, result, message):
    _patch(monkeypatch, result)
    with pytest.raises(CollectError, match=message):
        collect("http://parser:8080", "www.vavilovsar.ru/ucheba/raspisanie-zanyatii", tmp_path)
    assert list(tmp_path.iterdir()) == []      # ни снапшота, ни блокировки


def test_second_collect_is_rejected_while_first_runs(tmp_path, monkeypatch, mini_buildings):
    (tmp_path / LOCK_NAME).touch()
    _patch(monkeypatch, FakeResponse(payload=mini_buildings))
    with pytest.raises(CollectError, match="уже идёт"):
        collect("http://parser:8080", "www.vavilovsar.ru/ucheba/raspisanie-zanyatii", tmp_path)
    assert (tmp_path / LOCK_NAME).exists()     # чужую блокировку не трогаем


def test_stale_lock_is_ignored(tmp_path, monkeypatch, mini_buildings):
    lock = tmp_path / LOCK_NAME
    lock.touch()
    old = time.time() - 3600
    os.utime(lock, (old, old))
    _patch(monkeypatch, FakeResponse(payload=mini_buildings))
    collect("http://parser:8080", "www.vavilovsar.ru/ucheba/raspisanie-zanyatii", tmp_path, timeout_s=900)
    assert not lock.exists()


def test_collected_at_has_timezone(tmp_path, monkeypatch, mini_buildings):
    _patch(monkeypatch, FakeResponse(payload=mini_buildings))
    path = collect("http://parser:8080", "www.vavilovsar.ru/ucheba/raspisanie-zanyatii", tmp_path)
    stamp = json.loads(path.read_text())["collected_at"]
    assert stamp[-6] in "+-" and stamp[-3] == ":"      # …T12:03:39+03:00
