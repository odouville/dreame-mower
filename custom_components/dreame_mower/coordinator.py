"""DataUpdateCoordinator for Dreame Mower Integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME

from .const import DOMAIN, CONF_NOTIFY
from .config_flow import (
    CONF_ACCOUNT_TYPE, 
    CONF_COUNTRY, 
    CONF_DID, 
    CONF_MAC, 
    CONF_MODEL, 
    CONF_SERIAL, 
    NOTIFICATION_INFORMATION,
    NOTIFICATION_WARNING,
    NOTIFICATION_ERROR,
    NOTIFICATION_MQTT_DISCOVERY,
)
from .dreame.device import DreameMowerDevice
from .dreame.issue_reporter import DreameMowerIssueReporter
from .dreame.property import (
    DEVICE_CODE_ERROR_PROPERTY_NAME,
    DEVICE_CODE_WARNING_PROPERTY_NAME,
    DEVICE_CODE_INFO_PROPERTY_NAME,
    NOTIFICATION_CODE_FIELD,
    NOTIFICATION_NAME_FIELD,
    NOTIFICATION_DESCRIPTION_FIELD,
)
from .dreame.const import POWER_STATE_PROPERTY

_LOGGER = logging.getLogger(__name__)

class DreameMowerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Dreame Mower implementation."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
    ) -> None:
        """Initialize Dreame Mower coordinator."""
        self.entry = entry

        self.device = DreameMowerDevice(
            entry.data[CONF_DID],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data[CONF_ACCOUNT_TYPE],
            entry.data[CONF_COUNTRY],
            hass.config.config_dir)
        
        # Initialize issue reporter for unhandled MQTT messages
        self.issue_reporter = DreameMowerIssueReporter(hass)
        
        # Initialize coordinator with no automatic polling (device will push updates)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # No polling - use real-time updates from device
            config_entry=entry,  # Required for async_config_entry_first_refresh
        )
        
        # Register callback to receive device property updates
        self.device.register_property_callback(self._handle_device_update)
        


    async def _async_update_data(self) -> dict[str, Any]:
        """Update data. This method is required by DataUpdateCoordinator."""
        return {
            "name": self.device_name,
            "connected": self.device_connected,
            "last_update": self.last_update,
            "mac": self.device_mac,
            "model": self.device_model,
            "serial": self.device_serial,
            "firmware": self.device_firmware,
            "manufacturer": self.device_manufacturer,
            "battery_percent": self.device_battery_percent,
            "status": self.device_status,
            "bluetooth_connected": self.device_bluetooth_connected,
            "temperature": self.device_temperature,
            "charging_status": self.device_charging_status,
            "bms_phase": self.device_bms_phase,
            "current_task_data": self.current_task_data,
            "mowing_progress_percent": self.mowing_progress_percent,
            "current_area_sqm": self.current_area_sqm,
            "total_area_sqm": self.total_area_sqm,
            "mower_coordinates": self.mower_coordinates,
            "current_segment": self.current_segment,
            "mower_heading": self.mower_heading,
            "mowing_path_history": self.mowing_path_history,
        }

    @property
    def device_mac(self) -> str:
        """Return device MAC address for device identification from config entry."""
        return self.entry.data[CONF_MAC]

    @property
    def device_connected(self) -> bool:
        """Return device connection status."""
        return self.device.connected

    @property
    def device_name(self) -> str:
        """Return device name for display purposes from config entry."""
        return self.entry.data[CONF_NAME]

    @property
    def device_model(self) -> str:
        """Return device model identifier from config entry."""
        return self.entry.data[CONF_MODEL]

    @property
    def device_serial(self) -> str:
        """Return device serial number from config entry."""
        return self.entry.data[CONF_SERIAL]

    @property
    def device_firmware(self) -> str:
        """Return device firmware version."""
        return self.device.firmware

    @property
    def device_manufacturer(self) -> str:
        """Return device manufacturer."""
        return "Dreametech™"

    @property
    def last_update(self) -> str:
        """Return last update timestamp."""
        return self.device.last_update.isoformat()

    @property
    def device_battery_percent(self) -> int | None:
        """Return device battery percentage."""
        return self.device.battery_percent

    @property
    def device_status(self) -> str | None:
        """Return device status."""
        return self.device.status
    
    @property 
    def device_status_code(self) -> int:
        """Return raw device status code."""
        return self.device.status_code

    @property
    def device_bluetooth_connected(self) -> bool | None:
        """Return Bluetooth connection status."""
        return self.device.bluetooth_connected

    @property
    def device_temperature(self) -> float | None:
        """Return temperature from last mowing session."""
        return self.device.temperature

    @property
    def device_charging_status(self) -> str | None:
        """Return charging status (mapped text)."""
        return self.device.charging_status

    @property
    def device_bms_phase(self) -> int | None:
        """Return BMS micro-phase (5:106)."""
        return self.device.bms_phase

    @property
    def current_task_data(self) -> dict | None:
        """Return current task data from TaskHandler."""
        return self.device.current_task_data

    @property
    def device_code(self) -> int | None:
        """Return current device code (2:2)."""
        return self.device.device_code

    @property
    def device_code_name(self) -> str | None:
        """Return device code name."""
        return self.device.device_code_name

    @property
    def device_code_description(self) -> str | None:
        """Return device code description."""
        return self.device.device_code_description

    @property
    def device_code_is_error(self) -> bool | None:
        """Return True if device code represents an error."""
        return self.device.device_code_is_error

    @property
    def device_code_is_warning(self) -> bool | None:
        """Return True if device code represents a warning."""
        return self.device.device_code_is_warning

    @property
    def mowing_progress_percent(self) -> float | None:
        """Return current mowing progress percentage."""
        return self.device.mowing_progress_percent

    @property
    def current_area_sqm(self) -> float | None:
        """Return current mowed area in square meters."""
        return self.device.current_area_sqm

    @property
    def total_area_sqm(self) -> float | None:
        """Return total planned area in square meters."""
        return self.device.total_area_sqm

    @property
    def mower_coordinates(self) -> tuple[int, int] | None:
        """Return current mower coordinates as (x, y) tuple."""
        return self.device.mower_coordinates

    @property
    def current_segment(self) -> int | None:
        """Return current mowing segment/lane index."""
        return self.device.current_segment

    @property
    def mower_heading(self) -> int | None:
        """Return current mower heading/state value."""
        return self.device.mower_heading

    @property
    def mowing_path_history(self) -> list[dict[str, Any]]:
        """Return path history for visualization."""
        return self.device.mowing_path_history
    
    def _handle_device_update(self, property_name: str, value: Any) -> None:
        """Handle device property updates and notify Home Assistant."""
        # Handle device code error notifications
        if property_name == DEVICE_CODE_ERROR_PROPERTY_NAME and isinstance(value, dict):
            # Create persistent notification for error device codes
            notify_options = self.entry.options.get(CONF_NOTIFY, [])
            if NOTIFICATION_ERROR in notify_options:
                self.hass.create_task(
                    self.issue_reporter.create_device_error_notification(
                        value[NOTIFICATION_CODE_FIELD],
                        value[NOTIFICATION_NAME_FIELD], 
                        value[NOTIFICATION_DESCRIPTION_FIELD],
                        self.device_model,
                        self.device_firmware
                    )
                )
        
        # Handle device code warning notifications
        elif property_name == DEVICE_CODE_WARNING_PROPERTY_NAME and isinstance(value, dict):
            # Create persistent notification for warning device codes (optional - can be disabled)
            notify_options = self.entry.options.get(CONF_NOTIFY, [])
            if NOTIFICATION_WARNING in notify_options:
                self.hass.create_task(
                    self.issue_reporter.create_device_error_notification(
                        value[NOTIFICATION_CODE_FIELD],
                        value[NOTIFICATION_NAME_FIELD],
                        value[NOTIFICATION_DESCRIPTION_FIELD], 
                        self.device_model,
                        self.device_firmware
                    )
                )
        
        # Handle device code info notifications
        elif property_name == DEVICE_CODE_INFO_PROPERTY_NAME and isinstance(value, dict):
            # Create persistent notification for info device codes (optional - can be disabled)
            notify_options = self.entry.options.get(CONF_NOTIFY, [])
            if NOTIFICATION_INFORMATION in notify_options:
                self.hass.create_task(
                    self.issue_reporter.create_device_info_notification(
                        value[NOTIFICATION_CODE_FIELD],
                        value[NOTIFICATION_NAME_FIELD],
                        value[NOTIFICATION_DESCRIPTION_FIELD], 
                        self.device_model,
                        self.device_firmware
                    )
                )

        # Handle POWER_STATE_PROPERTY notifications
        elif property_name == POWER_STATE_PROPERTY.name:
            if value == 1:  # Only notify for powered off state
                notify_options = self.entry.options.get(CONF_NOTIFY, [])
                if NOTIFICATION_INFORMATION in notify_options:
                    self.hass.create_task(
                        self.issue_reporter.create_device_info_notification(
                            value,  # Use power state value as notification code
                            "Mower Powered Off",
                            "The mower has been powered off", 
                            self.device_model,
                            self.device_firmware
                        )
                    )
        
        # Handle special case for unhandled MQTT messages (both properties and other message types)
        elif property_name == "unhandled_mqtt" and isinstance(value, dict):
            # Check if user has enabled MQTT discovery notifications
            notify_options = self.entry.options.get(CONF_NOTIFY, [])
            if NOTIFICATION_MQTT_DISCOVERY in notify_options:
                # Create persistent notification using issue reporter
                self.hass.create_task(
                    self.issue_reporter.create_unhandled_mqtt_notification(
                        value, 
                        self.device_model, 
                        self.device_firmware
                    )
                )
            else:
                _LOGGER.debug("MQTT discovery notification skipped - user preference disabled")
        
        
        # Schedule a coordinator update to notify all entities
        # Use async_set_updated_data to trigger entity updates
        self.hass.create_task(self._async_handle_device_update())
    
    async def _async_handle_device_update(self) -> None:
        """Async handler for device updates."""
        try:
            # Get fresh data and update all entities
            data = await self._async_update_data()
            self.async_set_updated_data(data)
        except Exception as ex:
            _LOGGER.exception("Error handling device update: %s", ex)
    
    def register_property_callback(self, property_key: str, callback) -> None:
        """Register callback for property changes.
        
        Args:
            property_key: Property identifier for callback registration
            callback: Callback function to register
        """
        self.device.register_property_callback(callback)

    async def async_connect_device(self) -> bool:
        """Connect to the device."""
        return await self.device.connect()

    async def async_disconnect_device(self) -> None:
        """Disconnect from the device."""
        await self.device.disconnect()