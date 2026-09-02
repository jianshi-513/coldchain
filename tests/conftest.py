from __future__ import annotations

import copy
from pathlib import Path

import pytest

from coldchain.config import load_config
from coldchain.database import Database
from coldchain.engine import SimulationEngine


@pytest.fixture
def engine(tmp_path: Path) -> SimulationEngine:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "defaults.json")
    instance = SimulationEngine(copy.deepcopy(config), Database(tmp_path / "test.db"))
    yield instance
    instance.database.close()

