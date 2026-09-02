from __future__ import annotations

import math

from .entities import CargoBatch, RefrigerationUnit


def approach_temperature(current: float, surrounding: float, coefficient: float, minutes: float) -> float:
    """Stable first-order heat exchange; coefficient is per simulated minute."""
    fraction = 1.0 - math.exp(-max(0.0, coefficient) * max(0.0, minutes))
    return current + (surrounding - current) * fraction


def update_refrigeration(
    unit: RefrigerationUnit,
    air_temperature: float,
    minutes: int,
    high: float,
    low: float,
    energy_rate: float,
    defrost_interval: int,
    defrost_duration: int,
    cooling_rate: float = 0.22,
) -> tuple[float, float]:
    if unit.auto_defrost and unit.defrost_remaining <= 0 and unit.minutes_since_defrost >= defrost_interval:
        unit.defrost_remaining = defrost_duration
        unit.minutes_since_defrost = 0
    if unit.defrost_remaining > 0:
        unit.defrost_remaining = max(0, unit.defrost_remaining - minutes)
        unit.running = False
        unit.compressor_load = 0.0
        return air_temperature + 0.025 * minutes, 0.012 * minutes
    unit.minutes_since_defrost += minutes
    if unit.fault:
        unit.running = False
    elif air_temperature > unit.target_temperature + high:
        unit.running = True
    elif air_temperature < unit.target_temperature + low:
        unit.running = False
    if unit.running:
        delta = max(0.0, air_temperature - unit.target_temperature)
        unit.compressor_load = min(1.0, 0.35 + delta / 12.0)
        cooling = unit.cooling_power * unit.compressor_load * cooling_rate * minutes
        air_temperature = max(unit.target_temperature - 2.0, air_temperature - cooling)
        used = energy_rate * unit.compressor_load * minutes
        unit.energy_kwh += used
        unit.operating_minutes += minutes
        return air_temperature, used
    unit.compressor_load = 0.0
    return air_temperature, 0.0


def update_cargo_temperature(cargo: CargoBatch, air_temperature: float, minutes: int, config: dict) -> None:
    surface_rate = config["thermal"]["cargo_surface_factor"] / max(0.2, cargo.thermal_inertia)
    core_rate = config["thermal"]["cargo_core_factor"] / max(0.2, cargo.thermal_inertia)
    cargo.surface_temperature = approach_temperature(cargo.surface_temperature, air_temperature, surface_rate, minutes)
    cargo.current_core_temperature = approach_temperature(
        cargo.current_core_temperature, cargo.surface_temperature, core_rate, minutes
    )
    excess = max(0.0, cargo.current_core_temperature - cargo.max_temperature)
    under = max(0.0, cargo.min_temperature - cargo.current_core_temperature)
    deviation = excess + under * 0.35
    if deviation > 0:
        cargo.excursion_minutes += minutes
        cargo.degree_minutes += deviation * minutes
        quality = config["quality"]
        multiplier = quality["severe_multiplier"] if deviation > 5 else 1.0
        cargo.quality = max(
            0.0,
            cargo.quality - deviation * minutes * quality["mild_loss_per_degree_minute"]
            * cargo.temperature_sensitivity * multiplier,
        )
