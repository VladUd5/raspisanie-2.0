from datetime import date

import pytest

import academic
import kug
import semester
from feedback import store


def _file(conn, url, code, courses):
    kug.save_file(conn, kug.KugFile(url, f"График_{code}_оч_2026-2027", "П", "Очная", code, courses), "ok", "")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k in ("AUTUMN_START", "AUTUMN_END", "SPRING_START", "SPRING_END", "HOLIDAYS_EXTRA", "WORKDAYS_EXTRA"):
        monkeypatch.delenv(k, raising=False)
    c = store.connect(tmp_path / "feedback.db")
    yield c
    c.close()


def _year(theory_end=date(2027, 1, 16), spring=date(2027, 2, 1)):
    return [("theory", date(2026, 9, 1), theory_end), ("session", date(2027, 1, 18), date(2027, 1, 28)),
            ("vacation", date(2027, 1, 29), date(2027, 1, 30)), ("theory", spring, date(2027, 6, 16)),
            ("session", date(2027, 6, 17), date(2027, 6, 26))]


def test_holidays_fixed_transfer_votes_and_env(conn, monkeypatch):
    cal = academic.calendar()
    assert cal.holiday(date(2026, 11, 4)) == "День народного единства"
    assert cal.holiday(date(2027, 1, 5)) == "Новогодние каникулы"
    assert cal.holiday(date(2027, 5, 10)).startswith("Выходной за день победы")      # 9 мая 2027 — воскресенье
    assert cal.holiday(date(2026, 11, 5)) == ""
    for i in range(6):                                                    # «=» в графиках — голоса
        _file(conn, f"/f/{i}.pdf", f"Б-А{'А' * i}", [1])
        kug.save_holidays(conn, f"/f/{i}.pdf", {date(2027, 1, 11)} | ({date(2027, 3, 1)} if i == 0 else set()))
    academic.reset()
    cal = academic.calendar()
    assert cal.holiday(date(2027, 1, 11)) and not cal.holiday(date(2027, 3, 1))      # один голос — шум
    monkeypatch.setenv("HOLIDAYS_EXTRA", "2027-03-01")
    monkeypatch.setenv("WORKDAYS_EXTRA", "2027-01-11")
    assert cal.holiday(date(2027, 3, 1)) and not cal.holiday(date(2027, 1, 11))


def test_semesters_from_graphs_and_week_parity(conn, monkeypatch):
    for i in range(6):
        url = f"/f/{i}.pdf"
        _file(conn, url, f"Б-В{'В' * i}", [1, 2])
        kug.save_drafts(conn, url, {1: _year(), 2: _year(date(2027, 1, 9), date(2027, 1, 25))})
    academic.reset()
    assert academic.calendar().semesters == [(date(2026, 9, 1), date(2027, 1, 16)), (date(2027, 2, 1), date(2027, 6, 16))]
    assert semester.semester_for(date(2027, 1, 12)) == (date(2026, 9, 1), date(2027, 1, 16))   # январь — ещё осень
    assert semester.semester_for(date(2027, 1, 20)) is None
    # чередование — от недели 1 сентября, сквозь зиму (как строка «В/Н» в графике)
    assert semester.week_type_on(date(2026, 9, 1)) == semester.UPPER
    assert semester.week_type_on(date(2026, 10, 14)) == semester.UPPER                 # 7-я неделя
    assert semester.week_type_on(date(2027, 2, 1)) == semester.UPPER                   # 23-я неделя
    assert semester.week_type_on(date(2027, 2, 8)) == semester.LOWER
    monkeypatch.setenv("SPRING_START", "2027-02-08")                                   # .env главнее графиков
    assert semester.semester_for(date(2027, 2, 3)) is None
    assert semester.week_type_on(date(2027, 2, 8)) == semester.UPPER


def test_group_kind_only_confirmed(conn):
    _file(conn, "/f/a.pdf", "Б-СТ", [1])
    kug.save_drafts(conn, "/f/a.pdf", {1: _year()})
    cal = academic.calendar()
    assert cal.kind_on("Б-СТ-101", "Очная", date(2027, 1, 20)) == ""                  # черновик не в счёт
    kug.confirm_drafts(conn, "/f/a.pdf")
    academic.reset()                              # на сайте — не позже TTL_S
    cal = academic.calendar()
    assert cal.kind_on("Б-СТ-101", "Очная", date(2027, 1, 20)) == "session"
    assert cal.kind_on("Б-СТ-101", "Очная", date(2027, 1, 12)) == "theory"
    assert cal.kind_on("Б-СТ-201", "Очная", date(2027, 1, 20)) == ""                  # другого курса нет
