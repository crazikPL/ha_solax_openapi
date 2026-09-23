"""Sensor platform for the SolaX OpenAPI integration.

Sensor keys, units and device_class assignments mirror those used by the
Predbat project's SolaX Cloud component (springfall2008/batpred), since
that is the only known reference implementation for this API - this keeps
values consistent with what people may already be used to from Predbat.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_NAME_PREFIX,
    DEFAULT_NAME_PREFIX,
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    DOMAIN,
    SOLAX_BATTERY_STATUS,
    SOLAX_DEVICE_MODEL_BATTERY,
    SOLAX_DEVICE_MODEL_INVERTER,
    SOLAX_INVERTER_STATUS,
)
from .coordinator import SolaxOpenApiCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SolaxSensorDescription(SensorEntityDescription):
    """Adds a value_fn to pull the right field out of the raw dict."""

    value_fn: Callable[[dict], Any] = lambda data: None


# ---------------------------------------------------------------------------
# Plant-level sensors (one set per plant, values from plant_realtime + derived)
# ---------------------------------------------------------------------------

PLANT_SENSORS: tuple[SolaxSensorDescription, ...] = (
    SolaxSensorDescription(
        key="total_yield",
        translation_key="total_yield",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda rt: rt.get("totalYield"),
    ),
    SolaxSensorDescription(
        key="total_charged",
        translation_key="total_charged",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda rt: rt.get("totalCharged"),
    ),
    SolaxSensorDescription(
        key="total_discharged",
        translation_key="total_discharged",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda rt: rt.get("totalDischarged"),
    ),
    SolaxSensorDescription(
        key="total_imported",
        translation_key="total_imported",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda rt: rt.get("totalImported"),
    ),
    SolaxSensorDescription(
        key="total_exported",
        translation_key="total_exported",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda rt: rt.get("totalExported"),
    ),
    SolaxSensorDescription(
        key="total_load",
        translation_key="total_load",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        # Same derivation Predbat uses: imported + discharged - exported - charged + yield
        value_fn=lambda rt: (
            (rt.get("totalImported") or 0)
            + (rt.get("totalDischarged") or 0)
            - (rt.get("totalExported") or 0)
            - (rt.get("totalCharged") or 0)
            + (rt.get("totalYield") or 0)
        ),
    ),
)

# ---------------------------------------------------------------------------
# Inverter device sensors (value_fn receives the device realtime dict)
# ---------------------------------------------------------------------------


def _pv_power(rt: dict) -> float:
    pv_map = rt.get("pvMap") or {}
    mppt_map = rt.get("mpptMap") or {}
    total = 0.0
    source = pv_map or mppt_map
    for key, val in source.items():
        if "Power" in key and val is not None:
            total += val
    return total


def _ac_power(rt: dict) -> float:
    return sum((rt.get(f"acPower{i}") or 0) for i in (1, 2, 3))


INVERTER_SENSORS: tuple[SolaxSensorDescription, ...] = (
    SolaxSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("gridPower"),
    ),
    SolaxSensorDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_pv_power,
    ),
    SolaxSensorDescription(
        key="ac_power",
        translation_key="ac_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_ac_power,
    ),
    SolaxSensorDescription(
        key="inverter_temperature",
        translation_key="inverter_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("inverterTemperature"),
    ),
    SolaxSensorDescription(
        key="total_yield_device",
        translation_key="total_yield",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda rt: rt.get("totalYield"),
    ),
    SolaxSensorDescription(
        key="device_status",
        translation_key="device_status",
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda rt: SOLAX_INVERTER_STATUS.get(rt.get("deviceStatus"), "Unknown"),
    ),
)

BATTERY_SENSORS: tuple[SolaxSensorDescription, ...] = (
    SolaxSensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("batterySOC"),
    ),
    SolaxSensorDescription(
        key="battery_soh",
        translation_key="battery_soh",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("batterySOH"),
    ),
    SolaxSensorDescription(
        key="charge_discharge_power",
        translation_key="charge_discharge_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("chargeDischargePower"),
    ),
    SolaxSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("batteryVoltage"),
    ),
    SolaxSensorDescription(
        key="battery_current",
        translation_key="battery_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("batteryCurrent"),
    ),
    SolaxSensorDescription(
        key="battery_temperature",
        translation_key="battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("batteryTemperature"),
    ),
    SolaxSensorDescription(
        key="battery_remaining_energy",
        translation_key="battery_remaining_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda rt: rt.get("batteryRemainings"),
    ),
    SolaxSensorDescription(
        key="device_status",
        translation_key="device_status",
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda rt: SOLAX_BATTERY_STATUS.get(rt.get("deviceStatus"), "Unknown"),
    ),
)

_MPPT_KEY_RE = re.compile(r"^MPPT(\d+)(Voltage|Current|Power)$")
_MPPT_FIELD_UNITS: dict[str, tuple[str, SensorDeviceClass]] = {
    "Voltage": (UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    "Current": (UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    "Power": (UnitOfPower.WATT, SensorDeviceClass.POWER),
}


def _mppt_source(rt: dict) -> dict:
    """MPPT data lives under mpptMap on most models, pvMap on newer ones."""
    return rt.get("mpptMap") or rt.get("pvMap") or {}


def build_mppt_sensor_descriptions(rt: dict) -> list[SolaxSensorDescription]:
    """Discover which MPPT trackers exist for this inverter and build 3
    sensors (voltage/current/power) per tracker found. The number of MPPTs
    varies by inverter model, so this is detected from the actual API
    response rather than hardcoded.
    """
    indices: set[int] = set()
    for key in _mppt_source(rt):
        match = _MPPT_KEY_RE.match(key)
        if match:
            indices.add(int(match.group(1)))

    descriptions: list[SolaxSensorDescription] = []
    for idx in sorted(indices):
        for field, (unit, device_class) in _MPPT_FIELD_UNITS.items():
            source_key = f"MPPT{idx}{field}"
            descriptions.append(
                SolaxSensorDescription(
                    key=f"mppt{idx}_{field.lower()}",
                    name=f"MPPT {idx} {field}",
                    native_unit_of_measurement=unit,
                    device_class=device_class,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda rt, k=source_key: _mppt_source(rt).get(k),
                )
            )
    return descriptions


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up SolaX OpenAPI sensors from a config entry."""
    coordinator: SolaxOpenApiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    for plant_id, plant in coordinator.data["plants"].items():
        plant_name = plant.get("plantName") or plant_id
        for description in PLANT_SENSORS:
            entities.append(SolaxPlantSensor(coordinator, entry, plant_id, plant_name, description))

    for device_sn, device in coordinator.data["devices"].items():
        device_type = device.get("deviceType")
        if device_type == DEVICE_TYPE_INVERTER:
            model = SOLAX_DEVICE_MODEL_INVERTER.get(device.get("deviceModel"), "SolaX Inverter")
            for description in INVERTER_SENSORS:
                entities.append(SolaxDeviceSensor(coordinator, entry, device_sn, device_type, model, description))
            rt = coordinator.data["device_realtime"].get(device_sn, {})
            for description in build_mppt_sensor_descriptions(rt):
                entities.append(SolaxDeviceSensor(coordinator, entry, device_sn, device_type, model, description))
        elif device_type == DEVICE_TYPE_BATTERY:
            model = SOLAX_DEVICE_MODEL_BATTERY.get(device.get("deviceModel"), "SolaX Battery")
            for description in BATTERY_SENSORS:
                entities.append(SolaxDeviceSensor(coordinator, entry, device_sn, device_type, model, description))

    async_add_entities(entities)


