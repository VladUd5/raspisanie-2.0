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
    assert "изменено" in r.text and "Было:" in r.text            # аудитория химии поменялась вчера
    assert "1 пара" in r.text and "data-wk" in r.text
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


def test_day_and_subgroup_params_are_safe(client):
    for params in ({"day": "9"}, {"day": "x"}, {"sub": "7"}, {"sub": "-1"}, {"day": "2", "sub": "1"}):
        assert client.get("/g/Б-Э-101", params=params).status_code == 200
    assert 'data-show="2"' in client.get("/g/Б-Э-101", params={"day": "2"}).text


@pytest.fixture
def mixed_client(tmp_path, monkeypatch, make_snapshot):
    """Шалаева ведёт и у очников, и у заочников."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    m = monday(today())
    zao = zao_week(m) + [("З-ЭК-51", (m + timedelta(days=3)).isoformat(), "12:00", "лек. Право Шалаева Н.В. 102")]
    make_snapshot("a", (today() - timedelta(days=1)).isoformat() + "T03:00:00+04:00", OCHNO, zao)
    conn = connect(tmp_path / "schedule.db")
    ensure_loaded(conn, tmp_path / "snapshots", DICTIONARY_DIR)
    conn.close()
    from public import app as app_module
    from public.data import Store
    monkeypatch.setattr(app_module, "store", Store())
    return TestClient(app_module.app)


def test_teacher_form_switch_and_marks(mixed_client):
    teacher = next(e for e in mixed_client.get("/api/search", params={"q": "шалаева"}).json()
                   if e["kind"] == "преподаватель")
    page = mixed_client.get(teacher["url"])
    assert page.status_code == 200
    assert "Все формы" in page.text and "?form=zaoch" in page.text and "?form=och" in page.text
    assert 'class="tag form">заочн.' in page.text and "Форма обучения" in page.text
    zao = mixed_client.get(teacher["url"], params={"form": "zaoch"}).text
    assert "Право" in zao and "История России" not in zao
    och = mixed_client.get(teacher["url"], params={"form": "och"}).text
    assert "История России" in och and "Право" not in och and "form=och" in och
    assert mixed_client.get(teacher["url"], params={"form": "мусор"}).status_code == 200
    # на странице группы переключателя нет
    assert "Все формы" not in mixed_client.get("/g/Б-Э-101").text


def test_teacher_ics_form_filter(mixed_client):
    url = next(e for e in mixed_client.get("/api/search", params={"q": "шалаева"}).json()
               if e["kind"] == "преподаватель")["url"]
    get = lambda **p: mixed_client.get(url + ".ics", params=p).text.replace("\r\n ", "")   # склеить перенос строк
    full, zao, och = get(), get(form="zaoch"), get(form="och")
    assert "Право" in full and "История России" in full
    assert "Право" in zao and "История России" not in zao and "заочная форма" in zao
    assert "История России" in och and "Право" not in och
    uid = lambda body: {l for l in body.split("\r\n") if l.startswith("UID:")}
    assert uid(zao) <= uid(full) and uid(och) <= uid(full) and not uid(zao) & uid(och)
    assert get(form="мусор").count("BEGIN:VEVENT") == full.count("BEGIN:VEVENT")
    assert "?form=zaoch" in mixed_client.get(url).text.split('id="calendar"')[1]


def test_stats_tab_discipline_page_and_excel(client):
    r = client.get("/g/Б-Э-101", params={"view": "stats"})
    assert r.status_code == 200 and "Семестр" in r.text and 'aria-current="page">Аналитика' in r.text
    assert "История России" in r.text                                      # строка таблицы дисциплин
    hits = client.get("/api/search", params={"q": "история рос"}).json()
    disc = next(e for e in hits if e["kind"] == "дисциплина")
    page = client.get(disc["url"])
    assert page.status_code == 200 and "Б-Э-101" in page.text and "Б-БИ-101" in page.text
    assert client.get(disc["url"], params={"view": "stats"}).status_code == 200
    x = client.get("/g/Б-Э-101", params={"view": "stats", "format": "xlsx"})
    assert x.headers["content-type"].startswith("application/vnd.openxmlformats") and x.content[:2] == b"PK"
    teacher = client.get("/api/search", params={"q": "шалаева"}).json()[0]["url"]
    assert "Аналитика" in client.get(teacher, params={"view": "stats"}).text
    assert client.get("/d/Нет такой дисциплины").status_code == 404


def test_teacher_card_from_directory(client, tmp_path):
    import json
    (tmp_path / "directory.json").write_text(json.dumps({
        "fetched_at": "2026-10-13T10:00:00+04:00",
        "departments": [{"name": "История", "head": "", "email": "kaf-hist@vavilovsar.ru", "phone": "8 (8452) 00-00-00",
                         "address": "", "site": "https://site/kafedry/istoriya", "teacher_rooms": ["412"]}],
        "people": [{"full_name": "Шалаева Наталья Владимировна", "post": "Доцент", "degree": "канд. ист. наук",
                    "title": "доцент", "department": "История", "email": ""}]}, ensure_ascii=False), encoding="utf-8")
    url = client.get("/api/search", params={"q": "шалаева"}).json()[0]["url"]
    page = client.get(url).text
    assert "Шалаева Наталья Владимировна" in page and "Доцент, канд. ист. наук" in page
    assert "Кафедра «История»" in page and "ауд. 412" in page and "kaf-hist@vavilovsar.ru" in page
    assert "каф. «История»" in client.get("/g/Б-Э-101").text                 # в подробностях занятия


def test_holiday_and_confirmed_session_hide_weekly_lessons(client, tmp_path):
    import academic
    import kug
    from feedback import store
    r = client.get("/g/Б-Э-101", params={"week": "2026-11-02"})            # ср 4 ноября — праздник
    assert "День народного единства" in r.text and "Химия" not in r.text and "История России" in r.text
    conn = store.connect(tmp_path / "feedback.db")
    f = kug.KugFile("/f/e.pdf", "График_Б-Э_1-4курс_оч_2026-2027", "П", "Очная", "Б-Э", [1, 2, 3, 4])
    kug.save_file(conn, f, "ok", "")
    kug.save_drafts(conn, f.url, {1: [("theory", date(2026, 9, 1), date(2026, 11, 7)),
                                      ("session", date(2026, 11, 9), date(2026, 11, 14))]})
    r = client.get("/g/Б-Э-101", params={"week": "2026-11-09"})
    assert "История России" in r.text                                       # черновик ничего не прячет
    kug.confirm_drafts(conn, f.url)
    conn.close()
    academic.reset()
    r = client.get("/g/Б-Э-101", params={"week": "2026-11-09"})
    assert "По графику учебного процесса: сессия 9 ноября – 14 ноября" in r.text and "История России" not in r.text
    assert "История России" in client.get("/g/Б-БИ-101", params={"week": "2026-11-09"}).text   # у другой группы — нет
