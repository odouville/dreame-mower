"""Device code handling for Dreame Mower Implementation.

This module provides device code definitions, registry management, and parsing logic
for property siid:2, piid:2 (device codes). It supports both base device codes and
model-specific extensions.
"""

from __future__ import annotations

import logging
from typing import Dict, Any
from enum import IntEnum
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# Notification property name constants
DEVICE_CODE_PROPERTY_NAME = "device_code"
DEVICE_CODE_ERROR_PROPERTY_NAME = "device_code_error"
DEVICE_CODE_WARNING_PROPERTY_NAME = "device_code_warning"
DEVICE_CODE_INFO_PROPERTY_NAME = "device_code_info"
DEVICE_CODE_NAME_PROPERTY_NAME = "device_code_name"
DEVICE_CODE_DESCRIPTION_PROPERTY_NAME = "device_code_description"
DEVICE_CODE_IS_ERROR_PROPERTY_NAME = "device_code_is_error"
DEVICE_CODE_IS_WARNING_PROPERTY_NAME = "device_code_is_warning"

# Notification data field constants
NOTIFICATION_CODE_FIELD = "code"
NOTIFICATION_NAME_FIELD = "name"
NOTIFICATION_DESCRIPTION_FIELD = "description"
NOTIFICATION_TIMESTAMP_FIELD = "timestamp"


class DeviceCodeType(IntEnum):
    """Device code types for categorization."""
    INFO = 0      # Informational status codes
    WARNING = 1   # Warning codes that require attention but not critical
    ERROR = 2     # Error/fault codes that are critical


class DeviceCodeDefinition:
    """Device code definition with value, name, description, and type."""
    
    def __init__(self, code: int, name: str, description: str, code_type: DeviceCodeType) -> None:
        """Initialize device code definition."""
        self.code = code
        self.name = name
        self.description = description
        self.code_type = code_type
    
    def is_error(self) -> bool:
        """Check if this device code represents an error."""
        return self.code_type == DeviceCodeType.ERROR
    
    def is_warning(self) -> bool:
        """Check if this device code represents a warning."""
        return self.code_type == DeviceCodeType.WARNING
    
    def is_info(self) -> bool:
        """Check if this device code represents informational status."""
        return self.code_type == DeviceCodeType.INFO


class DeviceCodeRegistry:
    """Registry for device codes with support for model-specific extensions."""
    
    def __init__(self, base_codes: Dict[int, DeviceCodeDefinition]) -> None:
        """Initialize registry with base device codes."""
        self._codes = base_codes.copy()
    
    def extend(self, additional_codes: Dict[int, DeviceCodeDefinition]) -> 'DeviceCodeRegistry':
        """Create a new registry extending current codes with additional ones.
        
        Args:
            additional_codes: Additional codes to merge (will override existing)
            
        Returns:
            New DeviceCodeRegistry instance with merged codes
        """
        merged_codes = self._codes.copy()
        merged_codes.update(additional_codes)
        return DeviceCodeRegistry(merged_codes)
    
    def get_code(self, code: int) -> DeviceCodeDefinition | None:
        """Get device code definition by code value."""
        return self._codes.get(code)
    
    def get_name(self, code: int) -> str:
        """Get device code name by code value, with fallback."""
        definition = self._codes.get(code)
        return definition.name if definition else f"Unknown Code {code}"
    
    def get_description(self, code: int) -> str:
        """Get device code description by code value, with fallback."""
        definition = self._codes.get(code)
        return definition.description if definition else f"Unknown device code: {code}"
    
    def is_error(self, code: int) -> bool:
        """Check if device code represents an error."""
        definition = self._codes.get(code)
        return definition.is_error() if definition else False
    
    def is_warning(self, code: int) -> bool:
        """Check if device code represents a warning."""
        definition = self._codes.get(code)
        return definition.is_warning() if definition else False
    
    def is_info(self, code: int) -> bool:
        """Check if device code represents informational status."""
        definition = self._codes.get(code)
        return definition.is_info() if definition else False
    
    def get_mapping(self) -> Dict[int, str]:
        """Get simple code-to-name mapping dictionary for compatibility."""
        return {code: definition.name for code, definition in self._codes.items()}


