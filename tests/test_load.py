import shutil

import pytest

from etl.load import connect, ensure_loaded, load_snapshot, read_snapshot, suspicious_group


def _count(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def test_snapshot_counters(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    sid = load_snapshot(conn, mini_snapshot_path)
    row = conn.execute("SELECT groups_cnt, cells_cnt, lessons_cnt, service_cnt FROM snapshots WHERE id=?", (sid,)).fetchone()
    assert row == (3, 10, 10, 1)


def test_reload_is_idempotent(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path)
    load_snapshot(conn, mini_snapshot_path)
    assert _count(conn, "SELECT COUNT(*) FROM snapshots") == 1
    assert _count(conn, "SELECT COUNT(*) FROM lessons") == 10
    assert _count(conn, "SELECT COUNT(*) FROM lesson_teachers") == _count(
        conn, "SELECT COUNT(*) FROM lesson_teachers lt JOIN lessons l ON l.id = lt.lesson_id")


def test_split_cell_week_factor(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path)
    factors = conn.execute(
        "SELECT l.week_factor FROM lessons l JOIN cells c ON c.id = l.cell_id WHERE c.lessons_in_cell = 2").fetchall()
    assert factors == [(0.5,), (0.5,)]


def test_surname_resolved_and_typo_merged(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path)
    teachers = {r[0] for r in conn.execute("SELECT full_name FROM teachers")}
    assert "Шалаева Н.В." in teachers and "Шалаева" not in teachers
    assert {"Пяткина", "Балашова"} <= teachers
    disciplines = {r[0] for r in conn.execute("SELECT name FROM disciplines")}
    assert "Иностранный язык" in disciplines and "Иностанный язык" not in disciplines
    assert "Физика" in disciplines and "ФИЗИКА" not in disciplines


def test_same_room_number_in_two_buildings(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path)
    rooms = set(conn.execute("SELECT building, name FROM rooms WHERE name = '422'").fetchall())
    assert rooms == {("УК1", "422"), ("УК2", "422")}
    assert ("Прилегающие здания", "Физ. зал") in set(conn.execute("SELECT building, name FROM rooms").fetchall())


def test_quality_flags(tmp_path, mini_snapshot_path):
    conn = connect(tmp_path / "t.db")
    load_snapshot(conn, mini_snapshot_path)
    q = lambda col: _count(conn, f"SELECT SUM({col}) FROM quality")
    assert q("split_cell") == 2
    assert q("suspicious_group") == 2
    assert q("teacher_surname_only") == 3
    assert q("discipline_fuzzy") == 1


def test_ensure_loaded_loads_only_new(tmp_path, mini_snapshot_path):
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    shutil.copy(mini_snapshot_path, snaps / "a.json")
    conn = connect(tmp_path / "t.db")
    assert len(ensure_loaded(conn, snaps)[0]) == 1
    assert ensure_loaded(conn, snaps) == ([], [])


def test_broken_snapshot_is_skipped_with_error(tmp_path, mini_snapshot_path):
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    shutil.copy(mini_snapshot_path, snaps / "good.json")
    (snaps / "broken.json").write_text("{not json")
    conn = connect(tmp_path / "t.db")
    loaded, errors = ensure_loaded(conn, snaps)
    assert len(loaded) == 1
    assert [name for name, _ in errors] == ["broken.json"]


@pytest.mark.parametrize("name,expected", [
    ("Б-Э-101", False), ("М-ЗК-101", False), ("бэ", True), ("1", True), ("", True), ("-101", True)])
def test_suspicious_group_names(name, expected):
    assert suspicious_group(name) is expected


def test_bare_parser_list_is_accepted(tmp_path, mini_buildings):
    import json
    p = tmp_path / "raw.json"
    p.write_text(json.dumps(mini_buildings, ensure_ascii=False))
    assert len(read_snapshot(p)["buildings"]) == 2
