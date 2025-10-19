"""Tests for the Dreame Mower Camera Entity."""
import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.dreame_mower.camera import DreameMowerCameraEntity
from custom_components.dreame_mower.coordinator import DreameMowerCoordinator


# Path to test data
TEST_DATA_DIR = Path(__file__).parent / "dreame" / "test_data"
GOLDEN_JSON_FILE = TEST_DATA_DIR / "test_svg_map_generator.json"
GOLDEN_SVG_FILE = TEST_DATA_DIR / "test_svg_map_generator_rotated_0_golden.svg"


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = Mock(spec=DreameMowerCoordinator)
    coordinator.hass = Mock()
    coordinator.hass.loop = asyncio.get_event_loop()
    coordinator.device = Mock()
    coordinator.device.name = "Test Mower"
    coordinator.device.status_code = 1  # Some default status
    coordinator.device.register_property_callback = Mock()
    coordinator.device.mower_coordinates = None  # No current position by default
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    config_entry = Mock(spec=pytest.importorskip("homeassistant.config_entries").ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    return config_entry


@pytest.fixture
def camera_entity(mock_coordinator, mock_config_entry):
    """Create a camera entity instance."""
    return DreameMowerCameraEntity(mock_coordinator, mock_config_entry)


@pytest.fixture
def golden_map_data():
    """Load the golden JSON test data."""
    with open(GOLDEN_JSON_FILE, 'r') as f:
        return json.load(f)


@pytest.fixture
def golden_svg():
    """Load the golden SVG expected output."""
    with open(GOLDEN_SVG_FILE, 'r') as f:
        return f.read()


class TestDreameMowerCameraEntity:
    """Test the DreameMowerCameraEntity class."""

    def test_initialization(self, camera_entity, mock_coordinator):
        """Test camera entity initialization."""
        assert camera_entity.coordinator == mock_coordinator
        assert camera_entity._attr_unique_id == "test_entry_id_map_camera"
        assert camera_entity._attr_translation_key == "map_camera"
        assert camera_entity.content_type == "image/svg+xml"
    
    def test_save_actual_svg_output(self, camera_entity, golden_map_data, golden_svg):
        """Generate and save the actual SVG output for comparison with golden file.
        
        It compares the actual output with the golden file, allowing only
        the timestamp in "Updated: YYYY-MM-DD HH:MM:SS" to differ.
        """
        # Generate SVG from golden data
        result = camera_entity._generate_map_image(golden_map_data)
        
        # Save to actual output file
        actual_svg_file = TEST_DATA_DIR / "test_svg_map_generator_rotated_0_actual.svg"
        with open(actual_svg_file, 'wb') as f:
            f.write(result)
        
        # Verify the file was written
        assert actual_svg_file.exists()
        assert actual_svg_file.stat().st_size > 0
        
        # Basic validation that it's valid SVG
        svg_output = result.decode('utf-8')
        assert svg_output.startswith('<?xml')
        assert '<svg' in svg_output
        assert '</svg>' in svg_output
        
        # Compare with golden file, normalizing timestamps
        # Pattern to match: "Updated: 2025-10-19 15:01:49" or similar
        timestamp_pattern = r'Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
        
        # Normalize both SVGs by replacing timestamps with a placeholder
        actual_normalized = re.sub(timestamp_pattern, 'Updated: TIMESTAMP', svg_output)
        golden_normalized = re.sub(timestamp_pattern, 'Updated: TIMESTAMP', golden_svg)
        
        # Compare the normalized versions
        assert actual_normalized == golden_normalized, (
            "Generated SVG differs from golden file (excluding timestamp). "
            f"Actual file saved to: {actual_svg_file}"
        )

