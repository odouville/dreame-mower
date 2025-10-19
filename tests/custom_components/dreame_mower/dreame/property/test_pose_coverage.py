"""Tests for pose coverage property handler with mission completion tracking."""

import pytest
from custom_components.dreame_mower.dreame.property.pose_coverage import PoseCoverageHandler


@pytest.fixture
def handler():
    """Create a pose coverage handler for testing."""
    return PoseCoverageHandler()


def test_handler_initialization(handler):
    """Test handler initializes with correct default values."""
    assert handler.current_area_sqm is None
    assert handler.total_area_sqm is None
    assert handler.progress_percent is None
    assert handler.x_coordinate is None
    assert handler.y_coordinate is None
    assert handler._mission_completed is False


def test_parse_full_format_normal_progress(handler):
    """Test parsing full format with normal progress (not completed)."""
    # Create a mock payload with 96% progress (96/100 sqm)
    # Full format: 33 bytes total (0xCE + 31 bytes + 0xCE)
    payload = [
        0xCE,  # Start sentinel
        # Bytes 0-1: X coordinate (int16 LE) = 100
        100, 0,
        # Bytes 2-3: Y coordinate (int16 LE) = 200
        200, 0,
        # Bytes 4-5: padding
        0, 0,
        # Bytes 6-7: Heading (int16 LE) = 45
        45, 0,
        # Bytes 8-21: other data
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        # Bytes 22-23: Segment (uint16 LE) = 5
        5, 0,
        # Bytes 24: padding
        0,
        # Bytes 25-26: Total area in centi-sqm (uint16 LE) = 10000 (100.00 sqm)
        16, 39,  # 10000 in little-endian
        # Bytes 27: padding
        0,
        # Bytes 28-29: Current area in centi-sqm (uint16 LE) = 9600 (96.00 sqm)
        128, 37,  # 9600 in little-endian
        # Bytes 30: padding
        0,
        0xCE  # End sentinel
    ]
    
    result = handler.parse_value(payload)
    
    assert result is True
    assert handler.x_coordinate == 100
    assert handler.y_coordinate == 200
    assert handler.heading == 45
    assert handler.segment == 5
    assert handler.current_area_sqm == 96.0
    assert handler.total_area_sqm == 100.0
    assert handler.progress_percent == 96.0


def test_mission_completion_caps_progress_at_100(handler):
    """Test that marking mission as completed caps progress at 100%."""
    # First parse with 96% progress
    payload = [
        0xCE,  # Start sentinel
        100, 0,  # X
        200, 0,  # Y
        0, 0,  # padding
        45, 0,  # Heading
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # other data
        5, 0,  # Segment
        0,  # padding
        16, 39,  # Total: 10000 centi-sqm (100 sqm)
        0,  # padding
        128, 37,  # Current: 9600 centi-sqm (96 sqm)
        0,  # padding
        0xCE  # End sentinel
    ]
    
    handler.parse_value(payload)
    assert handler.progress_percent == 96.0
    
    # Mark mission as completed
    handler.mark_mission_completed()
    
    # Progress should now be capped at 100%
    assert handler.progress_percent == 100.0
    assert handler._mission_completed is True


def test_mission_completion_flag_affects_subsequent_parsing(handler):
    """Test that mission completion flag affects subsequent parse operations."""
    # Mark mission as completed first
    handler.mark_mission_completed()
    
    # Now parse with 96% progress
    payload = [
        0xCE,  # Start sentinel
        100, 0,  # X
        200, 0,  # Y
        0, 0,  # padding
        45, 0,  # Heading
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # other data
        5, 0,  # Segment
        0,  # padding
        16, 39,  # Total: 10000 centi-sqm (100 sqm)
        0,  # padding
        128, 37,  # Current: 9600 centi-sqm (96 sqm)
        0,  # padding
        0xCE  # End sentinel
    ]
    
    handler.parse_value(payload)
    
    # Even though calculated progress is 96%, it should be capped at 100%
    assert handler.progress_percent == 100.0


def test_reset_mission_completion(handler):
    """Test resetting mission completion flag for new mission."""
    # Mark mission as completed
    handler.mark_mission_completed()
    assert handler._mission_completed is True
    
    # Reset for new mission
    handler.reset_mission_completion()
    assert handler._mission_completed is False


