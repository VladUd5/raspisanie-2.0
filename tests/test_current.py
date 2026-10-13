from analytics import current
from etl.dictionary import DICTIONARY_DIR
from etl.load import connect, ensure_loaded

# очников больше, чем заочников, как на сайте: смена недели заочки не выглядит неполным сбором
OCHNO = [("Г-1", day, "08:30", "лек. Физика Рыжова Е.В. 101") for day in range(6)]
W1 = [("З-1", "2026-10-12", "08:30", "лек. Физика Рыжова Е.В. 101"),
      ("З-1", "2026-10-14", "08:30", "лек. Химия Иванов И.И. 102"),
      ("З-1", "2026-10-16", "08:30", "лек. Право Петров П.П. 103")]


def load(tmp_path):
    conn = connect(tmp_path / "t.db")
    ensure_loaded(conn, tmp_path / "snapshots", DICTIONARY_DIR)
    return current.load(conn)


def rows(s, group):
    df = s.lessons[s.lessons["group_name"] == group].merge(s.rooms, on="lesson_id")
    return sorted(zip(df["date"], df["room"]))


def test_empty_db(tmp_path):
    (tmp_path / "snapshots").mkdir()
    assert load(tmp_path) is None


def test_week_dropped_from_site_stays_in_archive(tmp_path, make_snapshot):
    make_snapshot("a", "2026-10-11T03:00:00+04:00", OCHNO, W1)
    w2 = [("З-1", "2026-10-19", "08:30", "лек. Физика Рыжова Е.В. 101")]
    make_snapshot("b", "2026-10-18T03:00:00+04:00", OCHNO, w2)
    s = load(tmp_path)
    assert [d for d, _ in rows(s, "З-1")] == ["2026-10-12", "2026-10-14", "2026-10-16", "2026-10-19"]
    assert len(s.lessons[s.lessons["group_name"] == "Г-1"]) == 6     # недатированные — только из последнего


def test_version_on_the_day_counts_once(tmp_path, make_snapshot):
    make_snapshot("a", "2026-10-11T03:00:00+04:00", OCHNO, W1)
    # 13.10 неделю переделали: 14-е и 16-е — в другой аудитории
    v2 = [W1[0], (*W1[1][:3], "лек. Химия Иванов И.И. 202"), (*W1[2][:3], "лек. Право Петров П.П. 203")]
    make_snapshot("b", "2026-10-13T03:00:00+04:00", OCHNO, v2)
    # 15.10 ещё раз: 14-е уже прошло — его правка историю не переписывает, 16-е — новое
    v3 = [W1[0], (*W1[1][:3], "лек. Химия Иванов И.И. 302"), (*W1[2][:3], "лек. Право Петров П.П. 303")]
    make_snapshot("c", "2026-10-15T03:00:00+04:00", OCHNO, v3)
    s = load(tmp_path)
    assert rows(s, "З-1") == [("2026-10-12", "101"), ("2026-10-14", "202"), ("2026-10-16", "303")]


def test_week_published_before_first_collection_uses_earliest(tmp_path, make_snapshot):
    make_snapshot("a", "2026-10-20T03:00:00+04:00", OCHNO, W1)      # собрано уже после недели
    s = load(tmp_path)
    assert len(rows(s, "З-1")) == 3
