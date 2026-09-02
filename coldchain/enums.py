from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    CREATED = "已创建"
    ALLOCATED = "已分配"
    PRECOOLING = "车辆预冷"
    PICKING = "拣货中"
    STAGING = "待装车"
    LOADING = "装车中"
    IN_TRANSIT = "运输中"
    ARRIVED = "已到达"
    UNLOADING = "卸货中"
    DELIVERED = "已签收"
    QUARANTINE = "隔离待检"
    CANCELLED = "已取消"


class CargoStatus(StrEnum):
    RECEIVING = "待验收"
    AVAILABLE = "合格库存"
    ALLOCATED = "已分配"
    PICKING = "拣货中"
    STAGING = "待装车"
    IN_TRANSIT = "运输中"
    DELIVERED = "已签收"
    QUARANTINE = "隔离待检"
    DESTROYED = "已销毁"


class HygieneCategory(StrEnum):
    RAW_MEAT = "生肉"
    RAW_POULTRY = "生禽"
    RAW_SEAFOOD = "生鲜水产"
    DAIRY = "乳制品"
    READY_TO_EAT = "即食食品"
    FRUIT = "水果"
    VEGETABLE = "蔬菜"
    FROZEN_PACKAGED = "冷冻包装食品"
    GENERAL_PACKAGED = "普通包装食品"


class HygieneStatus(StrEnum):
    CLEAN = "清洁"
    LOW_RISK = "低风险"
    CONTAMINATED = "已污染"
    REQUIRES_CLEANING = "待清洁"
    REQUIRES_DISINFECTION = "待消毒"
    REQUIRES_BOTH = "待清洁消毒"
    SANITIZING = "处理中"


class PackageIntegrity(StrEnum):
    SEALED = "密封完好"
    DAMAGED = "包装破损"
    LEAKING = "泄漏"
    EXPOSED = "裸露"


class EquipmentStatus(StrEnum):
    IDLE = "空闲"
    BUSY = "作业中"
    PRECOOLING = "预冷中"
    IN_TRANSIT = "运输中"
    FAULT = "故障"
    MAINTENANCE = "维护中"


class Severity(StrEnum):
    INFO = "信息"
    WARNING = "警告"
    CRITICAL = "严重"


class Compatibility(StrEnum):
    ALLOW = "允许"
    WARNING = "警告"
    REQUIRE_CLEANING = "需要清洁"
    REQUIRE_CLEAN_AND_DISINFECT = "需要清洁消毒"
    PROHIBIT_UNLESS_OVERRIDE = "仅可强制执行"

