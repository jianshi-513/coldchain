from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .entities import SimEvent, TemperatureSample


class Database:
    """Small buffered SQLite event/sensor store; operational state remains in the engine."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._event_buffer: list[SimEvent] = []
        self._sample_buffer: list[TemperatureSample] = []
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS simulation_sessions (
              id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, simulation_time TEXT NOT NULL,
              random_seed INTEGER NOT NULL, state_json TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS event_logs (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, severity TEXT NOT NULL, category TEXT NOT NULL,
              entity_id TEXT, message TEXT NOT NULL, recommendation TEXT);
            CREATE INDEX IF NOT EXISTS ix_event_time ON event_logs(time);
            CREATE TABLE IF NOT EXISTS temperature_logs (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, entity_id TEXT NOT NULL, entity_type TEXT NOT NULL,
              air_temperature REAL NOT NULL, cargo_temperature REAL);
            CREATE INDEX IF NOT EXISTS ix_temp_entity_time ON temperature_logs(entity_id, time);
            CREATE TABLE IF NOT EXISTS audit_logs (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sanitation_logs (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, equipment_id TEXT NOT NULL, action TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS maintenance_logs (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, equipment_id TEXT NOT NULL, action TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS handover_logs (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, order_id TEXT NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recalls (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, batch_id TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL);
            """
        )
        self.connection.commit()

    def buffer_event(self, event: SimEvent) -> None:
        self._event_buffer.append(event)

    def buffer_sample(self, sample: TemperatureSample) -> None:
        self._sample_buffer.append(sample)

    def audit(self, time: datetime, action: str, detail: str) -> None:
        self.connection.execute(
            "INSERT INTO audit_logs(time, action, detail) VALUES(?,?,?)", (time.isoformat(), action, detail)
        )
        self.connection.commit()

    def sanitation(self, time: datetime, equipment_id: str, action: str, result: str) -> None:
        self.connection.execute(
            "INSERT INTO sanitation_logs(time,equipment_id,action,result) VALUES(?,?,?,?)",
            (time.isoformat(), equipment_id, action, result),
        )
        self.connection.commit()

    def flush(self) -> None:
        if self._event_buffer:
            self.connection.executemany(
                "INSERT INTO event_logs(time,severity,category,entity_id,message,recommendation) VALUES(?,?,?,?,?,?)",
                [(e.time.isoformat(), e.severity.value, e.category, e.entity_id, e.message, e.recommendation) for e in self._event_buffer],
            )
            self._event_buffer.clear()
        if self._sample_buffer:
            self.connection.executemany(
                "INSERT INTO temperature_logs(time,entity_id,entity_type,air_temperature,cargo_temperature) VALUES(?,?,?,?,?)",
                [(s.time.isoformat(), s.entity_id, s.entity_type, s.air_temperature, s.cargo_temperature) for s in self._sample_buffer],
            )
            self._sample_buffer.clear()
        self.connection.commit()

    def recent_events(self, limit: int = 100) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT ?", (limit,)))

    def export_events_csv(self, path: Path) -> None:
        rows = self.connection.execute("SELECT * FROM event_logs ORDER BY id").fetchall()
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["时间", "严重度", "类别", "对象", "内容", "建议"])
            writer.writerows((r["time"], r["severity"], r["category"], r["entity_id"], r["message"], r["recommendation"]) for r in rows)

    def close(self) -> None:
        self.flush()
        self.connection.close()

