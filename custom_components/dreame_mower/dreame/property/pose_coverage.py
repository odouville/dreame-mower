"""Pose and Coverage property handling for Dreame Mower Implementation.

This module provides parsing and handling for Service 1, Property 4 (1:4) which contains:
- Mowing progress data with current and total area information
- X/Y coordinates describing the mowing path
- Additional metadata like segment information

The property can contain two different data formats:
1. Full mowing data (33-byte payload) - sent regularly during mowing sessions
2. Shorter format (8-byte payload) - unknown purpose, less common

Based on analysis from dev/analyses/README_property_1_4.md and dev/analyze_property_1_4.py
"""

from __future__ import annotations

import logging
import struct
from typing import Dict, Any, List

_LOGGER = logging.getLogger(__name__)

# Property name constants for notifications
POSE_COVERAGE_PROGRESS_PROPERTY_NAME = "mowing_progress"
POSE_COVERAGE_COORDINATES_PROPERTY_NAME = "mowing_coordinates"

# Progress data field constants
PROGRESS_CURRENT_AREA_FIELD = "current_area_sqm"
PROGRESS_TOTAL_AREA_FIELD = "total_area_sqm"
PROGRESS_PERCENT_FIELD = "progress_percent"

# Coordinates data field constants
COORDINATES_X_FIELD = "x"
COORDINATES_Y_FIELD = "y"
COORDINATES_SEGMENT_FIELD = "segment"
COORDINATES_HEADING_FIELD = "heading"

# Data format constants
SENTINEL_BYTE = 206  # 0xCE - frame delimiter
FULL_PAYLOAD_LENGTH = 31  # Expected payload length for full format
SHORT_PAYLOAD_LENGTH = 6   # Expected payload length for short format

# Byte positions in payload (0-indexed)
X_POSITION = (0, 1)      # int16 LE - X coordinate
Y_POSITION = (2, 3)      # int16 LE - Y coordinate  
HEADING_POSITION = (6, 7) # int16 LE - Heading/state
SEGMENT_POSITION = (22, 23) # uint16 - Segment/lane index
CURRENT_AREA_POSITION = (28, 29) # uint16 - Current area (centi-sqm)
TOTAL_AREA_POSITION = (25, 26)   # uint16 - Total area (centi-sqm)