class DeviceCodeHandler:
    """Handler for device code property (siid:2, piid:2) with model-specific support."""
    
    def __init__(self, model: str | None = None) -> None:
        """Initialize device code handler.
        
        Args:
            model: Device model identifier (e.g., "A1", "L10", etc.)
        """
        self._device_code: int | None = None
        self._device_code_name: str | None = None
        self._device_code_description: str | None = None
        self._device_code_is_error: bool | None = None
        self._device_code_is_warning: bool | None = None
        
        # Set up device code registry based on model
        self._registry = get_device_code_registry(model)
        self._model = model
    
    def set_model(self, model: str | None) -> None:
        """Update device model and switch to appropriate registry.
        
        Args:
            model: Device model identifier (e.g., "A1", "L10", etc.)
        """
        self._registry = get_device_code_registry(model)
        self._model = model
    
    def parse_value(self, value: Any) -> bool:
        """Parse device code value and update internal state.
        
        Args:
            value: Device code value from MQTT (should be int or convertible to int)
            
        Returns:
            True if parsing succeeded, False otherwise
        """
        try:
            # Convert value to integer
            code = int(value)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid device code value: %s", value)
            return False

        # Get device code definition from registry
        definition = self._registry.get_code(code)
        
        # Update device code properties
        self._device_code = code
        self._device_code_name = definition.name if definition else f"Unknown Code {code}"
        self._device_code_description = definition.description if definition else f"Unknown device code: {code}"
        self._device_code_is_error = definition.is_error() if definition else False
        self._device_code_is_warning = definition.is_warning() if definition else False
        
        return True
    
    def get_notification_data(self) -> Dict[str, Any]:
        """Get notification data dictionary for Home Assistant cards.
        
        Returns:
            Dictionary with device code notification data
        """
        return {
            NOTIFICATION_CODE_FIELD: self._device_code,
            NOTIFICATION_NAME_FIELD: self._device_code_name,
            NOTIFICATION_DESCRIPTION_FIELD: self._device_code_description,
            NOTIFICATION_TIMESTAMP_FIELD: datetime.now().isoformat()
        }
    
    @property
    def device_code(self) -> int | None:
        """Return current device code (2:2)."""
        return self._device_code
    
    @property
    def device_code_name(self) -> str | None:
        """Return device code name."""
        return self._device_code_name
    
    @property
    def device_code_description(self) -> str | None:
        """Return device code description."""
        return self._device_code_description
    
    @property
    def device_code_is_error(self) -> bool | None:
        """Return True if device code represents an error."""
        return self._device_code_is_error
    
    @property
    def device_code_is_warning(self) -> bool | None:
        """Return True if device code represents a warning."""
        return self._device_code_is_warning


