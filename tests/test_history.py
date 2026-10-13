from etl.dictionary import DICTIONARY_DIR
from etl.load import connect, ensure_loaded

OCHNO = [("Г-1", 0, "08:30", "лек. Физика Рыжова Е.В. 101"),
         ("Г-1", 0, "10:10", "пр.з. Химия Иванов И.И. 102"),
         ("Г-1", 1, "08:30", "лек. Право Петров П.П. 103"),
         ("Г-1", 2, "08:30", "лек. Экономика Сидоров С.С. 104")]


def load(tmp_path):
    conn = connect(tmp_path / "t.db")
    ensure_loaded(conn, tmp_path / "snapshots", DICTIONARY_DIR)
    return conn


def status(conn):
    return conn.execute("SELECT file_name, published FROM snapshots ORDER BY file_name").fetchall()


def test_first_published_and_changes_against_previous(tmp_path, make_snapshot):
    make_snapshot("a", "2026-10-10T03:00:00+04:00", OCHNO)
    changed = OCHNO[:1] + [("Г-1", 0, "10:10", "пр.з. Химия Иванов И.И. 202")] + OCHNO[2:]
    make_snapshot("b", "2026-10-11T03:00:00+04:00", changed)
    conn = load(tmp_path)
    assert status(conn) == [("a.json", 1), ("b.json", 1)]
    rows = conn.execute("SELECT kind, before, after FROM changes").fetchall()
    assert len(rows) == 1 and rows[0][0] == "changed" and "102" in rows[0][1] and "202" in rows[0][2]


def test_incomplete_collection_not_published(tmp_path, make_snapshot):
    make_snapshot("a", "2026-10-10T03:00:00+04:00", OCHNO)
    make_snapshot("b", "2026-10-11T03:00:00+04:00", OCHNO[:1])        # 1 из 4 занятий
    make_snapshot("c", "2026-10-12T03:00:00+04:00", OCHNO)
    conn = load(tmp_path)
    assert status(conn) == [("a.json", 1), ("b.json", 0), ("c.json", 1)]
    note = conn.execute("SELECT note FROM snapshots WHERE file_name='b.json'").fetchone()[0]
    assert "неполным" in note
    assert conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 0   # c сравнивается с a


def test_incremental_refresh_and_deleted_file(tmp_path, make_snapshot):
    make_snapshot("a", "2026-10-10T03:00:00+04:00", OCHNO)
    conn = load(tmp_path)
    p = make_snapshot("b", "2026-10-11T03:00:00+04:00", OCHNO[:3] + [("Г-1", 3, "08:30", OCHNO[3][3])])
    ensure_loaded(conn, tmp_path / "snapshots", DICTIONARY_DIR)
    assert [r[0] for r in conn.execute("SELECT kind FROM changes")] == ["moved"]
    p.unlink()
    ensure_loaded(conn, tmp_path / "snapshots", DICTIONARY_DIR)
    assert status(conn) == [("a.json", 1)]
    assert conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 0
