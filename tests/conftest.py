import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mini_snapshot_path() -> Path:
    return FIXTURES / "mini_snapshot.json"


@pytest.fixture
def mini_buildings(mini_snapshot_path) -> list[dict]:
    return json.loads(mini_snapshot_path.read_text())["buildings"]


DAY_NAMES = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]


def write_snapshot(path: Path, collected_at: str, ochno=(), zaoch=()) -> Path:
    """Снапшот в формате парсера.
    ochno: (группа, день 0..5, время "08:30", текст[, "numerator"|"denominator"]);
    zaoch: (группа, дата "YYYY-MM-DD", время, текст[, файл-источник])."""
    def end(t):
        h, m = map(int, t.split(":"))
        m += 90
        return f"{h + m // 60:02d}:{m % 60:02d}"

    def groups(rows, dated):
        out: dict[str, dict] = {}
        for r in rows:
            g, when, time, text, *rest = r
            grp = out.setdefault(g, {"name": g, "schedule": {"days": []}})
            if dated:
                from datetime import date
                d = date.fromisoformat(when)
                if rest:
                    grp["source"] = rest[0]
                day = next((x for x in grp["schedule"]["days"] if x.get("date") == when), None)
                if day is None:
                    day = {"name": DAY_NAMES[d.weekday()], "date": when, "lessons": []}
                    grp["schedule"]["days"].append(day)
            else:
                day = next((x for x in grp["schedule"]["days"] if x["name"] == DAY_NAMES[when]), None)
                if day is None:
                    day = {"name": DAY_NAMES[when], "lessons": []}
                    grp["schedule"]["days"].append(day)
            lesson = {"time_from": time, "time_to": end(time), "subject": text}
            if not dated and rest:
                lesson["week"] = rest[0]
            day["lessons"].append(lesson)
        return list(out.values())

    forms = []
    if ochno:
        forms.append({"name": "ochnaya-forma-obucheniya", "groups": groups(ochno, False)})
    if zaoch:
        forms.append({"name": "zaochnaya-forma-obucheniya", "groups": groups(zaoch, True)})
    data = {"collected_at": collected_at, "source_url": "test",
            "buildings": [{"name": "uk1", "institutes": [{"name": "institut-agrobiznesa", "forms": forms}]}]}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def make_snapshot(tmp_path):
    snaps = tmp_path / "snapshots"
    snaps.mkdir(exist_ok=True)

    def make(name: str, collected_at: str, ochno=(), zaoch=()) -> Path:
        return write_snapshot(snaps / f"{name}.json", collected_at, ochno, zaoch)
    return make
