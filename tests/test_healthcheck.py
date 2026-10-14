import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import healthcheck


@pytest.fixture
def kills(tmp_path, monkeypatch):
    monkeypatch.setattr(healthcheck, "COUNTER", tmp_path / "failures")
    sent = []
    monkeypatch.setattr(healthcheck.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    return sent


@pytest.fixture
def server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/ok" else 500)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_url_ok_and_error(server, kills):
    assert healthcheck.main(["url", server + "/ok"]) == 0
    assert healthcheck.main(["url", server + "/bad"]) == 1
    assert healthcheck.main(["url", "http://127.0.0.1:9/"]) == 1     # никто не слушает
    assert kills == []


def test_restart_only_after_fails_in_a_row(server, kills):
    bad, ok = ["url", server + "/bad"], ["url", server + "/ok"]
    healthcheck.main(bad)
    healthcheck.main(bad)
    healthcheck.main(ok)                    # удачная проверка сбрасывает счёт
    healthcheck.main(bad)
    healthcheck.main(bad)
    assert kills == []
    healthcheck.main(bad)
    assert kills == [(-1, signal.SIGKILL)]
    assert not healthcheck.COUNTER.exists()


def test_heartbeat_file(tmp_path, kills):
    beat = tmp_path / "alive"
    assert healthcheck.main(["file", str(beat), "60"]) == 1          # пульса ещё нет
    beat.touch()
    assert healthcheck.main(["file", str(beat), "60"]) == 0
    old = time.time() - 120
    os.utime(beat, (old, old))
    assert healthcheck.main(["file", str(beat), "60"]) == 1