class SolaxPlantSensor(CoordinatorEntity[SolaxOpenApiCoordinator], SensorEntity):
    """Sensor for a plant-level (aggregate) value."""

    entity_description: SolaxSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, plant_id: str, plant_name: str, description: SolaxSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._plant_id = plant_id
        self._attr_unique_id = f"{entry.entry_id}_{plant_id}_{description.key}"

        prefix = entry.data.get(CONF_NAME_PREFIX) or DEFAULT_NAME_PREFIX
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=f"{prefix} Elektrownia",
            manufacturer="SolaX Power",
            model="Plant",
        )

    @property
    def native_value(self):
        rt = self.coordinator.data["plant_realtime"].get(self._plant_id, {})
        return self.entity_description.value_fn(rt)

    @property
    def available(self) -> bool:
        return super().available and self._plant_id in self.coordinator.data.get("plant_realtime", {})


class SolaxDeviceSensor(CoordinatorEntity[SolaxOpenApiCoordinator], SensorEntity):
    """Sensor for an individual inverter or battery device."""

    entity_description: SolaxSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, device_sn: str, device_type: int, model: str, description: SolaxSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_sn = device_sn
        self._attr_unique_id = f"{entry.entry_id}_{device_sn}_{description.key}"

        prefix = entry.data.get(CONF_NAME_PREFIX) or DEFAULT_NAME_PREFIX
        simple_name = f"{prefix} Falownik" if device_type == DEVICE_TYPE_INVERTER else f"{prefix} Bateria"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=simple_name,
            manufacturer="SolaX Power",
            model=model,
            serial_number=device_sn,
        )

    @property
    def native_value(self):
        rt = self.coordinator.data["device_realtime"].get(self._device_sn)
        if rt is None:
            return None
        return self.entity_description.value_fn(rt)

    @property
    def available(self) -> bool:
        return super().available and self._device_sn in self.coordinator.data.get("device_realtime", {})
