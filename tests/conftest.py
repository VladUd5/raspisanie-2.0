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
