from __future__ import annotations

from .entities import CargoBatch, Forklift
from .enums import Compatibility, HygieneCategory, HygieneStatus, PackageIntegrity


HIGH_RISK = {HygieneCategory.RAW_MEAT, HygieneCategory.RAW_POULTRY, HygieneCategory.RAW_SEAFOOD}
SENSITIVE = {HygieneCategory.DAIRY, HygieneCategory.READY_TO_EAT}


def compatibility(forklift: Forklift, cargo: CargoBatch) -> Compatibility:
    if forklift.hygiene_status in {HygieneStatus.REQUIRES_BOTH, HygieneStatus.CONTAMINATED}:
        if cargo.hygiene_category in SENSITIVE:
            return Compatibility.PROHIBIT_UNLESS_OVERRIDE
        return Compatibility.REQUIRE_CLEAN_AND_DISINFECT
    if forklift.hygiene_status == HygieneStatus.REQUIRES_CLEANING:
        return Compatibility.REQUIRE_CLEANING
    if forklift.hygiene_status == HygieneStatus.REQUIRES_DISINFECTION:
        return Compatibility.REQUIRE_CLEAN_AND_DISINFECT
    if forklift.dedicated_category and forklift.dedicated_category != cargo.hygiene_category:
        return Compatibility.WARNING
    return Compatibility.ALLOW


def expose_forklift(forklift: Forklift, cargo: CargoBatch) -> None:
    forklift.last_cargo_category = cargo.hygiene_category
    if cargo.hygiene_category in HIGH_RISK and cargo.package_integrity in {
        PackageIntegrity.DAMAGED, PackageIntegrity.LEAKING, PackageIntegrity.EXPOSED
    }:
        forklift.hygiene_status = HygieneStatus.REQUIRES_BOTH
        forklift.contamination_type = f"{cargo.hygiene_category.value}残留"
        forklift.contamination_level = min(100.0, forklift.contamination_level + 70.0)


def apply_cross_contamination(forklift: Forklift, cargo: CargoBatch) -> None:
    cargo.contamination_risk = min(100.0, cargo.contamination_risk + forklift.contamination_level * 0.65)
    cargo.quality = max(0.0, cargo.quality - forklift.contamination_level * 0.08)