def test_complete_workflow_mission_lifecycle(handler):
    """Test complete workflow: start mission, complete, then start new mission."""
    # Step 1: Parse initial progress (50%)
    payload_50 = [
        0xCE,
        100, 0, 200, 0, 0, 0, 45, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        5, 0, 0,
        16, 39,  # Total: 10000 (100 sqm)
        0,
        136, 19,  # Current: 5000 (50 sqm)
        0,
        0xCE
    ]
    handler.parse_value(payload_50)
    assert handler.progress_percent == 50.0
    
    # Step 2: Parse progress near end (96%)
    payload_96 = [
        0xCE,
        150, 0, 250, 0, 0, 0, 90, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        8, 0, 0,
        16, 39,  # Total: 10000 (100 sqm)
        0,
        128, 37,  # Current: 9600 (96 sqm)
        0,
        0xCE
    ]
    handler.parse_value(payload_96)
    assert handler.progress_percent == 96.0
    
    # Step 3: Mission completion event received - cap at 100%
    handler.mark_mission_completed()
    assert handler.progress_percent == 100.0
    assert handler._mission_completed is True
    
    # Step 4: Any further updates while completed should stay at 100%
    handler.parse_value(payload_96)
    assert handler.progress_percent == 100.0
    
    # Step 5: Start new mission - reset flag
    handler.reset_mission_completion()
    assert handler._mission_completed is False
    
    # Step 6: Parse new mission progress (30%)
    payload_30 = [
        0xCE,
        50, 0, 100, 0, 0, 0, 30, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        2, 0, 0,
        16, 39,  # Total: 10000 (100 sqm)
        0,
        184, 11,  # Current: 3000 (30 sqm)
        0,
        0xCE
    ]
    handler.parse_value(payload_30)
    assert handler.progress_percent == 30.0  # Should be actual progress, not capped


def test_mission_completion_with_zero_progress(handler):
    """Test that marking completed with zero progress doesn't set to 100%."""
    # Parse with 0% progress
    payload_zero = [
        0xCE,
        0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0,
        16, 39,  # Total: 10000 (100 sqm)
        0,
        0, 0,  # Current: 0 (0 sqm)
        0,
        0xCE
    ]
    handler.parse_value(payload_zero)
    assert handler.progress_percent == 0.0
    
    # Mark as completed - should NOT cap at 100% when progress is 0
    handler.mark_mission_completed()
    assert handler.progress_percent == 0.0  # Stays at 0, not capped


def test_mission_completion_with_no_prior_progress(handler):
    """Test marking mission completed before any progress data is parsed."""
    # Mark completed without any progress data
    handler.mark_mission_completed()
    
    # Progress should remain None (not set to 100%)
    assert handler.progress_percent is None
    assert handler._mission_completed is True


def test_parse_short_format_unaffected_by_completion_flag(handler):
    """Test that short format parsing is unaffected by completion flag."""
    # Mark mission as completed
    handler.mark_mission_completed()
    
    # Parse short format (8 bytes total: 0xCE + 6 bytes + 0xCE)
    short_payload = [
        0xCE,
        100, 0,  # X
        200, 0,  # Y
        50, 0,   # Unknown
        0xCE
    ]
    
    result = handler.parse_value(short_payload)
    
    assert result is True
    assert handler.x_coordinate == 100
    assert handler.y_coordinate == 200
    # Short format doesn't update progress, so it should remain None
    assert handler.progress_percent is None


def test_progress_notification_data(handler):
    """Test getting progress notification data."""
    # Parse some progress
    payload = [
        0xCE,
        100, 0, 200, 0, 0, 0, 45, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        5, 0, 0,
        16, 39,  # Total: 10000 (100 sqm)
        0,
        232, 29,  # Current: 7656 (76.56 sqm)
        0,
        0xCE
    ]
    handler.parse_value(payload)
    
    notification_data = handler.get_progress_notification_data()
    
    assert notification_data["current_area_sqm"] == 76.56
    assert notification_data["total_area_sqm"] == 100.0
    assert notification_data["progress_percent"] == 76.56
    
    # Now complete the mission
    handler.mark_mission_completed()
    
    notification_data_completed = handler.get_progress_notification_data()
    assert notification_data_completed["progress_percent"] == 100.0


def test_progress_percent_capped_at_100_even_if_calculation_exceeds(handler):
    """Test that progress is capped at 100% even if calculated value would exceed it."""
    # Create scenario where current > total (edge case)
    payload = [
        0xCE,
        100, 0, 200, 0, 0, 0, 45, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        5, 0, 0,
        232, 3,  # Total: 1000 centi-sqm (10 sqm)
        0,
        16, 39,  # Current: 10000 centi-sqm (100 sqm) - exceeds total
        0,
        0xCE
    ]
    
    handler.parse_value(payload)
    
    # Should be capped at 100%, not 1000%
    assert handler.progress_percent == 100.0