class PoseCoverageHandler:
    """Handler for pose and coverage telemetry property (1:4)."""
    
    def __init__(self) -> None:
        """Initialize pose coverage handler."""
        # Progress tracking
        self._current_area_sqm: float | None = None
        self._total_area_sqm: float | None = None
        self._progress_percent: float | None = None
        self._mission_completed: bool = False  # Flag to indicate mission completion
        
        # Coordinate tracking
        self._x_coordinate: int | None = None
        self._y_coordinate: int | None = None
        self._segment: int | None = None
        self._heading: int | None = None
        
        # Path history for visualization
        self._path_history: List[Dict[str, Any]] = []
    
    def parse_value(self, value: Any) -> bool:
        """Parse pose coverage value from binary array."""
        try:
            # Ensure we have a list of integers (byte array)
            if not isinstance(value, list):
                _LOGGER.warning("Invalid pose coverage value type: %s", type(value))
                return False
            
            if len(value) < 8:
                _LOGGER.warning("Pose coverage payload too short: %d bytes", len(value))
                return False
            
            # Verify sentinel bytes
            if value[0] != SENTINEL_BYTE or value[-1] != SENTINEL_BYTE:
                _LOGGER.warning("Invalid sentinel bytes in pose coverage data: start=%d, end=%d", 
                              value[0], value[-1])
                return False
            
            # Extract payload (remove sentinel bytes)
            payload = value[1:-1]
            payload_length = len(payload)
            
            if payload_length == FULL_PAYLOAD_LENGTH:
                return self._parse_full_format(payload)
            elif payload_length == SHORT_PAYLOAD_LENGTH:
                return self._parse_short_format(payload)
            else:
                _LOGGER.warning("Unknown pose coverage payload length: %d bytes", payload_length)
                return False
                
        except Exception as ex:
            _LOGGER.error("Failed to parse pose coverage data: %s", ex)
            return False
    
    def _parse_full_format(self, payload: List[int]) -> bool:
        """Parse full format (31-byte payload) with complete mowing data."""
        try:
            # Extract coordinates (int16 little-endian)
            x = self._read_int16_le(payload, X_POSITION[0])
            y = self._read_int16_le(payload, Y_POSITION[0])
            
            # Extract heading/state
            heading = self._read_int16_le(payload, HEADING_POSITION[0])
            
            # Extract segment information
            segment = self._read_uint16_le(payload, SEGMENT_POSITION[0])
            
            # Extract area information (convert from centi-sqm to sqm)
            current_area_centisqm = self._read_uint16_le(payload, CURRENT_AREA_POSITION[0])
            total_area_centisqm = self._read_uint16_le(payload, TOTAL_AREA_POSITION[0])
            
            current_area_sqm = current_area_centisqm / 100.0
            total_area_sqm = total_area_centisqm / 100.0
            
            # Calculate progress percentage
            progress_percent = 0.0
            if total_area_sqm > 0:
                progress_percent = min(100.0, (current_area_sqm / total_area_sqm) * 100.0)
            
            # If mission is marked as completed, cap progress at 100%
            if self._mission_completed and progress_percent > 0:
                progress_percent = 100.0
            
            # Update state
            self._x_coordinate = x
            self._y_coordinate = y
            self._heading = heading
            self._segment = segment
            self._current_area_sqm = current_area_sqm
            self._total_area_sqm = total_area_sqm
            self._progress_percent = progress_percent
            
            # Add to path history (keep last 1000 points to avoid memory issues)
            path_point = {
                "x": x,
                "y": y,
                "heading": heading,
                "segment": segment,
                "timestamp": None  # Will be added by caller if available
            }
            self._path_history.append(path_point)
            if len(self._path_history) > 1000:
                self._path_history.pop(0)
            
            return True
            
        except Exception as ex:
            _LOGGER.error("Failed to parse full format pose coverage: %s", ex)
            return False
    
    def _parse_short_format(self, payload: List[int]) -> bool:
        """Parse short format (6-byte payload) with limited data."""
        try:
            # For now, just extract coordinates from short format
            # The meaning of other bytes is not yet understood
            x = self._read_int16_le(payload, 0)
            y = self._read_int16_le(payload, 2)
            
            # Update coordinate state only
            self._x_coordinate = x
            self._y_coordinate = y
            
            _LOGGER.debug("Short pose coverage parsed: x=%d, y=%d", x, y)
            return True
            
        except Exception as ex:
            _LOGGER.error("Failed to parse short format pose coverage: %s", ex)
            return False
    
    def _read_int16_le(self, payload: List[int], offset: int) -> int:
        """Read 16-bit signed integer in little-endian format."""
        if offset + 1 >= len(payload):
            raise ValueError(f"Payload too short for int16 at offset {offset}")
        
        # Pack bytes and unpack as little-endian signed short
        bytes_data = bytes([payload[offset], payload[offset + 1]])
        return struct.unpack('<h', bytes_data)[0]
    
    def _read_uint16_le(self, payload: List[int], offset: int) -> int:
        """Read 16-bit unsigned integer in little-endian format."""
        if offset + 1 >= len(payload):
            raise ValueError(f"Payload too short for uint16 at offset {offset}")
        
        # Pack bytes and unpack as little-endian unsigned short  
        bytes_data = bytes([payload[offset], payload[offset + 1]])
        return struct.unpack('<H', bytes_data)[0]
    
    def get_progress_notification_data(self) -> Dict[str, Any]:
        """Get progress notification data for Home Assistant."""
        return {
            PROGRESS_CURRENT_AREA_FIELD: self._current_area_sqm,
            PROGRESS_TOTAL_AREA_FIELD: self._total_area_sqm,
            PROGRESS_PERCENT_FIELD: self._progress_percent,
        }
    
    def get_coordinates_notification_data(self) -> Dict[str, Any]:
        """Get coordinates notification data for Home Assistant."""
        return {
            COORDINATES_X_FIELD: self._x_coordinate,
            COORDINATES_Y_FIELD: self._y_coordinate,
            COORDINATES_SEGMENT_FIELD: self._segment,
            COORDINATES_HEADING_FIELD: self._heading,
        }
    
    # Properties for direct access
    @property
    def current_area_sqm(self) -> float | None:
        """Return current mowed area in square meters."""
        return self._current_area_sqm
    
    @property
    def total_area_sqm(self) -> float | None:
        """Return total planned area in square meters."""
        return self._total_area_sqm
    
    @property
    def progress_percent(self) -> float | None:
        """Return mowing progress percentage."""
        return self._progress_percent
    
    @property
    def x_coordinate(self) -> int | None:
        """Return current X coordinate."""
        return self._x_coordinate
    
    @property
    def y_coordinate(self) -> int | None:
        """Return current Y coordinate."""
        return self._y_coordinate
    
    @property
    def segment(self) -> int | None:
        """Return current segment/lane index."""
        return self._segment
    
    @property
    def heading(self) -> int | None:
        """Return current heading/state value."""
        return self._heading
    
    @property
    def path_history(self) -> List[Dict[str, Any]]:
        """Return path history for visualization."""
        return self._path_history.copy()
    
    def clear_path_history(self) -> None:
        """Clear the path history (e.g., when a new mowing session starts)."""
        self._path_history.clear()
        _LOGGER.debug("Path history cleared")
    
    def mark_mission_completed(self) -> None:
        """Mark the current mission as completed.
        
        This will cap the progress percentage at 100% even if the calculated
        progress based on area is slightly less (e.g., 96%).
        Called when a mission completion event is received.
        """
        self._mission_completed = True
        # Update progress to 100% if we have valid data
        if self._progress_percent is not None and self._progress_percent > 0:
            self._progress_percent = 100.0
        _LOGGER.debug("Mission marked as completed, progress set to 100%%")
    
    def reset_mission_completion(self) -> None:
        """Reset the mission completion flag for a new mission.
        
        Called when a new mowing session starts to allow normal progress tracking.
        """
        self._mission_completed = False
        _LOGGER.debug("Mission completion flag reset")


# Unified property handler combining both functionalities
PoseCoveragePropertyHandler = PoseCoverageHandler