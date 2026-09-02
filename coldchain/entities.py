from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .enums import (
    CargoStatus, EquipmentStatus, HygieneCategory, HygieneStatus,
    OrderStatus, PackageIntegrity, Severity,
)


@dataclass(slots=True)
class RefrigerationUnit:
    target_temperature: float
    cooling_power: float = 1.0
    running: bool = False
    fault: bool = False
    compressor_load: float = 0.0
    energy_kwh: float = 0.0
    operating_minutes: int = 0
    auto_defrost: bool = True
    minutes_since_defrost: int = 0
    defrost_remaining: int = 0


@dataclass(slots=True)
class CargoBatch:
    batch_id: str
    sku: str
    name: str
    category: str
    hygiene_category: HygieneCategory
    quantity: float
    unit: str
    weight_kg: float
    volume_m3: float
    pallet_count: int
    production_date: datetime
    expiry_date: datetime
    min_temperature: float
    max_temperature: float
    target_temperature: float
    current_core_temperature: float
    surface_temperature: float
    thermal_inertia: float = 1.0
    temperature_sensitivity: float = 1.0
    quality: float = 100.0
    package_integrity: PackageIntegrity = PackageIntegrity.SEALED
    contamination_risk: float = 0.0
    status: CargoStatus = CargoStatus.AVAILABLE
    location: str = ""
    order_id: str | None = None
    excursion_minutes: float = 0.0
    degree_minutes: float = 0.0

    @property
    def remaining_shelf_life(self) -> int:
        return max(0, (self.expiry_date - datetime.now()).days)


@dataclass(slots=True)
class WarehouseZone:
    zone_id: str
    name: str
    temperature_setpoint: float
    temperature_min: float
    temperature_max: float
    current_temperature: float
    humidity: float
    capacity_weight: float
    capacity_volume: float
    capacity_pallets: int
    refrigeration: RefrigerationUnit
    door_open: bool = False
    power: bool = True
    emergency_power: bool = False
    cargo_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LoadingDock:
    dock_id: str
    name: str
    occupied_by: str | None = None
    queue: list[str] = field(default_factory=list)
    door_open: bool = False


@dataclass(slots=True)
class Warehouse:
    warehouse_id: str
    name: str
    location: str
    zones: dict[str, WarehouseZone] = field(default_factory=dict)
    docks: dict[str, LoadingDock] = field(default_factory=dict)
    power_status: bool = True
    emergency_power: bool = False


@dataclass(slots=True)
class TruckCompartment:
    compartment_id: str
    name: str
    target_temperature: float
    current_temperature: float
    max_weight: float
    max_volume: float
    max_pallets: int
    refrigeration: RefrigerationUnit
    cargo_ids: list[str] = field(default_factory=list)
    door_open: bool = False
    door_open_minutes: int = 0
    door_open_count: int = 0
    longest_door_open: int = 0


@dataclass(slots=True)
class Truck:
    truck_id: str
    plate_number: str
    truck_type: str
    compartments: dict[str, TruckCompartment]
    status: EquipmentStatus = EquipmentStatus.IDLE
    location: str = "武夷山中心仓"
    destination: str = ""
    distance_remaining_km: float = 0.0
    speed_kmh: float = 55.0
    cleanliness: HygieneStatus = HygieneStatus.CLEAN
    seal_number: str = ""
    maintenance_state: str = "正常"
    energy_kwh: float = 0.0
    order_id: str | None = None
    traffic_delay_minutes: int = 0

    def capacity_used(self, cargo: dict[str, CargoBatch]) -> tuple[float, float, int]:
        ids = [item for compartment in self.compartments.values() for item in compartment.cargo_ids]
        return (
            sum(cargo[item].weight_kg for item in ids),
            sum(cargo[item].volume_m3 for item in ids),
            sum(cargo[item].pallet_count for item in ids),
        )


@dataclass(slots=True)
class Forklift:
    forklift_id: str
    name: str
    warehouse_id: str
    current_zone: str
    allowed_zones: list[str]
    status: EquipmentStatus = EquipmentStatus.IDLE
    hygiene_status: HygieneStatus = HygieneStatus.CLEAN
    contamination_type: str = ""
    contamination_level: float = 0.0
    last_cargo_category: HygieneCategory | None = None
    task: str = ""
    remaining_minutes: int = 0
    battery_percent: float = 100.0
    dedicated_category: HygieneCategory | None = None


@dataclass(slots=True)
class Order:
    order_id: str
    origin: str
    destination: str
    cargo_ids: list[str]
    created_at: datetime
    deadline: datetime
    distance_km: float
    revenue: float
    status: OrderStatus = OrderStatus.CREATED
    truck_id: str | None = None
    forklift_id: str | None = None
    compartment_id: str | None = None
    phase_remaining: int = 0
    actual_departure: datetime | None = None
    actual_arrival: datetime | None = None
    energy_cost: float = 0.0
    labor_cost: float = 0.0
    loss_cost: float = 0.0
    penalty: float = 0.0
    override_hygiene: bool = False

    @property
    def profit(self) -> float:
        return self.revenue - self.energy_cost - self.labor_cost - self.loss_cost - self.penalty


@dataclass(slots=True)
class SimEvent:
    time: datetime
    severity: Severity
    category: str
    message: str
    entity_id: str = ""
    recommendation: str = ""


@dataclass(slots=True)
class TemperatureSample:
    time: datetime
    entity_id: str
    entity_type: str
    air_temperature: float
    cargo_temperature: float | None = None


@dataclass(slots=True)
class Sensor:
    sensor_id: str
    entity_id: str
    bias: float = 0.0
    noise: float = 0.08
    fault_mode: str = "正常"  # 正常 / 卡死 / 离线
    stuck_value: float | None = None

    def measure(self, true_value: float, random_source) -> float | None:
        if self.fault_mode == "离线":
            return None
        if self.fault_mode == "卡死":
            if self.stuck_value is None:
                self.stuck_value = true_value + self.bias
            return self.stuck_value
        return true_value + self.bias + random_source.gauss(0, self.noise)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
