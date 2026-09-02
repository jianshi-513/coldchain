from __future__ import annotations

from datetime import datetime, timedelta

from .entities import (
    CargoBatch, Forklift, LoadingDock, RefrigerationUnit, Truck, TruckCompartment,
    Warehouse, WarehouseZone,
)
from .enums import HygieneCategory, HygieneStatus, PackageIntegrity


def create_demo(now: datetime):
    cold = WarehouseZone("WYS-C", "冷藏库 B", 4, 2, 6, 4.2, 78, 100_000, 800, 500, RefrigerationUnit(4, 0.75))
    frozen = WarehouseZone("WYS-F", "冷冻库 A", -22, -25, -18, -21.3, 70, 140_000, 900, 600, RefrigerationUnit(-22, 1.0))
    staging = WarehouseZone("WYS-S", "发货暂存区", 12, 2, 18, 11.0, 68, 30_000, 250, 120, RefrigerationUnit(10, 0.35))
    quarantine = WarehouseZone("WYS-Q", "隔离区", 6, 2, 10, 6.0, 70, 20_000, 150, 80, RefrigerationUnit(6, 0.4))
    wys = Warehouse(
        "WYS", "武夷山中心仓", "武夷山",
        {z.zone_id: z for z in (cold, frozen, staging, quarantine)},
        {f"D{i}": LoadingDock(f"D{i}", f"月台 {i}") for i in range(1, 4)},
    )
    fz_zone = WarehouseZone("FZ-C", "福州冷藏库", 4, 2, 6, 4.3, 76, 90_000, 700, 420, RefrigerationUnit(4, .7))
    warehouses = {
        "WYS": wys,
        "FZ": Warehouse("FZ", "福州冷链仓", "福州", {fz_zone.zone_id: fz_zone}, {"FZ-D1": LoadingDock("FZ-D1", "月台 1")}),
        "XM": Warehouse("XM", "厦门冷链仓", "厦门"),
        "NC": Warehouse("NC", "南昌冷链仓", "南昌"),
    }
    def compartment(cid: str, name: str, target: float, current: float, weight: float, volume: float, pallets: int, power: float):
        return TruckCompartment(cid, name, target, current, weight, volume, pallets, RefrigerationUnit(target, power))
    trucks = {
        "A01": Truck("A01", "闽H·CC101", "5t冷冻车", {"A01-C": compartment("A01-C", "冷冻舱", -20, 29, 5000, 28, 12, 1.35)}),
        "A02": Truck("A02", "闽H·CC202", "3t冷藏车", {"A02-C": compartment("A02-C", "冷藏舱", 4, 31, 3000, 18, 8, .8)}),
        "A03": Truck("A03", "闽H·CC303", "8t多温区车", {
            "A03-F": compartment("A03-F", "前舱·冷冻", -20, 24, 4500, 24, 10, 1.25),
            "A03-C": compartment("A03-C", "后舱·冷藏", 4, 25, 3500, 20, 8, .65),
        }),
        "A04": Truck("A04", "闽H·CC404", "5t普通厢式车", {"A04-C": compartment("A04-C", "普通货舱", 20, 30, 5000, 30, 12, 0.0)}),
    }
    forklifts = {
        "F01": Forklift("F01", "冷冻区叉车", "WYS", "WYS-F", ["WYS-F", "WYS-S"], hygiene_status=HygieneStatus.REQUIRES_BOTH, contamination_type="泄漏猪肉汁", contamination_level=85, last_cargo_category=HygieneCategory.RAW_MEAT),
        "F02": Forklift("F02", "冷藏区叉车", "WYS", "WYS-C", ["WYS-C", "WYS-S"]),
        "F03": Forklift("F03", "乳制品专用叉车", "WYS", "WYS-C", ["WYS-C", "WYS-S"], dedicated_category=HygieneCategory.DAIRY),
        "F04": Forklift("F04", "通用叉车", "WYS", "WYS-S", ["WYS-C", "WYS-F", "WYS-S"]),
    }
    def batch(batch_id, sku, name, cat, hygiene, qty, weight, volume, pallets, days, tmin, tmax, target, current, inertia, sensitivity, integrity=PackageIntegrity.SEALED, zone="WYS-C"):
        return CargoBatch(batch_id, sku, name, cat, hygiene, qty, "箱", weight, volume, pallets, now-timedelta(days=3), now+timedelta(days=days), tmin, tmax, target, current, current+.2, inertia, sensitivity, package_integrity=integrity, location=zone)
    cargo = {
        "YOGURT-0901-A": batch("YOGURT-0901-A", "DAI-YG-01", "原味酸奶", "冷藏乳品", HygieneCategory.DAIRY, 400, 800, 3.2, 4, 14, 2, 6, 4, 4.2, .7, 1.35),
        "YOGURT-0828-B": batch("YOGURT-0828-B", "DAI-YG-01", "原味酸奶", "冷藏乳品", HygieneCategory.DAIRY, 160, 320, 1.3, 2, 7, 2, 6, 4, 4.0, .7, 1.35),
        "ICE-0901-A": batch("ICE-0901-A", "FRZ-ICE-01", "香草冰淇淋", "冷冻甜品", HygieneCategory.FROZEN_PACKAGED, 240, 600, 2.6, 3, 180, -25, -18, -20, -21, 1.1, 1.8, zone="WYS-F"),
        "PORK-0830-L": batch("PORK-0830-L", "RAW-PK-01", "冷冻猪肉", "冷冻肉类", HygieneCategory.RAW_MEAT, 120, 1200, 3.8, 4, 150, -25, -18, -21, -20, 2.0, 1.0, PackageIntegrity.LEAKING, "WYS-F"),
        "FRUIT-0901-A": batch("FRUIT-0901-A", "FRU-01", "鲜果组合", "水果", HygieneCategory.FRUIT, 200, 1000, 5, 5, 12, 2, 8, 5, 5.5, .8, 1.0),
        "MILK-0901-A": batch("MILK-0901-A", "DAI-MK-01", "巴氏鲜奶", "冷藏乳品", HygieneCategory.DAIRY, 300, 720, 2.9, 4, 9, 2, 6, 4, 4.1, .65, 1.5),
        "VEG-0901-A": batch("VEG-0901-A", "VEG-LF-01", "冷藏叶菜", "蔬菜", HygieneCategory.VEGETABLE, 260, 520, 4.6, 5, 6, 0, 5, 2, 3.0, .55, 1.5),
        "DUMPLING-0901-A": batch("DUMPLING-0901-A", "FRZ-DP-01", "速冻水饺", "冷冻面点", HygieneCategory.FROZEN_PACKAGED, 350, 900, 3.4, 4, 150, -25, -18, -20, -20.5, 1.0, 1.3, zone="WYS-F"),
    }
    for item in cargo.values():
        if item.location in wys.zones:
            wys.zones[item.location].cargo_ids.append(item.batch_id)
    return warehouses, trucks, forklifts, cargo