# Base device code definitions (siid:2, piid:2), based on the Dreame A2
BASE_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    0: DeviceCodeDefinition(
        code=0,
        name="NO_DEVICE_CODE",
        description="No device code - normal operation",
        code_type=DeviceCodeType.INFO
    ),
    2: DeviceCodeDefinition(
        code=2,
        name="MOWER_GOT_STUCK",
        description="Mower got stuck and cannot continue",
        code_type=DeviceCodeType.ERROR
    ),
    9: DeviceCodeDefinition(
        code=9,
        name="BUMPER_ERROR",
        description="Bumper error",
        code_type=DeviceCodeType.ERROR
    ),
    18: DeviceCodeDefinition(
        code=18,
        name="ROBOT_IS_OUT_OF_MAP",
        description="Robot is out of map boundaries",
        code_type=DeviceCodeType.ERROR
    ),
    19: DeviceCodeDefinition(
        code=19,
        name="ROBOT_IS_LOST",
        description="Robot is lost (or Emergency stop pressed for A1)",
        code_type=DeviceCodeType.ERROR
    ),
    21: DeviceCodeDefinition(
        code=21,
        name="ROBOT_STUCK_IN_NO_GO_ZONE",
        description="The robot is stuck in a no-go zone",
        code_type=DeviceCodeType.ERROR
    ),
    23: DeviceCodeDefinition(
        code=23,
        name="EMERGENCY_STOP_PRESSED",
        description="Emergency stop button was pressed",
        code_type=DeviceCodeType.ERROR
    ),
    24: DeviceCodeDefinition(
        code=24,
        name="BATTERY_IS_LOW_POWERING_OFF",
        description="Battery is low, powering off",
        code_type=DeviceCodeType.ERROR
    ),
    27: DeviceCodeDefinition(
        code=27,
        name="POSITIONING_FAILED",
        description="Positioning failed",
        code_type=DeviceCodeType.ERROR
    ),
    28: DeviceCodeDefinition(
        code=28,
        name="BLADES_SEVERELY_WORN",
        description="Blades are severely worn. Replace them soon.",
        code_type=DeviceCodeType.WARNING
    ),
    29: DeviceCodeDefinition(
        code=29,
        name="CLEANING_BRUSH_SEVERELY_USED",
        description="The cleaning brush is severely used. Replace it soon.",
        code_type=DeviceCodeType.WARNING
    ),
    31: DeviceCodeDefinition(
        code=31,
        name="FAILED_TO_RETURN_TO_DOCK",
        description="Failed to return to docking station",
        code_type=DeviceCodeType.ERROR
    ),
    32: DeviceCodeDefinition(
        code=32,
        name="FAILED_TO_DOCK_IN_STATION",
        description="Failed to dock in the charging station",
        code_type=DeviceCodeType.ERROR
    ),
    34: DeviceCodeDefinition(
        code=34,
        name="BATTERY_IS_LOW_RETURNING_TO_DOCK_34",
        description="Battery is low, returning to dock",
        code_type=DeviceCodeType.INFO
    ),
    35: DeviceCodeDefinition(
        code=35,
        name="BATTERY_IS_LOW_RETURNING_TO_DOCK_35",
        description="Battery is low, returning to dock",
        code_type=DeviceCodeType.INFO
    ),
    43: DeviceCodeDefinition(
        code=43,
        name="CHARGING_PAUSED_BATTERY_TEMP_TOO_LOW",
        description="Charging paused: battery temperature is too low",
        code_type=DeviceCodeType.WARNING
    ),
    47: DeviceCodeDefinition(
        code=47,
        name="ROBOT_IS_WORKING_SCHEDULED_TASK_CANCELLED",
        description="Robot is working, scheduled task cancelled",
        code_type=DeviceCodeType.INFO
    ),
    48: DeviceCodeDefinition(
        code=48,
        name="MOWING_COMPLETED",
        description="Mowing task completed successfully",
        code_type=DeviceCodeType.INFO
    ),
    49: DeviceCodeDefinition(
        code=49,
        name="MOWING_TASK_STARTED",
        description="Mowing task started",
        code_type=DeviceCodeType.INFO
    ),
    50: DeviceCodeDefinition(
        code=50,
        name="MOWING_STARTED",
        description="Mowing operation started",
        code_type=DeviceCodeType.INFO
    ),
    53: DeviceCodeDefinition(
        code=53,
        name="RAIN_DETECTED",
        description="Rain detected, operation paused",
        code_type=DeviceCodeType.WARNING
    ),
    54: DeviceCodeDefinition(
        code=54,
        name="LOW_BATTERY",
        description="Low battery warning",
        code_type=DeviceCodeType.WARNING
    ),
    56: DeviceCodeDefinition(
        code=56,
        name="WATER_ON_LIDAR",
        description="Water detected on LiDAR sensor",
        code_type=DeviceCodeType.WARNING
    ),
    59: DeviceCodeDefinition(
        code=59,
        name="LID_IS_OPEN",
        description="Device lid is open",
        code_type=DeviceCodeType.ERROR
    ),
    61: DeviceCodeDefinition(
        code=61,
        name="DND_START",
        description="Do Not Disturb period started",
        code_type=DeviceCodeType.INFO
    ),
    70: DeviceCodeDefinition(
        code=70,
        name="DND_END",
        description="Do Not Disturb period ended",
        code_type=DeviceCodeType.INFO
    ),
}
BASE_DEVICE_CODE_REGISTRY = DeviceCodeRegistry(BASE_DEVICE_CODES)

