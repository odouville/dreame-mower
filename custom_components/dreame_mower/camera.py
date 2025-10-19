from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from threading import Timer

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.lawn_mower import LawnMowerActivity  # type: ignore[attr-defined]
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN, CONF_MAP_ROTATION
from .coordinator import DreameMowerCoordinator
from .entity import DreameMowerEntity

from .dreame.const import STATUS_PROPERTY, map_status_to_activity, POSE_COVERAGE_PROPERTY
from .dreame.property.pose_coverage import POSE_COVERAGE_COORDINATES_PROPERTY_NAME
from .dreame.svg_map_generator import generate_svg_live_image, generate_svg_map_image

_LOGGER = logging.getLogger(__name__)

# Pose coverage property request interval during live mowing sessions
POSE_COVERAGE_REQUEST_INTERVAL = 120  # 2 minutes in seconds


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dreame Mower camera."""
    coordinator: DreameMowerCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    
    camera = DreameMowerCameraEntity(coordinator, entry)
    async_add_entities([camera], True)


class DreameMowerCameraEntity(DreameMowerEntity, Camera):
    """Camera entity for Dreame Mower map visualization."""

    def __init__(self, coordinator: DreameMowerCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the camera."""
        # Initialize base entity with a suitable key
        DreameMowerEntity.__init__(self, coordinator, "map_camera")
        Camera.__init__(self)
        
        self.config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_map_camera"
        self._attr_translation_key = "map_camera"
        self._attr_supported_features = CameraEntityFeature.ON_OFF
        
        # Set content type for SVG images
        self.content_type = "image/svg+xml"
        
        # Current map data
        self._current_map_data: dict[str, Any] | None = None
        self._historical_file_path: str | None = None
        self._image_bytes: bytes | None = None
        self._is_on = True

        # Live mode state
        self._live_coordinates: list[dict[str, Any]] = []  # Current session live coordinates
        self._base_map_boundary: list[list[int]] = []  # Base map boundary from previous session
        
        # Periodic property request timer for live mode
        self._pose_coverage_timer: Timer | None = None
        self._timer_interval = POSE_COVERAGE_REQUEST_INTERVAL

        # Initial docked state based on current status        
        self._docked = map_status_to_activity(coordinator.device.status_code) == LawnMowerActivity.DOCKED
        
        # Historical files cache
        self._historical_files_cache: list[tuple[str, float]] = []  # [(file_path, mtime), ...]
        self._cache_built = False
        
        # Track current rotation to detect changes
        self._current_rotation = self.config_entry.options.get(CONF_MAP_ROTATION, 0)
        
        # Register for property change notifications
        self.coordinator.device.register_property_callback(self._handle_property_change)

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Build initial historical files cache now that hass is available
        self.hass.create_task(self._refresh_historical_files_cache())

        # If not docked, request initial pose coverage property and start timer
        if not self._docked:
            await self._request_pose_coverage_property()
            self._start_pose_coverage_timer()
        
        # Listen for config entry options updates
        self.async_on_remove(
            self.config_entry.add_update_listener(self._async_config_entry_updated)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity is being removed from Home Assistant."""
        # Ensure timer is stopped and cleaned up
        self._stop_pose_coverage_timer()
        await super().async_will_remove_from_hass()

    async def _async_config_entry_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle config entry options update."""
        new_rotation = entry.options.get(CONF_MAP_ROTATION, 0)
        if new_rotation != self._current_rotation:
            self._current_rotation = new_rotation
            # Re-render the image with new rotation
            if self._is_on:
                if self._live_coordinates:
                    # Re-render live image
                    await self._async_update_live_image()
                else:
                    # Re-render static map
                    await self._async_update_image()
                self.async_write_ha_state()

    async def _request_pose_coverage_property(self) -> None:
        """Request POSE_COVERAGE_PROPERTY from device to maintain live data stream.
        
        During live mowing sessions, the device stops sending pose coverage updates
        after POSE_COVERAGE_REQUEST_INTERVAL if not requested. This method keeps the data
        flowing.
        """
        try:
            parameters = [{
                "siid": POSE_COVERAGE_PROPERTY.siid,
                "piid": POSE_COVERAGE_PROPERTY.piid
            }]
            # Run the blocking HTTP call in an executor to avoid blocking the event loop
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.coordinator.device.cloud_device.get_properties(parameters, retry_count=1)
            )
        except Exception as ex:
            _LOGGER.warning("Failed to request pose coverage property: %s", ex)

    def _start_pose_coverage_timer(self) -> None:
        """Start periodic timer to request pose coverage property during live mowing."""
        if self._pose_coverage_timer is not None:
            self._pose_coverage_timer.cancel()
        
        self._pose_coverage_timer = Timer(self._timer_interval, self._pose_coverage_timer_callback)
        self._pose_coverage_timer.start()

    def _stop_pose_coverage_timer(self) -> None:
        """Stop periodic timer for pose coverage property requests."""
        if self._pose_coverage_timer is not None:
            self._pose_coverage_timer.cancel()
            self._pose_coverage_timer = None

    def _pose_coverage_timer_callback(self) -> None:
        """Timer callback to request pose coverage property and schedule next request."""
        try:
            # Schedule the async property request as a task
            self.hass.create_task(self._request_pose_coverage_property())
            
            # Schedule next request if still in live mode (not docked)
            if not self._docked:
                self._start_pose_coverage_timer()
        except Exception as ex:
            _LOGGER.error("Error in pose coverage timer callback: %s", ex)

    async def _refresh_historical_files_cache(self) -> None:
        """Refresh the historical files cache by scanning the ali_dreame directory."""
        try:
            loop = asyncio.get_event_loop()
            self._historical_files_cache = await loop.run_in_executor(
                None, self._build_historical_files_list_sync
            )
            self._cache_built = True
        except Exception as ex:
            _LOGGER.error("Failed to refresh historical files cache: %s", ex)
            self._historical_files_cache = []
            self._cache_built = True

    def _build_historical_files_list_sync(self) -> list[tuple[str, float]]:
        """Build the historical files list synchronously (runs in executor).
        
        Returns:
            List of (file_path, mtime) tuples sorted by modification time (newest first)
        """
        try:
            ali_dreame_path = os.path.join(
                self.hass.config.config_dir,
                "www",
                "dreame",
                "ali_dreame"
            )
            
            if not os.path.exists(ali_dreame_path):
                return []
            
            # Find all .json files recursively
            json_files = []
            for root, dirs, files in os.walk(ali_dreame_path):
                for file in files:
                    if file.endswith('.json'):
                        full_path = os.path.join(root, file)
                        try:
                            # Get file modification time
                            mtime = os.path.getmtime(full_path)
                            json_files.append((full_path, mtime))
                        except OSError as ex:
                            _LOGGER.warning("Could not stat file %s: %s", full_path, ex)
                            continue  # Skip files we can't stat
            
            # Sort by modification time (newest first)
            json_files.sort(key=lambda x: x[1], reverse=True)
            return json_files
            
        except Exception as ex:
            _LOGGER.error("Error building historical files list: %s", ex)
            return []

    def _handle_property_change(self, property_name: str, value: Any) -> None:
        """Handle property changes from the device."""
        if property_name == POSE_COVERAGE_COORDINATES_PROPERTY_NAME:
            self._handle_live_coordinates_update(value)
        elif property_name == STATUS_PROPERTY.name:
            new_state = map_status_to_activity(value) == LawnMowerActivity.DOCKED
            if new_state != self._docked:
                self._docked = new_state
                if self._docked:
                    # Exiting live mode when docked - stop timer and clear coordinates
                    self._stop_pose_coverage_timer()
                    self._live_coordinates.clear()
                    self.hass.create_task(self._async_update_image(force_refresh=True))
                else:
                    # Entering live mode when undocked - start timer
                    self._start_pose_coverage_timer()

    def _handle_live_coordinates_update(self, coordinates_data: dict[str, Any]) -> None:
        """Handle live coordinate updates during mowing session."""
        try:
            # If not in live mode yet, switch to live mode (new session starting)
            if not self._live_coordinates:
                self._extract_base_map_boundary()
            
            # Add coordinates to live tracking
            self._live_coordinates.append(coordinates_data)
            
            # Limit live coordinates to last 2000 points to avoid memory issues
            if len(self._live_coordinates) > 2000:
                self._live_coordinates = self._live_coordinates[-2000:]
            
            # Update image with new live data
            if self._is_on:
                self.hass.create_task(self._async_update_live_image())
                            
        except Exception as ex:
            _LOGGER.error("Error handling live coordinates update: %s", ex)

    def _extract_base_map_boundary(self) -> None:
        """Extract base map boundary from current map data for live mode overlay."""
        try:
            self._base_map_boundary.clear()
            
            if not self._current_map_data:
                return
                
            map_items = self._current_map_data["map"]
            all_boundary_points = []
            for item in map_items:
                item_data = item.get("data", [])
                for point in item_data:
                    if point[0] != 2147483647 and point[1] != 2147483647:
                        all_boundary_points.append(point)
            
            self._base_map_boundary = all_boundary_points
                        
        except Exception as ex:
            _LOGGER.error("Error extracting base map boundary: %s", ex)

    async def _async_update_live_image(self) -> None:
        """Update camera image with live coordinates overlay."""
        if not self._live_coordinates:
            return
            
        try:
            # Generate live image in executor
            loop = asyncio.get_event_loop()
            self._image_bytes = await loop.run_in_executor(
                None,
                self._generate_live_image
            )
            
        except Exception as ex:
            _LOGGER.error("Failed to update live image: %s", ex)

    def _generate_live_image(self) -> bytes:
        """Generate live map image in SVG format with current coordinates overlay."""
        return generate_svg_live_image(
            self._live_coordinates,
            self._base_map_boundary,
            self._current_map_data,
            self.coordinator,
            rotation=self._current_rotation
        )

    @property
    def is_on(self) -> bool:
        """Return True if the camera is on."""
        return self._is_on

    async def async_turn_on(self) -> None:
        """Turn on the camera."""
        self._is_on = True
        await self._async_update_image()

    async def async_turn_off(self) -> None:
        """Turn off the camera."""
        self._is_on = False
        self._image_bytes = None

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return camera image bytes."""
        return self._image_bytes

    async def async_update(self) -> None:
        """Update the camera with latest map data.
        
        Image updates are primarily handled by event-driven property callbacks,
        but this method provides a fallback to ensure an image is always available.
        """
        if not self._image_bytes:
            await self._async_update_image()



    def _load_historical_file_sync(self, full_path: str) -> dict[str, Any] | None:
        """Synchronously load historical file - runs in executor."""
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as ex:
            _LOGGER.error("Error reading historical file %s: %s", full_path, ex)
            return None

    async def _find_most_recent_historical_file(self, force_refresh: bool = False) -> str | None:
        """Find the most recent historical file using the cached file list.
        
        Returns:
            Full path to the most recent .json file, or None if none found
        """
        try:
            # Build cache if not built yet
            if not self._cache_built or force_refresh:
                await self._refresh_historical_files_cache()
            
            # Return the most recent file from cache
            if self._historical_files_cache:
                return self._historical_files_cache[0][0]  # First item is most recent
            else:
                return None
                
        except Exception as ex:
            _LOGGER.error("Error getting most recent historical file from cache: %s", ex)
            return None

    async def _async_update_image(self, force_refresh: bool = False) -> None:
        """Update the camera image by generating a new map visualization."""

        historical_file = await self._find_most_recent_historical_file(force_refresh=force_refresh)
        if not historical_file:
            _LOGGER.warning("No historical file found")
            return

        try:
            # Load historical file directly (we already have the full path)
            loop = asyncio.get_event_loop()
            self._current_map_data = await loop.run_in_executor(
                None,
                self._load_historical_file_sync,
                historical_file
            )
            if self._current_map_data is None:
                _LOGGER.warning("Failed to load historical file data: %s", historical_file)
                return
            
            # Set relative path for display purposes
            www_dreame_path = os.path.join(self.hass.config.config_dir, "www", "dreame")
            if historical_file.startswith(www_dreame_path):
                self._historical_file_path = os.path.relpath(historical_file, www_dreame_path)
            else:
                self._historical_file_path = os.path.basename(historical_file)

        except Exception as ex:
            _LOGGER.warning("Could not load historical file %s: %s", historical_file, ex)
            return
                    
        try:
            # Generate the map image in an executor to avoid blocking (including module loading)
            loop = asyncio.get_event_loop()
            self._image_bytes = await loop.run_in_executor(
                None, 
                self._generate_map_image,
                self._current_map_data
            )
        except Exception as ex:
            _LOGGER.error("Failed to generate map image: %s", ex)

    def _generate_map_image(self, data: dict[str, Any]) -> bytes:
        """Generate map image in SVG format from map data."""
        return generate_svg_map_image(data, self._historical_file_path, self.coordinator, rotation=self._current_rotation)

    @property
    def available(self) -> bool:
        """Return True if the camera is available."""
        return self.coordinator.device.connected