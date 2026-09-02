from __future__ import annotations

from datetime import timedelta

import pytest

from coldchain.entities import CargoBatch, RefrigerationUnit
from coldchain.enums import HygieneCategory
from coldchain.physics import approach_temperature, update_cargo_temperature, update_refrigeration


def test_simulation_clock_advances(engine):
    start = engine.simulation_time
    engine.advance(17)
    assert engine.simulation_time == start + timedelta(minutes=17)


def test_speed_validation(engine):
    engine.set_speed(50)
    assert engine.speed == 50
    with pytest.raises(ValueError): engine.set_speed(3)


def test_random_seed_is_repeatable(engine, tmp_path):
    assert engine.random.random() == pytest.approx(0.41661987254534116)


def test_heat_exchange_never_teleports():
    result = approach_temperature(-20, 30, .01, 1)
    assert -20 < result < 30


def test_cargo_core_has_more_inertia_than_surface(engine):
    cargo = engine.cargo["ICE-0901-A"]
    before_core, before_surface = cargo.current_core_temperature, cargo.surface_temperature
    update_cargo_temperature(cargo, 30, 10, engine.config)
    assert cargo.surface_temperature - before_surface > cargo.current_core_temperature - before_core


def test_open_door_warms_truck_faster(engine):
    closed = engine.trucks["A02"].compartments["A02-C"]
    closed.current_temperature = 4
    engine.advance(5); closed_result = closed.current_temperature
    closed.current_temperature = 4; closed.door_open = True
    engine.advance(5)
    assert closed.current_temperature > closed_result


def test_refrigeration_hysteresis():
    unit = RefrigerationUnit(4, 1)
    temp, _ = update_refrigeration(unit, 7, 1, 2, -1, .05, 999, 20)
    assert unit.running and temp < 7
    unit.running = True
    update_refrigeration(unit, 2.5, 1, 2, -1, .05, 999, 20)
    assert not unit.running


def test_precooling_is_gradual(engine):
    engine.assign_truck("CL202609010001", "A02", "A02-C")
    initial = engine.trucks["A02"].compartments["A02-C"].current_temperature
    engine.start_precooling("CL202609010001")
    engine.advance(1)
    current = engine.trucks["A02"].compartments["A02-C"].current_temperature
    assert 4 < current < initial


def test_excursion_accumulates_and_quality_changes(engine):
    cargo = engine.cargo["YOGURT-0901-A"]
    cargo.current_core_temperature = cargo.surface_temperature = 15
    before = cargo.quality
    update_cargo_temperature(cargo, 20, 30, engine.config)
    assert cargo.excursion_minutes == 30
    assert cargo.degree_minutes > 0
    assert cargo.quality < before


def test_power_failure_is_gradual(engine):
    zone = engine.warehouses["WYS"].zones["WYS-F"]
    before = zone.current_temperature
    engine.set_warehouse_power("WYS", False)
    engine.advance(15)
    assert before < zone.current_temperature < engine.environment_temperature
    assert engine.cargo["ICE-0901-A"].current_core_temperature < zone.current_temperature