# A1 and A1 Pro model variations
A1_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    19: DeviceCodeDefinition(
        code=19,
        name="EMERGENCY_STOP_PRESSED",
        description="Emergency stop pressed (A1 model specific)",
        code_type=DeviceCodeType.ERROR
    ),
    53: DeviceCodeDefinition(
        code=53,
        name="MOWING_STARTED",
        description="Mowing operation started",
        code_type=DeviceCodeType.INFO
    ),
    70: DeviceCodeDefinition(
        code=70,
        name="MOWING_RESUMED_AFTER_CHARGING",
        description="Mower resumed mowing after recharge",
        code_type=DeviceCodeType.INFO
    ),
    73: DeviceCodeDefinition(
        code=73,
        name="ROBOT_LIFTED",
        description="Robot was lifted",
        code_type=DeviceCodeType.ERROR
    ),
}
A1_DEVICE_CODE_REGISTRY = BASE_DEVICE_CODE_REGISTRY.extend(A1_DEVICE_CODES)

# MOVA 600 and MOVA 1000 model variations
MOVA_DEVICE_CODES: Dict[int, DeviceCodeDefinition] = {
    # MOVA-specific device codes
    0: DeviceCodeDefinition(
        code=0,
        name="ROBOT_LIFTED",
        description="Robot lifted",
        code_type=DeviceCodeType.ERROR
    ),
    1: DeviceCodeDefinition(
        code=1,
        name="ROBOT_TILTED",
        description="Robot tilted",
        code_type=DeviceCodeType.ERROR
    ),
    12: DeviceCodeDefinition(
        code=12,
        name="LIDAR_IS_BLOCKED",
        description="Lidar is blocked",
        code_type=DeviceCodeType.ERROR
    ),
    30: DeviceCodeDefinition(
        code=30,
        name="MAINTENANCE_TIME_REACHED",
        description="Robot maintenance time reached. Maintain the robot soon",
        code_type=DeviceCodeType.WARNING
    ),
    55: DeviceCodeDefinition(
        code=55,
        name="ROBOT_CANT_START_LOW_BATTERY",
        description="Robot can't start due to low battery",
        code_type=DeviceCodeType.ERROR
    ),
    70: DeviceCodeDefinition(
        code=70,
        name="CONTINUE_UNFINISHED_TASK",
        description="Robot will continue the unfinished task",
        code_type=DeviceCodeType.INFO
    ),
}
MOVA_DEVICE_CODE_REGISTRY = BASE_DEVICE_CODE_REGISTRY.extend(MOVA_DEVICE_CODES)


def get_device_code_registry(model: str | None = None) -> DeviceCodeRegistry:
    """Get device code registry for specific model."""
    if model is None:
        return BASE_DEVICE_CODE_REGISTRY

    if model in ["dreame.mower.p2255", "dreame.mower.g2422"]:  # A1 and A1 Pro models
        return A1_DEVICE_CODE_REGISTRY
    elif model in ["mova.mower.g2405b", "mova.mower.g2405c"]:  # MOVA models
        return MOVA_DEVICE_CODE_REGISTRY
    
    return BASE_DEVICE_CODE_REGISTRY
