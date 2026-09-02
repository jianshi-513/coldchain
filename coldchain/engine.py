from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from .database import Database
from .demo import create_demo
from .entities import CargoBatch, Order, Sensor, SimEvent, TemperatureSample, to_jsonable
from .enums import CargoStatus, Compatibility, EquipmentStatus, HygieneStatus, OrderStatus, Severity
from .hygiene import apply_cross_contamination, compatibility, expose_forklift
from .physics import approach_temperature, update_cargo_temperature, update_refrigeration


class SimulationEngine(QObject):
    tick_completed = Signal()
    event_created = Signal(object)
    running_changed = Signal(bool)

    SPEEDS = (1, 2, 5, 10, 20, 50, 100)

    def __init__(self, config: dict[str, Any], database: Database):
        super().__init__()
        self.config = config
        sim = config["simulation"]
        self.simulation_time = datetime.fromisoformat(sim["start_time"])
        self.tick_minutes = int(sim["tick_minutes"])
        self.random_seed = int(sim["random_seed"])
        self.random = random.Random(self.random_seed)
        self.database = database
        self.warehouses, self.trucks, self.forklifts, self.cargo = create_demo(self.simulation_time)
        self.orders: dict[str, Order] = {}
        entity_ids = [z.zone_id for w in self.warehouses.values() for z in w.zones.values()]
        entity_ids += [c.compartment_id for t in self.trucks.values() for c in t.compartments.values()]
        self.sensors = {f"S-{eid}": Sensor(f"S-{eid}", eid) for eid in entity_ids}
        self.recalls: list[dict[str, str]] = []
        self.events: list[SimEvent] = []
        self.samples: list[TemperatureSample] = []
        self.weather = config["environment"]["weather"]
        self.environment_temperature = config["environment"]["base_temperature"]
        self.humidity = config["environment"]["humidity"]
        self.speed = 10
        self.running = False
        self.elapsed_minutes = 0
        self.total_energy_kwh = 0.0
        self.total_cost = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer)
        self._create_demo_orders()
        self._sample_all()

    def _create_demo_orders(self) -> None:
        """Seed a small operating day instead of a single scripted order."""
        orders = [
            ("CL202609010001", "FZ", ["YOGURT-0901-A"], 5, 145.0, 3600.0),
            ("CL202609010002", "FZ", ["ICE-0901-A"], 7, 145.0, 4200.0),
            ("CL202609010003", "XM", ["FRUIT-0901-A"], 10, 365.0, 5100.0),
            ("CL202609010004", "NC", ["PORK-0830-L"], 12, 425.0, 6800.0),
            ("CL202609010005", "XM", ["YOGURT-0828-B"], 9, 365.0, 2800.0),
            ("CL202609010006", "FZ", ["MILK-0901-A"], 6, 145.0, 3300.0),
            ("CL202609010007", "XM", ["VEG-0901-A"], 11, 365.0, 4600.0),
            ("CL202609010008", "NC", ["DUMPLING-0901-A"], 13, 425.0, 5700.0),
        ]
        for order_id, destination, cargo_ids, deadline_hours, distance, revenue in orders:
            self.create_order(
                order_id, "WYS", destination, cargo_ids,
                self.simulation_time + timedelta(hours=deadline_hours), distance, revenue,
            )

    def set_running(self, running: bool) -> None:
        self.running = running
        if running:
            self._timer.start()
        else:
            self._timer.stop()
            self.database.flush()
        self.running_changed.emit(running)

    def set_speed(self, speed: int) -> None:
        if speed not in self.SPEEDS:
            raise ValueError(f"unsupported speed: {speed}")
        self.speed = speed

    def _on_timer(self) -> None:
        self.advance(self.tick_minutes * self.speed)

    def advance(self, minutes: int = 1) -> None:
        """Advance in one-minute substeps for stable state transitions and repeatability."""
        for _ in range(max(0, minutes)):
            self.simulation_time += timedelta(minutes=1)
            self.elapsed_minutes += 1
            self._update_environment()
            self._update_zones()
            self._update_trucks()
            self._update_orders()
            self._update_forklifts()
            self._check_alerts()
            if self.elapsed_minutes % self.config["simulation"]["sample_interval_minutes"] == 0:
                self._sample_all()
                self.database.flush()
        self.tick_completed.emit()

    def _update_environment(self) -> None:
        env = self.config["environment"]
        hour = self.simulation_time.hour + self.simulation_time.minute / 60
        # Daily maximum near 15:00 and minimum near 03:00.
        self.environment_temperature = env["base_temperature"] + env["daily_amplitude"] * math.cos((hour - 15) * math.pi / 12)

    def _refrigerate(self, unit, temperature: float) -> tuple[float, float]:
        r = self.config["refrigeration"]
        return update_refrigeration(
            unit, temperature, 1, r["hysteresis_high"], r["hysteresis_low"],
            r["energy_kwh_per_minute"], r["defrost_interval_minutes"],
            r["defrost_duration_minutes"], self.config["thermal"]["cooling_rate"],
        )

    def _update_zones(self) -> None:
        thermal = self.config["thermal"]
        for warehouse in self.warehouses.values():
            for zone in warehouse.zones.values():
                exchange = thermal["zone_exchange"] * (thermal["door_open_multiplier"] if zone.door_open else 1)
                zone.current_temperature = approach_temperature(zone.current_temperature, self.environment_temperature, exchange, 1)
                zone.refrigeration.fault = not (warehouse.power_status or warehouse.emergency_power or zone.emergency_power)
                zone.current_temperature, used = self._refrigerate(zone.refrigeration, zone.current_temperature)
                self.total_energy_kwh += used
                for cargo_id in list(zone.cargo_ids):
                    if cargo_id in self.cargo:
                        update_cargo_temperature(self.cargo[cargo_id], zone.current_temperature, 1, self.config)

    def _update_trucks(self) -> None:
        thermal = self.config["thermal"]
        for truck in self.trucks.values():
            for compartment in truck.compartments.values():
                exchange = thermal["truck_exchange"] * (thermal["door_open_multiplier"] if compartment.door_open else 1)
                if truck.status == EquipmentStatus.IN_TRANSIT:
                    exchange *= .75
                compartment.current_temperature = approach_temperature(compartment.current_temperature, self.environment_temperature, exchange, 1)
                compartment.current_temperature, used = self._refrigerate(compartment.refrigeration, compartment.current_temperature)
                truck.energy_kwh += used
                self.total_energy_kwh += used
                if compartment.door_open:
                    compartment.door_open_minutes += 1
                    compartment.longest_door_open = max(compartment.longest_door_open, compartment.door_open_minutes)
                for cargo_id in compartment.cargo_ids:
                    update_cargo_temperature(self.cargo[cargo_id], compartment.current_temperature, 1, self.config)
            if truck.status == EquipmentStatus.IN_TRANSIT:
                if truck.traffic_delay_minutes > 0:
                    truck.traffic_delay_minutes -= 1
                else:
                    truck.distance_remaining_km = max(0, truck.distance_remaining_km - truck.speed_kmh / 60)

    def create_order(self, order_id: str, origin: str, destination: str, cargo_ids: list[str], deadline: datetime, distance_km: float, revenue: float) -> Order:
        if order_id in self.orders:
            raise ValueError("订单号已存在")
        if not cargo_ids or any(item not in self.cargo for item in cargo_ids):
            raise ValueError("货物批次不存在")
        order = Order(order_id, origin, destination, cargo_ids, self.simulation_time, deadline, distance_km, revenue)
        self.orders[order_id] = order
        self.emit_event(Severity.INFO, "订单", f"创建订单 {order_id}", order_id)
        return order

    def select_fefo(self, sku: str, required_weight: float) -> list[str]:
        batches = sorted(
            (c for c in self.cargo.values() if c.sku == sku and c.status == CargoStatus.AVAILABLE),
            key=lambda c: c.expiry_date,
        )
        selected, accumulated = [], 0.0
        for batch in batches:
            selected.append(batch.batch_id)
            accumulated += batch.weight_kg
            if accumulated >= required_weight:
                return selected
        raise ValueError("可用库存不足")

    def recommend_truck(self, order_id: str) -> list[tuple[str, str, float]]:
        order = self.orders[order_id]
        cargo = [self.cargo[cid] for cid in order.cargo_ids]
        weight = sum(c.weight_kg for c in cargo)
        volume = sum(c.volume_m3 for c in cargo)
        pallets = sum(c.pallet_count for c in cargo)
        result = []
        for truck in self.trucks.values():
            if truck.status not in {EquipmentStatus.IDLE, EquipmentStatus.PRECOOLING} and truck.order_id != order_id:
                continue
            for comp in truck.compartments.values():
                temp_penalty = sum(max(0, abs(comp.target_temperature - c.target_temperature) - 3) for c in cargo)
                if weight <= comp.max_weight and volume <= comp.max_volume and pallets <= comp.max_pallets:
                    score = 100 - temp_penalty * 15 - abs(comp.current_temperature - cargo[0].target_temperature)
                    result.append((truck.truck_id, comp.compartment_id, score))
        return sorted(result, key=lambda item: item[2], reverse=True)

    def assign_truck(self, order_id: str, truck_id: str, compartment_id: str, force: bool = False) -> None:
        order, truck = self.orders[order_id], self.trucks[truck_id]
        compartment = truck.compartments[compartment_id]
        cargo = [self.cargo[item] for item in order.cargo_ids]
        weight, volume, pallets = sum(c.weight_kg for c in cargo), sum(c.volume_m3 for c in cargo), sum(c.pallet_count for c in cargo)
        invalid = weight > compartment.max_weight or volume > compartment.max_volume or pallets > compartment.max_pallets
        poor_temp = any(abs(compartment.target_temperature - c.target_temperature) > 5 for c in cargo)
        if (invalid or poor_temp) and not force:
            raise ValueError("车辆容量或温区不匹配；可选择强制分配")
        order.truck_id, order.compartment_id = truck_id, compartment_id
        order.status = OrderStatus.ALLOCATED
        truck.order_id = order_id
        for item in order.cargo_ids:
            self.cargo[item].order_id = order_id
            self.cargo[item].status = CargoStatus.ALLOCATED
        if invalid or poor_temp:
            self.database.audit(self.simulation_time, "强制分配车辆", f"{truck_id} → {order_id}，容量/温区不匹配")
            self.emit_event(Severity.CRITICAL, "合规", f"强制将不匹配车辆 {truck_id} 分配给订单", order_id, "更换合适车辆")
        else:
            self.emit_event(Severity.INFO, "调度", f"车辆 {truck_id} 已分配", order_id)

    def start_precooling(self, order_id: str) -> None:
        order = self.orders[order_id]
        if not order.truck_id:
            raise ValueError("请先分配车辆")
        truck = self.trucks[order.truck_id]
        cargo_target = self.cargo[order.cargo_ids[0]].target_temperature
        compartment = truck.compartments[order.compartment_id]
        compartment.refrigeration.target_temperature = cargo_target
        compartment.target_temperature = cargo_target
        compartment.refrigeration.fault = False
        truck.status = EquipmentStatus.PRECOOLING
        order.status = OrderStatus.PRECOOLING
        self.emit_event(Severity.INFO, "预冷", f"{truck.truck_id} 开始预冷，目标 {cargo_target:.1f}℃", order_id)

    def recommend_forklift(self, order_id: str) -> list[tuple[str, Compatibility]]:
        cargo = self.cargo[self.orders[order_id].cargo_ids[0]]
        candidates = [(f.forklift_id, compatibility(f, cargo)) for f in self.forklifts.values() if f.status == EquipmentStatus.IDLE]
        rank = {Compatibility.ALLOW: 0, Compatibility.WARNING: 1, Compatibility.REQUIRE_CLEANING: 2, Compatibility.REQUIRE_CLEAN_AND_DISINFECT: 3, Compatibility.PROHIBIT_UNLESS_OVERRIDE: 4}
        return sorted(candidates, key=lambda item: rank[item[1]])

    def begin_fulfillment(self, order_id: str, forklift_id: str, force: bool = False) -> None:
        order, forklift = self.orders[order_id], self.forklifts[forklift_id]
        if not order.truck_id:
            raise ValueError("请先分配车辆")
        cargo = self.cargo[order.cargo_ids[0]]
        comp = self.trucks[order.truck_id].compartments[order.compartment_id]
        if comp.current_temperature > cargo.max_temperature + 2 and not force:
            raise ValueError(f"车厢尚未预冷到位（当前 {comp.current_temperature:.1f}℃）")
        verdict = compatibility(forklift, cargo)
        if verdict == Compatibility.PROHIBIT_UNLESS_OVERRIDE and not force:
            raise ValueError("叉车卫生状态不兼容；必须清洁消毒或明确强制作业")
        order.forklift_id = forklift_id
        order.override_hygiene = force and verdict != Compatibility.ALLOW
        order.status = OrderStatus.PICKING
        order.phase_remaining = self.config["operations"]["picking_minutes"]
        forklift.status = EquipmentStatus.BUSY
        forklift.task = f"订单 {order_id} 拣货"
        forklift.remaining_minutes = order.phase_remaining
        for item in order.cargo_ids:
            self.cargo[item].status = CargoStatus.PICKING
        if force and verdict != Compatibility.ALLOW:
            for item in order.cargo_ids:
                apply_cross_contamination(forklift, self.cargo[item])
            self.database.audit(self.simulation_time, "强制卫生不兼容作业", f"{forklift_id} → {order_id}，{verdict.value}")
            self.emit_event(Severity.CRITICAL, "卫生", f"强制使用卫生不兼容叉车 {forklift_id}", order_id, "隔离货物并评估")
        self.emit_event(Severity.INFO, "作业", f"{forklift_id} 开始拣货", order_id)

    def _update_orders(self) -> None:
        ops = self.config["operations"]
        for order in self.orders.values():
            if order.status == OrderStatus.PRECOOLING and order.truck_id:
                cargo = self.cargo[order.cargo_ids[0]]
                comp = self.trucks[order.truck_id].compartments[order.compartment_id]
                if comp.current_temperature <= cargo.max_temperature:
                    self.trucks[order.truck_id].status = EquipmentStatus.IDLE
                    order.status = OrderStatus.ALLOCATED
                    self.emit_event(Severity.INFO, "预冷", f"{order.truck_id} 预冷完成：{comp.current_temperature:.1f}℃", order.order_id)
            elif order.status in {OrderStatus.PICKING, OrderStatus.STAGING, OrderStatus.LOADING, OrderStatus.UNLOADING}:
                order.phase_remaining -= 1
                order.labor_cost += self.config["costs"]["labor_per_minute"]
                if order.phase_remaining <= 0:
                    self._finish_phase(order)
            elif order.status == OrderStatus.IN_TRANSIT and order.truck_id:
                truck = self.trucks[order.truck_id]
                if truck.distance_remaining_km <= 0:
                    order.status = OrderStatus.ARRIVED
                    order.actual_arrival = self.simulation_time
                    truck.status = EquipmentStatus.IDLE
                    truck.location = self.warehouses[order.destination].name
                    self.emit_event(Severity.INFO, "运输", f"{truck.truck_id} 到达目的仓，封签 {truck.seal_number} 待核验", order.order_id)

    def _finish_phase(self, order: Order) -> None:
        forklift = self.forklifts[order.forklift_id] if order.forklift_id else None
        truck = self.trucks[order.truck_id] if order.truck_id else None
        compartment = truck.compartments[order.compartment_id] if truck else None
        if order.status == OrderStatus.PICKING:
            for cid in order.cargo_ids:
                cargo = self.cargo[cid]
                if cargo.location in self.warehouses[order.origin].zones:
                    zone = self.warehouses[order.origin].zones[cargo.location]
                    if cid in zone.cargo_ids:
                        zone.cargo_ids.remove(cid)
                cargo.location = "WYS-S"
                cargo.status = CargoStatus.STAGING
                self.warehouses[order.origin].zones["WYS-S"].cargo_ids.append(cid)
            order.status, order.phase_remaining = OrderStatus.STAGING, 8
            self.emit_event(Severity.INFO, "作业", "货物进入发货暂存区，等待月台", order.order_id)
        elif order.status == OrderStatus.STAGING:
            dock = next((d for d in self.warehouses[order.origin].docks.values() if d.occupied_by is None), None)
            if dock is None:
                order.phase_remaining = 1
                return
            dock.occupied_by = truck.truck_id
            dock.door_open = True
            compartment.door_open = True
            compartment.door_open_count += 1
            order.status, order.phase_remaining = OrderStatus.LOADING, self.config["operations"]["loading_minutes"]
            self.emit_event(Severity.INFO, "月台", f"分配 {dock.name}，打开车门开始装车", order.order_id)
        elif order.status == OrderStatus.LOADING:
            for cid in order.cargo_ids:
                staging = self.warehouses[order.origin].zones["WYS-S"]
                if cid in staging.cargo_ids:
                    staging.cargo_ids.remove(cid)
                compartment.cargo_ids.append(cid)
                self.cargo[cid].location = f"{truck.truck_id}/{compartment.compartment_id}"
                self.cargo[cid].status = CargoStatus.IN_TRANSIT
                expose_forklift(forklift, self.cargo[cid])
            compartment.door_open = False
            for dock in self.warehouses[order.origin].docks.values():
                if dock.occupied_by == truck.truck_id:
                    dock.occupied_by, dock.door_open = None, False
            truck.seal_number = f"SEAL-{order.order_id[-6:]}"
            truck.status = EquipmentStatus.IN_TRANSIT
            truck.destination = self.warehouses[order.destination].name
            truck.distance_remaining_km = order.distance_km
            order.status = OrderStatus.IN_TRANSIT
            order.actual_departure = self.simulation_time
            forklift.status, forklift.task, forklift.remaining_minutes = EquipmentStatus.IDLE, "", 0
            self.emit_event(Severity.INFO, "运输", f"{truck.truck_id} 已封签发车", order.order_id)
        elif order.status == OrderStatus.UNLOADING:
            for cid in order.cargo_ids:
                if cid in compartment.cargo_ids:
                    compartment.cargo_ids.remove(cid)
                cargo = self.cargo[cid]
                dest_zone = next(iter(self.warehouses[order.destination].zones.values()))
                dest_zone.cargo_ids.append(cid)
                cargo.location = dest_zone.zone_id
                cargo.status = CargoStatus.DELIVERED if cargo.quality >= self.config["quality"]["quarantine_threshold"] else CargoStatus.QUARANTINE
            order.status = OrderStatus.DELIVERED
            order.energy_cost = truck.energy_kwh * self.config["costs"]["energy_per_kwh"]
            order.loss_cost = sum((100-self.cargo[c].quality)*self.cargo[c].weight_kg*self.config["costs"]["loss_per_quality_point_kg"] for c in order.cargo_ids)
            if self.simulation_time > order.deadline:
                order.penalty = 500
            truck.order_id = None
            compartment.door_open = False
            self.database.audit(self.simulation_time, "订单签收", f"{order.order_id} 已完成，封签核对通过")
            self.emit_event(Severity.INFO, "交接", f"订单签收完成，利润 ¥{order.profit:.2f}", order.order_id)

    def begin_unloading(self, order_id: str) -> None:
        order = self.orders[order_id]
        if order.status != OrderStatus.ARRIVED:
            raise ValueError("订单尚未到达")
        comp = self.trucks[order.truck_id].compartments[order.compartment_id]
        comp.door_open = True
        comp.door_open_count += 1
        order.status = OrderStatus.UNLOADING
        order.phase_remaining = self.config["operations"]["unloading_minutes"]
        self.emit_event(Severity.INFO, "交接", "封签核对通过，开始卸货", order_id)

    def _update_forklifts(self) -> None:
        for forklift in self.forklifts.values():
            if forklift.status == EquipmentStatus.BUSY and forklift.remaining_minutes > 0:
                forklift.remaining_minutes -= 1
                forklift.battery_percent = max(0, forklift.battery_percent - .06)

    def clean_forklift(self, forklift_id: str) -> None:
        forklift = self.forklifts[forklift_id]
        forklift.contamination_level = max(0, forklift.contamination_level - 60)
        forklift.hygiene_status = HygieneStatus.REQUIRES_DISINFECTION if forklift.contamination_level > 0 else HygieneStatus.CLEAN
        self.database.sanitation(self.simulation_time, forklift_id, "清洁", forklift.hygiene_status.value)
        self.emit_event(Severity.INFO, "卫生", f"{forklift_id} 完成清洁；仍需消毒", forklift_id)

    def disinfect_forklift(self, forklift_id: str) -> None:
        forklift = self.forklifts[forklift_id]
        if forklift.hygiene_status == HygieneStatus.REQUIRES_BOTH:
            raise ValueError("存在明显污物，必须先清洁再消毒")
        forklift.contamination_level = max(0, forklift.contamination_level - 40)
        forklift.hygiene_status = HygieneStatus.CLEAN if forklift.contamination_level <= 1 else HygieneStatus.REQUIRES_DISINFECTION
        self.database.sanitation(self.simulation_time, forklift_id, "消毒", forklift.hygiene_status.value)
        self.emit_event(Severity.INFO, "卫生", f"{forklift_id} 完成消毒：{forklift.hygiene_status.value}", forklift_id)

    def inject_refrigeration_fault(self, truck_id: str, compartment_id: str) -> None:
        comp = self.trucks[truck_id].compartments[compartment_id]
        comp.refrigeration.fault = True
        self.trucks[truck_id].maintenance_state = "制冷故障"
        self.emit_event(Severity.CRITICAL, "设备故障", f"{truck_id} 制冷系统故障", truck_id, "就近转运、换车或返回")
        self.database.audit(self.simulation_time, "人工制造故障", f"{truck_id}/{compartment_id} 制冷故障")

    def repair_refrigeration(self, truck_id: str, compartment_id: str) -> None:
        self.trucks[truck_id].compartments[compartment_id].refrigeration.fault = False
        self.trucks[truck_id].maintenance_state = "正常"
        self.emit_event(Severity.INFO, "设备维护", f"{truck_id} 制冷系统恢复", truck_id)

    def set_warehouse_power(self, warehouse_id: str, enabled: bool) -> None:
        warehouse = self.warehouses[warehouse_id]
        warehouse.power_status = enabled
        self.database.audit(self.simulation_time, "供电干预", f"{warehouse_id} 供电={enabled}")
        self.emit_event(Severity.CRITICAL if not enabled else Severity.INFO, "供电", f"{warehouse.name}{'恢复供电' if enabled else '发生停电'}", warehouse_id, "检查备用电源" if not enabled else "")

    def add_traffic_delay(self, truck_id: str, minutes: int = 25) -> None:
        self.trucks[truck_id].traffic_delay_minutes += minutes
        self.emit_event(Severity.WARNING, "运输", f"{truck_id} 遭遇拥堵，预计延误 {minutes} 分钟", truck_id)

    def set_door(self, truck_id: str, compartment_id: str, opened: bool) -> None:
        comp = self.trucks[truck_id].compartments[compartment_id]
        if opened and not comp.door_open:
            comp.door_open_count += 1
        comp.door_open = opened
        self.database.audit(self.simulation_time, "车门操作", f"{truck_id}/{compartment_id} {'开启' if opened else '关闭'}")

    def set_sensor_fault(self, entity_id: str, mode: str, bias: float = 0.0) -> None:
        sensor = next((s for s in self.sensors.values() if s.entity_id == entity_id), None)
        if sensor is None:
            raise ValueError("传感器对象不存在")
        if mode not in {"正常", "卡死", "离线"}:
            raise ValueError("不支持的传感器状态")
        sensor.fault_mode, sensor.bias = mode, bias
        if mode == "正常":
            sensor.stuck_value = None
        self.database.audit(self.simulation_time, "传感器干预", f"{entity_id} 状态={mode} 偏差={bias:+.1f}℃")
        self.emit_event(Severity.WARNING if mode != "正常" or bias else Severity.INFO, "传感器", f"{entity_id} 传感器设为 {mode}，偏差 {bias:+.1f}℃", entity_id)

    def sensor_value(self, entity_id: str, true_value: float) -> float | None:
        sensor = next((s for s in self.sensors.values() if s.entity_id == entity_id), None)
        return sensor.measure(true_value, self.random) if sensor else true_value

    def recall_batch(self, batch_id: str, reason: str) -> dict[str, str]:
        if batch_id not in self.cargo:
            raise ValueError("批次不存在")
        cargo = self.cargo[batch_id]
        cargo.status = CargoStatus.QUARANTINE
        record = {"time": self.simulation_time.isoformat(), "batch_id": batch_id, "reason": reason, "location": cargo.location, "order_id": cargo.order_id or ""}
        self.recalls.append(record)
        self.database.connection.execute(
            "INSERT INTO recalls(time,batch_id,reason,status) VALUES(?,?,?,?)",
            (record["time"], batch_id, reason, "已发起"),
        )
        self.database.connection.commit()
        self.database.audit(self.simulation_time, "批次召回", f"{batch_id}：{reason}；位置={cargo.location}；订单={cargo.order_id or '无'}")
        self.emit_event(Severity.CRITICAL, "召回", f"批次 {batch_id} 已发起召回", batch_id, "隔离在库货物并联系下游")
        return record

    def _check_alerts(self) -> None:
        if self.elapsed_minutes % 10:
            return
        for truck in self.trucks.values():
            for comp in truck.compartments.values():
                if comp.cargo_ids and any(comp.current_temperature > self.cargo[c].max_temperature + 3 for c in comp.cargo_ids):
                    self.emit_event(Severity.WARNING, "温度", f"{truck.truck_id} 车厢温度异常 {comp.current_temperature:.1f}℃", truck.truck_id, "检查制冷机与车门")
        for order in self.orders.values():
            if order.status not in {OrderStatus.DELIVERED, OrderStatus.CANCELLED} and self.simulation_time > order.deadline:
                self.emit_event(Severity.WARNING, "时效", f"订单 {order.order_id} 已超过截止时间", order.order_id)

    def emit_event(self, severity: Severity, category: str, message: str, entity_id: str = "", recommendation: str = "") -> None:
        event = SimEvent(self.simulation_time, severity, category, message, entity_id, recommendation)
        self.events.insert(0, event)
        self.events = self.events[:500]
        self.database.buffer_event(event)
        self.event_created.emit(event)

    def _sample_all(self) -> None:
        for warehouse in self.warehouses.values():
            for zone in warehouse.zones.values():
                sample = TemperatureSample(self.simulation_time, zone.zone_id, "zone", zone.current_temperature)
                self.samples.append(sample); self.database.buffer_sample(sample)
        for truck in self.trucks.values():
            for comp in truck.compartments.values():
                core = sum(self.cargo[c].current_core_temperature for c in comp.cargo_ids) / len(comp.cargo_ids) if comp.cargo_ids else None
                sample = TemperatureSample(self.simulation_time, comp.compartment_id, "truck", comp.current_temperature, core)
                self.samples.append(sample); self.database.buffer_sample(sample)
        self.samples = self.samples[-5000:]

    def kpis(self) -> dict[str, str]:
        delivered = [o for o in self.orders.values() if o.status == OrderStatus.DELIVERED]
        on_time = sum(o.actual_arrival is not None and o.actual_arrival <= o.deadline for o in delivered)
        all_cargo = list(self.cargo.values())
        compliance = sum(c.excursion_minutes == 0 for c in all_cargo) / max(1, len(all_cargo)) * 100
        return {
            "准时率": f"{on_time/max(1,len(delivered))*100:.0f}%",
            "温度合规": f"{compliance:.0f}%",
            "运输中": str(sum(o.status == OrderStatus.IN_TRANSIT for o in self.orders.values())),
            "温度异常": str(sum(c.excursion_minutes > 0 for c in all_cargo)),
            "卫生异常": str(sum(f.hygiene_status != HygieneStatus.CLEAN for f in self.forklifts.values())),
            "累计能耗": f"{self.total_energy_kwh:.1f} kWh",
            "当前成本": f"¥{self.total_energy_kwh*self.config['costs']['energy_per_kwh']:.2f}",
            "平均品质": f"{sum(c.quality for c in all_cargo)/max(1,len(all_cargo)):.1f}",
        }

    def order_report(self, order_id: str) -> dict[str, Any]:
        order = self.orders[order_id]
        cargo = [self.cargo[c] for c in order.cargo_ids]
        truck = self.trucks[order.truck_id] if order.truck_id else None
        compartment = truck.compartments[order.compartment_id] if truck else None
        return {
            "订单号": order.order_id, "状态": order.status.value, "起点": order.origin, "终点": order.destination,
            "货物批次": [c.batch_id for c in cargo], "车辆": order.truck_id or "未分配", "封签": truck.seal_number if truck else "",
            "出发时间": order.actual_departure.isoformat(" ") if order.actual_departure else "", "到达时间": order.actual_arrival.isoformat(" ") if order.actual_arrival else "",
            "最高货物核心温度": max(c.current_core_temperature for c in cargo), "累计超温分钟": sum(c.excursion_minutes for c in cargo),
            "温度暴露指数": sum(c.degree_minutes for c in cargo), "平均最终品质": sum(c.quality for c in cargo)/len(cargo),
            "开门次数": compartment.door_open_count if compartment else 0, "最长开门分钟": compartment.longest_door_open if compartment else 0,
            "能耗kWh": truck.energy_kwh if truck else 0, "能源成本": order.energy_cost, "人工成本": order.labor_cost,
            "货损成本": order.loss_cost, "罚金": order.penalty, "利润": order.profit,
            "说明": "温度/品质结果为教学仿真的简化风险模型，不构成食品安全或标准合规判定。",
        }

    def export_order_report(self, order_id: str, path: Path) -> None:
        path.write_text(json.dumps(self.order_report(order_id), ensure_ascii=False, indent=2), encoding="utf-8")
