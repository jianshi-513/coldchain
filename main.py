"""ColdChain Simulator application entry point."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from coldchain.config import load_config
from coldchain.database import Database
from coldchain.engine import SimulationEngine
from coldchain.ui.main_window import MainWindow


def main() -> int:
    root = Path(__file__).resolve().parent
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(root / "coldchain.log", encoding="utf-8"), logging.StreamHandler()],
    )
    config = load_config(root / "config" / "defaults.json")
    database = Database(root / "data" / "coldchain.db")
    engine = SimulationEngine(config=config, database=database)
    app = QApplication(sys.argv)
    app.setApplicationName("ColdChain Simulator")
    window = MainWindow(engine, database)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

