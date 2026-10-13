import re
from urllib.parse import unquote
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from etl.dictionary import DICTIONARY_DIR
from etl.load import connect, ensure_loaded
from semester import monday, today

OCHNO = [("Б-Э-101", 0, "08:30", "лек. ИСТОРИЯ РОССИИ доц. Шалаева Н.В. 422"),
         ("Б-Э-101", 0, "10:10", "пр.з. История России Шалаева 422", "numerator"),
         ("Б-Э-101", 0, "10:10", "пр.з. Иностранный язык Балашова 314", "denominator"),
         ("Б-БИ-101", 0, "08:30", "лек. ИСТОРИЯ РОССИИ доц. Шалаева Н.В. 422"),
         ("Б-Э-101", 2, "12:00", "лаб.з. Химия Иванов И.И. С-12/1")]


def zao_week(m: date):
    return [("З-ЭК-51", (m + timedelta(days=1)).isoformat(), "08:30", "лек. Экономика Петров П.П. 101"),
            ("З-ЭК-51", (m + timedelta(days=2)).isoformat(), "10:10", "пр.з. Экономика Петров П.П. 101")]


@pytest.fixture
def client(tmp_path, monkeypatch, make_snapshot):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    m = monday(today())
    make_snapshot("a", (today() - timedelta(days=2)).isoformat() + "T03:00:00+04:00", OCHNO, zao_week(m))
    changed = OCHNO[:4] + [("Б-Э-101", 2, "12:00", "лаб.з. Химия Иванов И.И. 316")]
    make_snapshot("b", (today() - timedelta(days=1)).isoformat() + "T03:00:00+04:00", changed,
                  zao_week(m) + zao_week(m + timedelta(days=7)))
    conn = connect(tmp_path / "schedule.db")
    ensure_loaded(conn, tmp_path / "snapshots", DICTIONARY_DIR)
    conn.close()
    from public import app as app_module
    from public.data import Store
    monkeypatch.setattr(app_module, "store", Store())
    return TestClient(app_module.app)


def test_index_and_search(client):
    r = client.get("/")
    assert r.status_code == 200 and "Расписание" in r.text
    r = client.get("/", params={"q": "бэ101"})
    assert "Б-Э-101" in r.text
    js = client.get("/api/search", params={"q": "шалаев"}).json()
    assert js[0]["kind"] == "преподаватель" and js[0]["url"].startswith("/t/")
    assert client.get("/api/search", params={"q": "шлаева"}).json()      # опечатка


def test_group_week_and_change_badge(client):
    r = client.get("/g/Б-Э-101")
    assert r.status_code == 200
    assert "История России" in r.text
    assert "изменено" in r.text and "было:" in r.text            # аудитория химии поменялась вчера
    # на неделе виден только один из вариантов 10:10 (верхняя/нижняя) или оба с пометкой вне семестра
    shown = ("Иностранный язык" in r.text) + ("пр.з" in r.text or r.text.count("История России") > 1)
    assert shown >= 1


def test_zaochniki_weeks_and_navigation(client):
    r = client.get("/g/З-ЭК-51")
    assert r.status_code == 200 and "Экономика" in r.text
    nxt = monday(today()) + timedelta(days=7)
    assert f"?week={nxt.isoformat()}" in r.text
    r2 = client.get("/g/З-ЭК-51", params={"week": nxt.isoformat()})
    assert "Экономика" in r2.text


def test_teacher_room_with_slash_and_unknown(client):
    r = client.get("/t/Шалаева Н.В.")
    assert r.status_code == 200 and "Б-БИ-101" in r.text and "Б-Э-101" in r.text   # поток — одно занятие с группами
    links = re.findall(r'href="(/r/[^"]+)"', client.get("/g/Б-Э-101").text)
    assert links
    for link in set(links):
        assert client.get(link).status_code == 200
    assert client.get("/g/НЕТ-ТАКОЙ").status_code == 404
    assert client.get("/g/Б-Э-101", params={"week": "мусор"}).status_code == 200


def test_ics(client):
    r = client.get("/g/Б-Э-101.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR") and body.rstrip().endswith("END:VCALENDAR")
    assert "TZID:Europe/Saratov" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    z = client.get("/g/З-ЭК-51.ics").text
    assert z.count("BEGIN:VEVENT") == 4
    assert client.get("/t/Петров П.П..ics").status_code == 200


def test_changes_page(client):
    r = client.get("/changes")
    assert r.status_code == 200 and "Б-Э-101" in r.text and "новая неделя" in r.text
    assert "Б-Э-101" not in client.get("/changes", params={"q": "З-ЭК"}).text


def test_report_flow(client, tmp_path):
    form = {"kind": "room", "text": "Химия в 316", "page": "/g/Б-Э-101", "group_name": "Б-Э-101"}
    r = client.post("/report", data=form, follow_redirects=False)
    assert r.status_code == 303 and unquote(r.headers["location"]) == "/g/Б-Э-101?reported=1"
    assert "Спасибо" in client.get(r.headers["location"]).text
    from feedback import store
    c = store.connect(tmp_path / "feedback.db")
    assert len(store.list_reports(c)) == 1
    client.post("/report", data={**form, "website": "spam"}, follow_redirects=False)   # ловушка
    assert len(store.list_reports(c)) == 1
    r = client.post("/report", data={**form, "page": "https://evil.example"}, follow_redirects=False)
    assert r.headers["location"].startswith("/?")                                     # только свои адреса
    for _ in range(5):
        r = client.post("/report", data=form, follow_redirects=False)
    assert r.status_code == 429


def test_empty_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from public import app as app_module
    from public.data import Store
    monkeypatch.setattr(app_module, "store", Store())
    c = TestClient(app_module.app)
    assert c.get("/").status_code == 200
    assert c.get("/g/Б-Э-101").status_code == 503
    assert c.get("/healthz").json() == {"ok": True}
