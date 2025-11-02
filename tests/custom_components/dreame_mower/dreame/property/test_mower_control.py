"""Test the mower control property handler."""

import pytest
from unittest.mock import Mock

from custom_components.dreame_mower.dreame.property.mower_control import (
    MowerControlPropertyHandler,
    MowerControlStatusHandler,
    MowerControlAction,
    MOWER_CONTROL_STATUS_PROPERTY_NAME,
)


class TestMowerControlStatusHandler:
    """Test MowerControlStatusHandler for property 2:56."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = MowerControlStatusHandler()

    def test_parse_continue_status_dict_format(self):
        """Test parsing continue status from dict format."""
        status_data = {'status': [[0, 0]]}
        
        result = self.handler.parse_value(status_data)
        
        assert result is True
        assert self.handler.action == MowerControlAction.CONTINUE
        assert self.handler.status_code == 0
        assert self.handler.raw_status == [[0, 0]]
        assert self.handler.is_continuing is True
        assert self.handler.is_paused is False
        assert self.handler.is_completed is False

    def test_parse_pause_status_dict_format(self):
        """Test parsing pause status from dict format."""
        status_data = {'status': [[1, 4]]}
        
        result = self.handler.parse_value(status_data)
        
        assert result is True
        assert self.handler.action == MowerControlAction.PAUSE
        assert self.handler.status_code == 4
        assert self.handler.raw_status == [[1, 4]]
        assert self.handler.is_continuing is False
        assert self.handler.is_paused is True
        assert self.handler.is_completed is False

    def test_parse_completed_status_dict_format(self):
        """Test parsing completed status from dict format."""
        status_data = {'status': [[2, 2]]}
        
        result = self.handler.parse_value(status_data)
        
        assert result is True
        assert self.handler.action == MowerControlAction.COMPLETED
        assert self.handler.status_code == 2
        assert self.handler.raw_status == [[2, 2]]
        assert self.handler.is_continuing is False
        assert self.handler.is_paused is False
        assert self.handler.is_completed is True

    def test_parse_empty_status_array(self):
        """Test parsing empty status array - valid case for no active control command."""
        status_data = {'status': []}
        
        result = self.handler.parse_value(status_data)
        
        assert result is True
        assert self.handler.action is None
        assert self.handler.status_code is None
        assert self.handler.raw_status == []
        assert self.handler.is_continuing is None
        assert self.handler.is_paused is None
        assert self.handler.is_completed is None

    def test_parse_status_dict_format_alternative(self):
        """Test parsing status from dict format (alternative values)."""
        status_data = {'status': [[3, 4]]}
        
        result = self.handler.parse_value(status_data)
        
        assert result is True
        assert self.handler.action == MowerControlAction.PAUSE
        assert self.handler.status_code == 4
        assert self.handler.raw_status == [[3, 4]]

    def test_parse_unknown_status_code(self):
        """Test parsing unknown status code returns False."""
        status_data = {'status': [[1, 99]]}  # Unknown status code 99
        
        result = self.handler.parse_value(status_data)
        
        assert result is False  # Should return False for unknown status codes

    def test_parse_invalid_status_missing_field(self):
        """Test parsing invalid status with missing status field."""
        status_data = {'other_field': 'value'}
        
        result = self.handler.parse_value(status_data)
        
        assert result is False

    def test_parse_invalid_status_wrong_type(self):
        """Test parsing invalid status with wrong type."""
        status_data = {'status': 'not_a_list'}
        
        result = self.handler.parse_value(status_data)
        
        assert result is False

    def test_parse_invalid_status_entry_format(self):
        """Test parsing invalid status entry format."""
        status_data = {'status': [['invalid', 'format']]}
        
        result = self.handler.parse_value(status_data)
        
        assert result is False

    def test_parse_invalid_status_entry_short(self):
        """Test parsing status entry with insufficient data."""
        status_data = {'status': [[1]]}  # Missing second element
        
        result = self.handler.parse_value(status_data)
        
        assert result is False

    def test_get_notification_data_with_action(self):
        """Test get_notification_data with valid action."""
        status_data = {'status': [[1, 4]]}
        self.handler.parse_value(status_data)
        
        notification_data = self.handler.get_notification_data()
        
        assert notification_data['action'] == 'pause'
        assert notification_data['status'] == 4
        assert notification_data['value'] == [[1, 4]]

    def test_get_notification_data_empty_status(self):
        """Test get_notification_data with empty status."""
        status_data = {'status': []}
        self.handler.parse_value(status_data)
        
        notification_data = self.handler.get_notification_data()
        
        assert notification_data['action'] is None
        assert notification_data['status'] is None
        assert notification_data['value'] == []


class TestMowerControlPropertyHandler:
    """Test MowerControlPropertyHandler integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = MowerControlPropertyHandler()
        self.notify_callback = Mock()

    def test_handle_empty_status_message(self):
        """Test handling the specific empty status message from logs."""
        # Simulate the exact message from the logs
        mqtt_message = {
            'id': 291, 
            'method': 'properties_changed', 
            'params': [{
                'did': '-100000005', 
                'piid': 56, 
                'siid': 2, 
                'value': {'status': []}
            }]
        }
        
        # Extract the relevant parts for the handler
        param = mqtt_message['params'][0]
        siid = param['siid']
        piid = param['piid'] 
        value = param['value']
        
        # Use the real property constant for matching - no need to mock it
        from custom_components.dreame_mower.dreame.const import MOWER_CONTROL_STATUS_PROPERTY
        
        # Verify this matches the expected property
        assert MOWER_CONTROL_STATUS_PROPERTY.matches(siid, piid)
        
        result = self.handler.handle_property_update(siid, piid, value, self.notify_callback)
        
        # Verify successful handling
        assert result is True
        
        # Verify notification was called
        self.notify_callback.assert_called()
        
        # Check the notification data
        call_args = self.notify_callback.call_args_list
        main_notification = next(call for call in call_args if call[0][0] == MOWER_CONTROL_STATUS_PROPERTY_NAME)
        
        notification_data = main_notification[0][1]
        assert notification_data['action'] is None
        assert notification_data['status'] is None
        assert notification_data['value'] == []
        
        # Verify state properties
        assert self.handler.current_action is None
        assert self.handler.last_status_code is None
        assert self.handler.is_paused is None
        assert self.handler.is_continuing is None  
        assert self.handler.is_completed is None

    def test_handle_valid_pause_message(self):
        """Test handling a valid pause message."""
        # Simulate a pause message
        siid = 2
        piid = 56
        value = {'status': [[1, 4]]}
        
        # Use the real property constant
        from custom_components.dreame_mower.dreame.const import MOWER_CONTROL_STATUS_PROPERTY
        assert MOWER_CONTROL_STATUS_PROPERTY.matches(siid, piid)
        
        result = self.handler.handle_property_update(siid, piid, value, self.notify_callback)
        
        # Verify successful handling
        assert result is True
        
        # Verify state properties
        assert self.handler.current_action == MowerControlAction.PAUSE
        assert self.handler.last_status_code == 4
        assert self.handler.is_paused is True
        assert self.handler.is_continuing is False
        assert self.handler.is_completed is False

    def test_handle_unrecognized_property(self):
        """Test handling unrecognized property returns False."""
        # Different property that shouldn't be handled
        siid = 3
        piid = 99
        value = {'status': [[1, 4]]}
        
        # Use the real property constant - this should NOT match siid=3, piid=99
        from custom_components.dreame_mower.dreame.const import MOWER_CONTROL_STATUS_PROPERTY
        assert not MOWER_CONTROL_STATUS_PROPERTY.matches(siid, piid)
        
        result = self.handler.handle_property_update(siid, piid, value, self.notify_callback)
        
        # Should return False for unrecognized properties
        assert result is False
        
        # No notifications should be sent
        self.notify_callback.assert_not_called()