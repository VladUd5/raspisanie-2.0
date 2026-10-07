"""Каждая страница стенда рендерится без исключений — на данных и без данных."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "stand" / "app.py")
PAGES = ["overview", "teachers", "rooms", "disciplines", "groups", "quality", "spellings", "export"]


@pytest.fixture
def env(tmp_path, monkeypatch, mini_snapshot_path):
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    shutil.copy(mini_snapshot_path, snaps / "2026-10-07_120000.json")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PARSER_URL", "http://127.0.0.1:9")   # заведомо недоступен
    return tmp_path


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_data(env, page):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.switch_page(f"views/{page}.py")
    at.run()
    assert not at.exception, at.exception


def test_pages_survive_empty_selection(env):
    """Фильтры, после которых не осталось ни одного занятия, не роняют страницы."""
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    widgets = {m.key: m for m in at.get("multiselect")}
    widgets["f_groups"].select("бэ")
    widgets["f_days"].select("понедельник")      # у группы «бэ» занятия только в среду
    at.run()
    assert not at.exception
    for page in PAGES[1:]:
        at.switch_page(f"views/{page}.py")
        at.run()
        assert not at.exception, (page, at.exception)


def test_empty_database_shows_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Данных пока нет" in i.value for i in at.info)


def test_collect_without_parser_shows_error(env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.button[0].click()
    at.run()
    assert any("Сбор не удался" in e.value for e in at.error)


def test_sidebar_filter_changes_selection(env):
    # AppTest.switch_page исполняет файл страницы без app.py, поэтому фильтры
    # проверяем на стартовой странице, где боковая панель строится всегда.
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    selected = lambda: next(m for m in at.metric if m.label == "Занятий в текущей выборке").value
    assert selected() == "10"
    institutes = next(m for m in at.get("multiselect") if m.key == "f_institutes")
    institutes.select("Институт инженерии и робототехники")
    at.run()
    assert not at.exception
    assert selected() == "2"


def test_full_time_form_is_selected_by_default(env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    forms = next(m for m in at.get("multiselect") if m.key == "f_forms")
    assert forms.value == ["Очная"]


def _later_snapshot(src: Path, dst: Path, stamp: str = "2026-10-08T09:00:00+03:00") -> Path:
    import json
    data = json.loads(src.read_text())
    dst.write_text(json.dumps({**data, "collected_at": stamp}, ensure_ascii=False))
    return dst


def test_successful_collect_selects_new_snapshot(env, monkeypatch, mini_snapshot_path):
    """Успешный сбор не падает и выбирает новый снапшот (раньше — исключение
    StreamlitWidgetAlreadyInstantiatedError на каждом успешном сборе)."""
    import etl.collect

    def fake_collect(parser_url, schedule_url, snapshots_dir, timeout_s=900):
        return _later_snapshot(mini_snapshot_path, Path(snapshots_dir) / "2026-10-08_090000.json")

    monkeypatch.setattr(etl.collect, "collect", fake_collect)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.button[0].click()
    at.run()
    assert not at.exception, at.exception
    at.run()
    selected = at.selectbox(key="snapshot_id")
    assert len(selected.options) == 2
    assert selected.value == 2          # id нового снапшота; старый — 1


def test_snapshot_added_while_running_is_picked_up(env, mini_snapshot_path):
    """Файл, положенный в data/snapshots во время работы, появляется без перезапуска."""
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.selectbox(key="snapshot_id").options) == 1
    _later_snapshot(mini_snapshot_path, env / "snapshots" / "2026-10-08_090000.json")
    at.run()
    assert not at.exception
    assert len(at.selectbox(key="snapshot_id").options) == 2


def test_export_orders_days_by_week(env):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.switch_page("views/export.py")
    at.run()
    table = at.dataframe[0].value
    days = table[table["Группа"] == "Б-Э-101"]["День"].tolist()
    assert days.index("понедельник") < days.index("вторник")
