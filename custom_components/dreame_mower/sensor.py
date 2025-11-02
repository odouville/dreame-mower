"""Minimal sensor platform for Dreame Mower Implementation."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfArea

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Mower sensors from config entry."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    
    # Create minimal essential sensors for a lawn mower
    sensors = [
        DreameMowerBatterySensor(coordinator),
        DreameMowerStatusSensor(coordinator),
        DreameMowerChargingStatusSensor(coordinator),
        DreameMowerBluetoothSensor(coordinator),
        DreameMowerTemperatureSensor(coordinator),
        DreameMowerBMSPhaseSensor(coordinator),
        DreameMowerDeviceCodeSensor(coordinator),
        DreameMowerTaskSensor(coordinator),
        DreameMowerProgressSensor(coordinator),
    ]
    
    async_add_entities(sensors)


class DreameMowerBatterySensor(DreameMowerEntity, SensorEntity):
    """Battery level sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, "battery")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery level."""
        return self.coordinator.device_battery_percent


class DreameMowerStatusSensor(DreameMowerEntity, SensorEntity):
    """Status sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the status sensor."""
        super().__init__(coordinator, "status")
        self._attr_icon = "mdi:robot-mower"
        self._attr_translation_key = "status"

    @property
    def native_value(self) -> str | None:
        """Return the mower status."""
        if not self.available:
            return "offline"
        return self.coordinator.device_status


class DreameMowerChargingStatusSensor(DreameMowerEntity, SensorEntity):
    """Charging status sensor for Dreame Mower (3:2)."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the charging status sensor."""
        super().__init__(coordinator, "charging_status")
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "charging_status"

    @property
    def native_value(self) -> str | None:
        """Return the charging status mapped text."""
        return self.coordinator.device_charging_status


class DreameMowerBluetoothSensor(DreameMowerEntity, SensorEntity):
    """Bluetooth connection sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the Bluetooth sensor."""
        super().__init__(coordinator, "bluetooth_connection")
        self._attr_icon = "mdi:bluetooth"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "bluetooth_connection"

    @property
    def native_value(self) -> bool | None:
        """Return the Bluetooth connection status."""
        return self.coordinator.device_bluetooth_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "bluetooth_connected": self.coordinator.device_bluetooth_connected,
        }


class DreameMowerTemperatureSensor(DreameMowerEntity, SensorEntity):
    """Temperature sensor for Dreame Mower (live device temperature)."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, "temperature")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:thermometer"
        self._attr_translation_key = "temperature"

    @property
    def native_value(self) -> float | None:
        """Return the current device temperature."""
        return self.coordinator.device_temperature


class DreameMowerBMSPhaseSensor(DreameMowerEntity, SensorEntity):
    """BMS micro-phase (5:106) diagnostic sensor."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        super().__init__(coordinator, "bms_phase")
        self._attr_icon = "mdi:current-dc"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "bms_phase"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.device_bms_phase


class DreameMowerDeviceCodeSensor(DreameMowerEntity, SensorEntity):
    """Device code sensor (2:2) - shows current device status/error codes."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the device code sensor."""
        super().__init__(coordinator, "device_code")
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "device_code"

    @property
    def native_value(self) -> int | None:
        """Return the current device code."""
        return self.coordinator.device_code

    @property
    def icon(self) -> str:
        """Return icon based on device code type."""
        if self.coordinator.device_code_is_error:
            return "mdi:alert-circle"
        elif self.coordinator.device_code_is_warning:
            return "mdi:alert"
        else:
            return "mdi:information-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes: dict[str, Any] = {}
        
        # Add device code details
        if self.coordinator.device_code is not None:
            attributes["code"] = self.coordinator.device_code
            attributes["name"] = self.coordinator.device_code_name
            attributes["description"] = self.coordinator.device_code_description
            
            # Determine type based on priority: error > warning > info
            if self.coordinator.device_code_is_error:
                attributes["type"] = "error"
            elif self.coordinator.device_code_is_warning:
                attributes["type"] = "warning"
            else:
                attributes["type"] = "info"
        
        return attributes


class DreameMowerTaskSensor(DreameMowerEntity, SensorEntity):
    """Current task sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the task sensor."""
        super().__init__(coordinator, "current_task")
        self._attr_icon = "mdi:clipboard-play"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "current_task"

    @property
    def native_value(self) -> str | None:
        """Return the current task status."""
        task_data = self.coordinator.current_task_data
        if not task_data:
            return None
        
        execution_active = task_data.get("execution_active", False)
        task_active = task_data.get("task_active", False)
        
        if task_active and execution_active:
            return "Active"
        elif task_active and not execution_active:
            return "Paused"
        else:
            return "Inactive"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with detailed task information."""
        attributes: dict[str, Any] = {}
        
        task_data = self.coordinator.current_task_data
        if task_data:
            attributes.update({
                "task_type": task_data.get("type"),
                "execution_active": task_data.get("execution_active"),
                "task_active": task_data.get("task_active"),
                "coverage_target": task_data.get("coverage_target"),
                "area_id": task_data.get("area_id"),
                "region_id": task_data.get("region_id"),
                "elapsed_time": task_data.get("elapsed_time"),
            })
        
        return attributes


class DreameMowerProgressSensor(DreameMowerEntity, SensorEntity):
    """Mowing progress sensor for Dreame Mower."""

    def __init__(self, coordinator: DreameMowerCoordinator) -> None:
        """Initialize the progress sensor."""
        super().__init__(coordinator, "mowing_progress")
        self._attr_device_class = SensorDeviceClass.POWER_FACTOR
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:percent"
        self._attr_translation_key = "mowing_progress"

    @property
    def native_value(self) -> float | None:
        """Return the mowing progress percentage."""
        progress = self.coordinator.mowing_progress_percent
        if progress is not None:
            return round(progress, 1)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        progress = self.coordinator.mowing_progress_percent
        attributes: dict[str, Any] = {
            "current_area_sqm": self.coordinator.current_area_sqm,
            "total_area_sqm": self.coordinator.total_area_sqm,
            "progress_percent": round(progress, 1) if progress is not None else None,
        }
        
        # Add mower coordinates data
        coordinates = self.coordinator.mower_coordinates
        if coordinates:
            attributes["coordinates"] = f"{coordinates[0]}, {coordinates[1]}"
            attributes["x"] = coordinates[0]
            attributes["y"] = coordinates[1]
        else:
            attributes["coordinates"] = None
            attributes["x"] = None
            attributes["y"] = None
            
        attributes["segment"] = self.coordinator.current_segment
        attributes["heading"] = self.coordinator.mower_heading
        
        # Add path history summary
        path_history = self.coordinator.mowing_path_history
        attributes["path_points"] = len(path_history)
        
        return attributes
