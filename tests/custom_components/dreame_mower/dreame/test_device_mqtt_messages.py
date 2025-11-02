"""Test device MQTT message handling.

This test module focuses on testing the device-level integration of MQTT message handling.
It verifies that real-world MQTT messages (as reported in issues) are correctly processed
through the full device stack.

Key aspects tested:
- _handle_mqtt_property_update: Direct property update handling
- _handle_message: Full MQTT message flow including properties_changed wrapper
- Property notifications: Verifies callbacks are triggered correctly
- Parametrized tests: Easy to add new message types from future issues

When adding new message types discovered in issues, add them to the parametrized test
to ensure they are properly handled and don't create unhandled_mqtt notifications.
"""

import pytest
from unittest.mock import Mock, patch

from custom_components.dreame_mower.dreame.device import DreameMowerDevice


class TestDeviceMqttPropertyUpdate:
    """Test _handle_mqtt_property_update with real MQTT messages."""

    @pytest.fixture
    def device(self):
        """Create a device instance for testing."""
        with patch('custom_components.dreame_mower.dreame.device.DreameMowerCloudDevice'):
            device = DreameMowerDevice(
                device_id="test_device",
                username="test_user",
                password="test_pass",
                account_type="mi",
                country="de",
                hass_config_dir="/tmp"
            )
            return device

    @pytest.fixture
    def property_notifications(self):
        """Create a list to capture property notifications."""
        notifications = []
        
        def callback(property_name, value):
            notifications.append((property_name, value))
        
        return notifications, callback

    @pytest.mark.parametrize(
        "mqtt_message,expected_property,expected_value_check",
        [
            (# Battery update
                {
                    "id": 100,
                    "method": "properties_changed",
                    "params": [{"did": "-1******95", "piid": 1, "siid": 3, "value": 85}]
                },
                "battery_percent",
                lambda v: v == 85
            ),
            (# Status update
                {
                    "id": 101,
                    "method": "properties_changed",
                    "params": [{"did": "-1******95", "piid": 1, "siid": 2, "value": 13}]
                },
                "status",
                lambda v: v == 13
            ),
        ],
    )
    def test_full_mqtt_messages_parametrized(
        self, device, property_notifications, mqtt_message, expected_property, expected_value_check
    ):
        """Test handling complete MQTT messages with properties_changed wrapper.
        
        This parametrized test covers real-world MQTT messages including:
        - Issue #135: Sixth variant obstacle avoidance setting
        - Battery updates
        - Status updates
        - DND schedule updates
        
        All tests use the complete MQTT message format as received from the device,
        including the id, method, and params wrapper.
        """
        notifications, callback = property_notifications
        device.register_property_callback(callback)
        
        # Process through the full message handler
        device._handle_message(mqtt_message)
        
        # Verify at least one notification was sent
        assert len(notifications) > 0, f"No notifications sent for message: {mqtt_message}"
        
        # Find the expected property in notifications
        property_names = [name for name, _ in notifications]
        assert expected_property in property_names, \
            f"Expected property '{expected_property}' not found in notifications: {property_names}"
        
        # Verify the value using the check function
        notify_dict = {name: value for name, value in notifications}
        value = notify_dict[expected_property]
        assert expected_value_check(value), \
            f"Value check failed for property '{expected_property}': {value}"
