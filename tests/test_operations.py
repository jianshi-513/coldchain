from __future__ import annotations

from datetime import timedelta

import pytest

from coldchain.enums import (
    CargoStatus, Compatibility, EquipmentStatus, HygieneStatus, OrderStatus,
)
from coldchain.hygiene import compatibility


def test_order_number_unique(engine):
    with pytest.raises(ValueError):
        engine.create_order("CL202609010001", "WYS", "FZ", ["ICE-0901-A"], engine.simulation_time+timedelta(hours=5), 145, 1000)


def test_demo_contains_operating_day(engine):
    assert len(engine.orders) == 8
    assert {engine.cargo[cid].name for order in engine.orders.values() for cid in order.cargo_ids} >= {
        "原味酸奶", "香草冰淇淋", "鲜果组合", "冷冻猪肉", "巴氏鲜奶", "冷藏叶菜", "速冻水饺"
    }


def test_refrigerated_truck_precools_within_one_hour(engine):
    order_id = "CL202609010001"
    engine.assign_truck(order_id, "A02", "A02-C")
    engine.start_precooling(order_id)
    engine.advance(60)
    assert engine.orders[order_id].status == OrderStatus.ALLOCATED
    assert engine.trucks["A02"].compartments["A02-C"].current_temperature <= 6


def test_freezer_truck_reaches_ice_cream_range(engine):
    order_id = "CL202609010002"
    engine.assign_truck(order_id, "A01", "A01-C")
    engine.start_precooling(order_id)
    engine.advance(60)
    assert engine.orders[order_id].status == OrderStatus.ALLOCATED
    assert engine.trucks["A01"].compartments["A01-C"].current_temperature <= -18


def test_fefo_selects_earliest_expiry(engine):
    selected = engine.select_fefo("DAI-YG-01", 200)
    assert selected[0] == "YOGURT-0828-B"


def test_vehicle_capacity(engine):
    cargo = engine.cargo["YOGURT-0901-A"]
    cargo.weight_kg = 4000
    with pytest.raises(ValueError): engine.assign_truck("CL202609010001", "A02", "A02-C")


def test_vehicle_temperature_match(engine):
    with pytest.raises(ValueError): engine.assign_truck("CL202609010001", "A01", "A01-C")


def test_multi_compartment_exists(engine):
    assert set(engine.trucks["A03"].compartments) == {"A03-F", "A03-C"}


def test_forklift_raw_meat_to_dairy_is_blocked(engine):
    verdict = compatibility(engine.forklifts["F01"], engine.cargo["YOGURT-0901-A"])
    assert verdict == Compatibility.PROHIBIT_UNLESS_OVERRIDE


def test_clean_then_disinfect(engine):
    engine.clean_forklift("F01")
    assert engine.forklifts["F01"].hygiene_status == HygieneStatus.REQUIRES_DISINFECTION
    engine.disinfect_forklift("F01")
    assert engine.forklifts["F01"].hygiene_status == HygieneStatus.CLEAN


def test_cannot_disinfect_visible_soil(engine):
    with pytest.raises(ValueError): engine.disinfect_forklift("F01")


def test_forced_hygiene_override_propagates_risk(engine):
    engine.assign_truck("CL202609010001", "A02", "A02-C")
    comp = engine.trucks["A02"].compartments["A02-C"]
    comp.current_temperature = 4
    engine.begin_fulfillment("CL202609010001", "F01", force=True)
    assert engine.cargo["YOGURT-0901-A"].contamination_risk > 50
    assert engine.orders["CL202609010001"].override_hygiene


def test_order_state_machine_to_departure(engine):
    oid = "CL202609010001"
    engine.assign_truck(oid, "A02", "A02-C")
    engine.trucks["A02"].compartments["A02-C"].current_temperature = 4
    engine.begin_fulfillment(oid, "F03")
    engine.advance(12+8+18)
    assert engine.orders[oid].status == OrderStatus.IN_TRANSIT
    assert engine.trucks["A02"].status == EquipmentStatus.IN_TRANSIT
    assert engine.cargo["YOGURT-0901-A"].status == CargoStatus.IN_TRANSIT


def test_transport_eta_and_traffic(engine):
    truck = engine.trucks["A02"]
    truck.status = EquipmentStatus.IN_TRANSIT; truck.distance_remaining_km = 10
    engine.add_traffic_delay("A02", 2)
    engine.advance(2)
    assert truck.distance_remaining_km == 10
    engine.advance(1)
    assert truck.distance_remaining_km < 10


def test_dock_capacity_causes_wait(engine):
    for dock in engine.warehouses["WYS"].docks.values(): dock.occupied_by = "OTHER"
    order = engine.orders["CL202609010001"]
    engine.assign_truck(order.order_id, "A02", "A02-C")
    engine.trucks["A02"].compartments["A02-C"].current_temperature = 4
    engine.begin_fulfillment(order.order_id, "F03")
    engine.advance(12+8)
    assert order.status == OrderStatus.STAGING


def test_refrigeration_fault(engine):
    engine.inject_refrigeration_fault("A01", "A01-C")
    assert engine.trucks["A01"].compartments["A01-C"].refrigeration.fault
    engine.repair_refrigeration("A01", "A01-C")
    assert not engine.trucks["A01"].compartments["A01-C"].refrigeration.fault


def test_recall_batch_lookup_fields(engine):
    cargo = engine.cargo["ICE-0901-A"]
    record = engine.recall_batch(cargo.batch_id, "教学演示")
    assert record["location"] == "WYS-F"
    assert cargo.status == CargoStatus.QUARANTINE


def test_sensor_bias_and_fault(engine):
    engine.set_sensor_fault("A02-C", "正常", bias=-3.0)
    measured = engine.sensor_value("A02-C", 10.0)
    assert 6.5 < measured < 7.5
    engine.set_sensor_fault("A02-C", "卡死", bias=-2.0)
    first = engine.sensor_value("A02-C", 10.0)
    assert engine.sensor_value("A02-C", 20.0) == first


def test_full_delivery_flow(engine):
    oid = "CL202609010001"
    engine.assign_truck(oid, "A02", "A02-C")
    engine.trucks["A02"].compartments["A02-C"].current_temperature = 4
    engine.begin_fulfillment(oid, "F03")
    engine.advance(38)
    truck = engine.trucks["A02"]
    truck.distance_remaining_km = 0
    engine.advance(1)
    assert engine.orders[oid].status == OrderStatus.ARRIVED
    engine.begin_unloading(oid); engine.advance(12)
    assert engine.orders[oid].status == OrderStatus.DELIVERED
    assert engine.order_report(oid)["订单号"] == oid
