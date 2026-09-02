from __future__ import annotations

from pathlib import Path


def test_event_buffer_flush(engine):
    engine.database.flush()
    assert len(engine.database.recent_events()) >= 1


def test_temperature_sampling_is_intervalled(engine):
    before = len(engine.samples)
    engine.advance(engine.config["simulation"]["sample_interval_minutes"])
    assert len(engine.samples) > before


def test_csv_export(engine, tmp_path: Path):
    engine.database.flush(); path = tmp_path / "events.csv"
    engine.database.export_events_csv(path)
    assert "创建订单" in path.read_text(encoding="utf-8-sig")

