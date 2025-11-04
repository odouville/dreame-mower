#!/usr/bin/env python3
"""
Comprehensive Dreame Mower Device Configuration Analysis Tool

This tool provides deep analysis of all data types from the Dreame mower's REST API getDeviceData endpoint.
It decodes and interprets:
- SETTINGS data: Advanced mowing features, bit flags, and configurations
- SCHEDULE data: Time-based mowing schedules with base64 encoded time periods
- MAP data: Coordinate points, boundaries, and mapping information  
- FBD_NTYPE data: Forbidden area type configurations
- OTA_INFO data: Over-The-Air update information

Usage:
- Uses the Dreame cloud REST API endpoint getDeviceData to fetch hierarchical device data
  (MAP.*, SETTINGS.*, SCHEDULE.*, etc.) with {"did": "..."}. The decoding and analysis routines
  provide deep inspection of that content.
  See dev/findings/README_rest_api_knowledge.md for REST API details.

Key Features:
- Advanced settings interpretation with bit flag analysis
- Schedule decoding from base64 encoded time periods
- MAP coordinate extraction and boundary analysis (leveraging debug plot script patterns)
- Forbidden area type analysis
- OTA update information parsing
- Comprehensive error handling and data validation

Usage:
    python dev/analyze_device_data.py

The tool connects to your configured Dreame mower device and performs comprehensive
analysis of all configuration data, providing detailed insights into device capabilities
and settings that are not visible through standard user interfaces.

Data Types Analyzed:
- SETTINGS.*: 4 items containing device configurations and feature flags
- SCHEDULE.*: 2 items with encoded time-based mowing schedules  
- MAP.*: 24 items with coordinate data, boundaries, and mapping information
- FBD_NTYPE.*: 2 items with forbidden area type configurations
- OTA_INFO.*: 2 items with over-the-air update information
"""

import json
import logging
import sys
import os
import base64
import struct
import re
from pathlib import Path
from typing import Any, Dict, Union, Optional
from datetime import datetime

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_components.dreame_mower.dreame.cloud.cloud_device import DreameMowerCloudDevice
from custom_components.dreame_mower.const import *

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

class DeviceDataAnalyzer:
    def __init__(self) -> None:
        self.protocol: Optional[DreameMowerCloudDevice] = None

    def decode_schedule_data(self, encoded_data: str) -> Union[Dict[str, Any], str]:
        """Decode base64 encoded schedule data."""
        try:
            if not encoded_data or encoded_data == "":
                return "Empty schedule"
            
            # Decode base64
            decoded_bytes = base64.b64decode(encoded_data)

            # Try to parse as binary data
            schedule_info: Dict[str, Any] = {
                'raw_bytes': decoded_bytes.hex(),
                'length': len(decoded_bytes),
                'time_periods': []
            }

            # The schedule appears to be 7-byte chunks representing time periods
            if len(decoded_bytes) % 7 == 0:
                num_periods = len(decoded_bytes) // 7
                schedule_info['format'] = f'{num_periods} time periods (7 bytes each)'
                
                for i in range(num_periods):
                    chunk = decoded_bytes[i*7:(i+1)*7]
                    period_info = self._decode_time_period(chunk, i + 1)
                    schedule_info['time_periods'].append(period_info)
            else:
                # Try other interpretations if not 7-byte aligned
                schedule_info['format'] = 'Non-standard format'
                schedule_info['raw_interpretation'] = self._try_generic_decode(decoded_bytes)
            
            return schedule_info
            
        except Exception as e:
            return f"Decode error: {e}"

    def _decode_time_period(self, chunk, period_num):
        """Decode a 7-byte time period chunk from schedule data."""
        try:
            if len(chunk) != 7:
                return {
                    'period': period_num,
                    'error': 'Invalid chunk size',
                    'raw_hex': chunk.hex()
                }

            b0, b1, b2, b3, b4, b5, b6 = chunk
            interpretations = []

            # Interpretation 1: b1=hour, b2=minute, b3=duration or param
            if b1 < 24 and b2 < 60:
                start_time = f"{b1:02d}:{b2:02d}"
                if b3 < 24:
                    interpretations.append(f"Start {start_time}, duration {b3}h")
                else:
                    interpretations.append(f"Start {start_time}, param {b3}")

            # Interpretation 2: 16-bit minutes since midnight from b1,b2 (little-endian)
            time_minutes = (b2 << 8) | b1
            if time_minutes < 24 * 60:
                h = time_minutes // 60
                m = time_minutes % 60
                interpretations.append(f"Start (16-bit) {h:02d}:{m:02d}")

            # Interpretation 3: BCD time
            bcd_hour = (b1 >> 4) * 10 + (b1 & 0xF)
            bcd_min = (b2 >> 4) * 10 + (b2 & 0xF)
            if bcd_hour <= 23 and bcd_min <= 59:
                interpretations.append(f"BCD {bcd_hour:02d}:{bcd_min:02d}")

            # Heuristic patterns seen in data
            if b1 == 0xE0 and b2 == 0x71:
                base_minutes = 224 + 113 * 256
                if base_minutes < 24 * 60:
                    h = base_minutes // 60
                    m = base_minutes % 60
                    interpretations.append(f"Pattern E0 71 => {h:02d}:{m:02d}")
                interpretations.append("Pattern E0 71: likely 14:00-20:00 window")
            elif b1 == 0x1C and b2 == 0x32:
                interpretations.append("Pattern 1C 32: likely 07:00-12:00 window")

            if not interpretations:
                interpretations.append(f"Raw values: {b1}, {b2}, {b3}")

            return {
                'period': period_num,
                'identifier': f"0x{b0:02x}",
                'time_bytes': f"0x{b1:02x} 0x{b2:02x} 0x{b3:02x}",
                'padding': f"0x{b4:02x} 0x{b5:02x} 0x{b6:02x}",
                'interpretations': interpretations,
                'raw_hex': chunk.hex(),
            }
        except Exception as e:
            return {'period': period_num, 'error': str(e), 'raw_hex': chunk.hex()}

    def _try_generic_decode(self, decoded_bytes):
        """Generic decoder for non-standard schedule formats."""
        interpretations = []
        
        # Try as pairs of time values
        for i in range(0, len(decoded_bytes) - 1, 2):
            val = struct.unpack('<H', decoded_bytes[i:i+2])[0]
            if val < 24 * 60:
                hours = val // 60
                minutes = val % 60
                interpretations.append(f"Time @{i}: {hours:02d}:{minutes:02d}")
        
        return interpretations

    def dump_device_data_to_json(self, data: Dict[str, Any]) -> None:
        """Dump device data to JSON file with timestamp."""
        try:
            # Create logs directory if it doesn't exist
            logs_dir = Path(__file__).parent / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            # Create timestamp-based filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_file = logs_dir / f"device_data_{timestamp}.json"
            
            # Write data to JSON file with nice formatting
            with open(json_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Device data dumped to: {json_file}")
            print(f"💾 Device data saved to: {json_file}")
            
        except Exception as e:
            logger.error(f"Error dumping device data to JSON: {e}")
            import traceback
            traceback.print_exc()

    def connect_to_device(self):
        """Connect to Dreame cloud via DreameMowerCloudDevice using .vscode/launch.json creds."""
        logger.info("Connecting to cloud using DreameMowerCloudDevice…")

        # Import credentials from launch.json (same as CLI debug)
        try:
            launch_json_path = Path(__file__).parent.parent / ".vscode" / "launch.json"
            with open(launch_json_path, "r") as f:
                launch_config = json.load(f)
                configs = launch_config["configurations"]
                debug_config = next(c for c in configs if "CLI" in c.get("name", ""))
                args = debug_config["args"]
                
                # Parse args for credentials
                username = args[args.index("--username") + 1]
                password = args[args.index("--password") + 1]
                device_id = args[args.index("--device_id") + 1]
                country = "eu"  # default
                
        except (FileNotFoundError, KeyError, StopIteration, IndexError) as ex:
            logger.error("❌ Could not load credentials from .vscode/launch.json: %s", ex)
            logger.error("Please ensure .vscode/launch.json exists with CLI configuration")
            return False

        # Initialize protocol and login
        self.protocol = DreameMowerCloudDevice(
            username=username,
            password=password,
            country=country,
            account_type="dreame",
            device_id=device_id,
        )

        logger.info("🔐 Connecting to Dreame cloud…")
        if not self.protocol._cloud_base.connect():
            logger.error("❌ Cloud connection failed")
            return False

        logger.info("✅ Cloud connection successful")
        return True

    def parse_settings_data(self, settings_raw):
        """Parse and extract key information from SETTINGS data."""
        try:
            # Handle simple string/number values (like SETTINGS.info)
            if isinstance(settings_raw, (str, int)):
                settings_str = str(settings_raw)
                # Check if it's a simple number or info value
                if settings_str.isdigit() or (isinstance(settings_raw, int)):
                    settings_value = int(settings_raw)
                    return {
                        'type': 'info',
                        'value': settings_value,
                        'decoded_flags': self.decode_settings_flags(settings_value)
                    }
                
                # Special handling for SETTINGS.1 which starts with "Height" (obstacleAvoidanceHeight)
                elif settings_str.startswith('"Height"'):
                    logger.info(f"Detected SETTINGS.1 fragment starting with obstacleAvoidanceHeight")
                    # This is a valid JSON fragment from SETTINGS.1
                    # Try to reconstruct it for analysis
                    reconstructed = '{"obstacleAvoidance' + settings_str
                    if reconstructed.endswith('}}}]'):
                        # Try to build a complete JSON structure
                        test_json = '[{"mode":0,"settings":{"0":{' + reconstructed[1:]
                        try:
                            data = json.loads(test_json)
                            logger.info("Successfully reconstructed SETTINGS.1 fragment")
                            
                            # Extract the settings from the reconstructed data
                            results = {}
                            for mode_idx, mode_data in enumerate(data):
                                mode_info = {
                                    'mode': mode_data.get('mode', 'unknown'),
                                    'settings': {}
                                }
                                
                                for setting_id, setting_values in mode_data.get('settings', {}).items():
                                    mode_info['settings'][setting_id] = setting_values
                                
                                results[f'mode_{mode_idx}'] = mode_info
                            
                            return results
                        except json.JSONDecodeError:
                            pass
                    
                    logger.warning("Could not reconstruct SETTINGS.1 fragment")
                    return None
                
                # Check if it's clearly not JSON (doesn't start with [ or {)
                elif not settings_str.strip().startswith(('[', '{')):
                    logger.warning(f"Unrecognized settings format: {settings_str[:50]}...")
                    return None
            
            # Clean up truncated JSON data
            settings_str = str(settings_raw)
            
            # If it doesn't start with '[', it's likely truncated - try to find the beginning
            if not settings_str.startswith('['):
                # Look for the start of a JSON array
                start_pos = settings_str.find('[{')
                if start_pos != -1:
                    settings_str = settings_str[start_pos:]
                else:
                    logger.warning(f"Could not find valid JSON start in: {settings_str[:100]}...")
                    return None
            
            # Try to fix incomplete JSON by finding the last complete object
            if not settings_str.endswith(']'):
                # Find the last complete object
                brace_count = 0
                last_complete = -1
                
                for i, char in enumerate(settings_str):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            last_complete = i
                
                if last_complete != -1:
                    settings_str = settings_str[:last_complete + 1] + ']'
            
            settings_data = json.loads(settings_str)
            
            results = {}
            for mode_idx, mode_data in enumerate(settings_data):
                mode_info = {
                    'mode': mode_data.get('mode', 'unknown'),
                    'settings': {}
                }
                
                for setting_id, setting_values in mode_data.get('settings', {}).items():
                    mode_info['settings'][setting_id] = setting_values
                
                results[f'mode_{mode_idx}'] = mode_info
            
            return results
        except Exception as e:
            logger.error(f"Error parsing settings: {e}")
            return None

    def decode_settings_flags(self, settings_value):
        """Decode settings value as bit flags for mower features."""
        if not isinstance(settings_value, int):
            return {"error": f"Invalid settings value: {settings_value}"}
        
        # Define the bit flag meanings based on analysis
        flag_definitions = {
            0: "Unknown feature 0",
            1: "Unknown feature 1", 
            2: "Rain sensor enabled",
            3: "Theft protection enabled",
            4: "Unknown feature 4",
            5: "Auto return enabled",
            6: "Blade height auto-adjust",
            7: "Path optimization",
            8: "Unknown feature 8",
            9: "Night mode enabled",
            10: "Unknown feature 10",
            11: "Unknown feature 11",
            12: "Unknown feature 12",
            13: "Unknown feature 13",
            14: "Unknown feature 14",
            15: "Unknown feature 15"
        }
        
        # Extract active flags
        active_flags = []
        inactive_flags = []
        
        for bit in range(16):
            flag_name = flag_definitions.get(bit, f"Unknown bit {bit}")
            if settings_value & (1 << bit):
                active_flags.append(f"Bit {bit}: {flag_name}")
            else:
                inactive_flags.append(f"Bit {bit}: {flag_name}")
        
        # Get enabled feature summary
        known_features = {
            2: "Rain Sensor",
            3: "Theft Protection", 
            5: "Auto Return",
            6: "Blade Height Auto-Adjust",
            7: "Path Optimization",
            9: "Night Mode"
        }
        
        enabled_features = []
        for bit, feature_name in known_features.items():
            if settings_value & (1 << bit):
                enabled_features.append(feature_name)
        
        return {
            "binary_representation": f"0b{settings_value:016b}",
            "hexadecimal": f"0x{settings_value:04X}",
            "decimal": settings_value,
            "active_flags": active_flags,
            "inactive_flags": inactive_flags,
            "active_bits": [i for i in range(16) if settings_value & (1 << i)],
            "enabled_features": enabled_features,
            "total_enabled_features": len(enabled_features),
            "total_active_bits": len([i for i in range(16) if settings_value & (1 << i)])
        }

    def parse_schedule_data(self, schedule_raw: Any) -> Dict[str, Any]:
        """Parse and extract schedule information."""
        try:
            # Handle simple string/number values (like SCHEDULE.info)
            if isinstance(schedule_raw, (str, int)) and not (isinstance(schedule_raw, str) and schedule_raw.startswith('{')):
                return {
                    'type': 'info',
                    'value': schedule_raw
                }
            
            # Try to parse as JSON
            if isinstance(schedule_raw, str):
                schedule_data = json.loads(schedule_raw)
            else:
                schedule_data = schedule_raw
                
            return {
                'type': 'schedule',
                'version': schedule_data.get('v', 'unknown'),
                'schedules': schedule_data.get('d', [])
            }
        except Exception as e:
            logger.error(f"Error parsing schedule: {e}")
            return {'type': 'error', 'message': str(e)}

    def display_advanced_features(self, settings_data):
        """Display advanced mowing features in an organized way."""
        print("\n" + "="*80)
        print("🔧 ADVANCED MOWING FEATURES DISCOVERED")
        print("="*80)
        
        # Handle info-type settings
        if settings_data.get('type') == 'info':
            settings_value = settings_data['value']
            print(f"Settings Info: {settings_value}")
            
            # Display decoded flags if available
            if 'decoded_flags' in settings_data:
                flags_info = settings_data['decoded_flags']
                print(f"\n🏷️  FLAG ANALYSIS:")
                print(f"   Binary: {flags_info['binary_representation']}")
                print(f"   Hex: {flags_info['hexadecimal']}")
                print(f"   Active bits: {flags_info['active_bits']}")
                
                print(f"\n✅ ENABLED FEATURES ({flags_info['total_enabled_features']} features):")
                for feature in flags_info['enabled_features']:
                    print(f"   • {feature}")
                
                print(f"\n🔧 DETAILED BIT FLAGS:")
                print(f"   Active flags ({flags_info['total_active_bits']} total):")
                for flag in flags_info['active_flags']:
                    print(f"   ✓ {flag}")
                
                print(f"   Inactive flags:")
                for flag in flags_info['inactive_flags'][:5]:  # Show first 5 to avoid clutter
                    print(f"   ✗ {flag}")
                if len(flags_info['inactive_flags']) > 5:
                    print(f"   ... and {len(flags_info['inactive_flags']) - 5} more inactive flags")
            
            return
        
        for mode_key, mode_info in settings_data.items():
            print(f"\n📋 {mode_key.upper()} (Mode {mode_info['mode']}):")
            print("-" * 50)
            
            for setting_id, settings in mode_info['settings'].items():
                print(f"\n  🎯 Setting Profile {setting_id}:")
                
                # Group features by category
                basic_features = {}
                edge_features = {}
                obstacle_features = {}
                direction_features = {}
                
                for key, value in settings.items():
                    if 'mowing' in key.lower() and 'edge' not in key.lower():
                        basic_features[key] = value
                    elif 'edge' in key.lower():
                        edge_features[key] = value
                    elif 'obstacle' in key.lower():
                        obstacle_features[key] = value
                    elif 'direction' in key.lower():
                        direction_features[key] = value
                    else:
                        basic_features[key] = value
                
                # Display categorized features with explanations
                if basic_features:
                    print("    🌱 Basic Mowing:")
                    for key, value in basic_features.items():
                        explanation = self.get_setting_explanation(key, value)
                        print(f"      • {key}: {value} {explanation}")
                
                if edge_features:
                    print("    🔄 Edge Mowing:")
                    for key, value in edge_features.items():
                        explanation = self.get_setting_explanation(key, value)
                        print(f"      • {key}: {value} {explanation}")
                
                if obstacle_features:
                    print("    🚧 Obstacle Avoidance:")
                    for key, value in obstacle_features.items():
                        explanation = self.get_setting_explanation(key, value)
                        print(f"      • {key}: {value} {explanation}")
                
                if direction_features:
                    print("    🧭 Direction Control:")
                    for key, value in direction_features.items():
                        explanation = self.get_setting_explanation(key, value)
                        print(f"      • {key}: {value} {explanation}")

    def get_setting_explanation(self, key: str, value: Any) -> str:
        """Get detailed explanation of setting values and possible ranges."""
        explanations: Dict[str, Any] = {
            # Basic Mowing Settings
            'version': {
                'description': '(Settings schema version)',
                'range': 'Internal versioning'
            },
            'id': {
                'description': '(Profile identifier)',
                'range': '0-n profiles'
            },
            'efficientMode': {
                0: '(Standard mode)',
                1: '(Efficient mode)',
                'description': '(Mowing efficiency mode)',
                'range': '0=Standard, 1=Efficient'
            },
            'mowingHeight': {
                'description': f'(Blade height: {value}cm)',
                'range': '3-7cm range',
                'note': 'Lower=shorter grass, Higher=longer grass'
            },
            'cutterPosition': {
                0: '(Position mode 0 - possibly center/normal)',
                1: '(Position mode 1 - possibly edge/active)', 
                'description': '(Cutter position/mode)',
                'range': 'Internal setting (not in app UI)',
                'note': 'Could be center/edge position or active/idle state'
            },
            'mowingDirection': {
                'description': f'(Direction angle: {value}°)',
                'range': '0-180° (not cardinal directions)',
                'note': 'Mowing pattern angle preference'
            },
            'mowingDirectionMode': {
                0: '(One direction)',
                1: '(Cross pattern)',
                2: '(Checkerboard pattern)',
                3: '(Random pattern)',
                'description': '(Pattern mode)',
                'range': '0=One direction, 1=Cross, 2=Checkerboard, 3=Random'
            },
            
            # Edge Mowing Settings
            'edgeMowingWalkMode': {
                0: '(Disabled)',
                1: '(Enabled)',
                'description': '(Edge walking mode)',
                'range': '0=Off, 1=On'
            },
            'edgeMowingAuto': {
                0: '(Manual edge mowing)',
                1: '(Automatic edge detection)',
                'description': '(Auto edge detection)',
                'range': '0=Manual, 1=Auto'
            },
            'edgeMowingSafe': {
                0: '(Standard edge mode)',
                1: '(Safe edge mode)',
                'description': '(Safety mode for edges)',
                'range': '0=Standard, 1=Safe'
            },
            'edgeMowingNum': {
                'description': f'(Internal parameter: {value})',
                'range': 'Internal setting (not in app UI)',
                'note': 'Purpose unclear - may be edge algorithm parameter'
            },
            'edgeMowingObstacleAvoidance': {
                0: '(Disabled for edges)',
                1: '(Enabled for edges)',
                'description': '(Obstacle avoidance on edges)',
                'range': '0=Off, 1=On'
            },
            
            # Obstacle Avoidance Settings
            'obstacleAvoidanceEnabled': {
                0: '(Disabled)',
                1: '(Enabled)',
                'description': '(Obstacle detection)',
                'range': '0=Off, 1=On'
            },
            'obstacleAvoidanceHeight': {
                5: '(Detection height: 5cm - High sensitivity)',
                10: '(Detection height: 10cm - Medium-high sensitivity)',
                15: '(Detection height: 15cm - Medium-low sensitivity)',
                20: '(Detection height: 20cm - Low sensitivity)',
                'description': f'(Detection height: {value}cm)',
                'range': '5, 10, 15, or 20cm options',
                'note': 'Minimum obstacle height to detect - lower = more sensitive'
            },
            'obstacleAvoidanceDistance': {
                10: '(Stop distance: 10cm - Close approach)',
                15: '(Stop distance: 15cm - Medium approach)',
                20: '(Stop distance: 20cm - Safe approach)',
                'description': f'(Stop distance: {value}cm)',
                'range': '10, 15, or 20cm options', 
                'note': 'Distance to stop before obstacle - higher = more cautious'
            },
            'obstacleAvoidanceAi': {
                0: '(No AI detection)',
                1: '(Objects only)',
                2: '(Animals only)',
                3: '(Objects + Animals)',
                4: '(People only)',
                5: '(Objects + People)',
                6: '(Animals + People)',
                7: '(Full AI: Objects + Animals + People)',
                'description': f'(AI detection types: {value})',
                'range': '0-7 bit flags (Objects=1, Animals=2, People=4)',
                'note': f'Bit flags: {self.decode_ai_flags(value) if hasattr(self, "decode_ai_flags") else "Objects+Animals+People" if value == 7 else "Custom combination"}'
            }
        }
        
        if key in explanations:
            setting_info = explanations[key]
            
            # Check for specific value explanation
            if value in setting_info:
                return setting_info[value]
            
            # Build general explanation
            parts = []
            if 'description' in setting_info:
                parts.append(setting_info['description'])
            if 'range' in setting_info:
                parts.append(f"({setting_info['range']})")
            if 'note' in setting_info:
                parts.append(f"- {setting_info['note']}")
            
            return ' '.join(parts) if parts else ''
        
        return ''  # No explanation available

    def decode_ai_flags(self, ai_value):
        """Decode AI detection flags."""
        if not isinstance(ai_value, int):
            return "Invalid AI value"
        
        detection_types = []
        if ai_value & 1:  # Bit 0
            detection_types.append("Objects")
        if ai_value & 2:  # Bit 1
            detection_types.append("Animals")
        if ai_value & 4:  # Bit 2
            detection_types.append("People")
        
        if not detection_types:
            return "No detection"
        
        return "+".join(detection_types)

    def parse_map_data(self, map_raw):
        """Parse and extract map coordinate information."""
        try:
            if not map_raw:
                return None
                
            # Clean up escaped JSON strings (multiple levels of escaping)
            raw_str = str(map_raw)
            for _ in range(3):
                raw_str = raw_str.replace('\\"', '"').replace('\"', '"')
            
            # Extract coordinate points using regex pattern from your plot scripts
            points = re.findall(r'\{"x":(-?\d+\.?\d*),"y":(-?\d+\.?\d*)\}', raw_str)
            coords = [(float(x), float(y)) for x, y in points] if points else []
            
            # Extract boundary information if present
            boundary_match = re.search(r'boundary\\?":{\\?"x1\\?":(-?\d+\.?\d*),\\?"y1\\?":(-?\d+\.?\d*),\\?"x2\\?":(-?\d+\.?\d*),\\?"y2\\?":(-?\d+\.?\d*)', raw_str)
            boundary = None
            if boundary_match:
                x1, y1, x2, y2 = map(float, boundary_match.groups())
                boundary = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
            
            # Extract area information if present
            area_match = re.search(r'totalArea\\?":(\d+\.?\d*)', raw_str)
            total_area = float(area_match.group(1)) if area_match else None
            
            # Extract map index if present
            map_index_match = re.search(r'mapIndex\\?":(\d+)', raw_str)
            map_index = int(map_index_match.group(1)) if map_index_match else None
            
            return {
                'coordinates': coords,
                'coordinate_count': len(coords),
                'boundary': boundary,
                'total_area': total_area,
                'map_index': map_index,
                'raw_length': len(raw_str)
            }
            
        except Exception as e:
            logger.error(f"Error parsing map data: {e}")
            return None

    def parse_fbd_ntype_data(self, fbd_raw):
        """Parse FBD_NTYPE (Forbidden Area Type) data."""
        try:
            if isinstance(fbd_raw, str) and fbd_raw.startswith('['):
                # Parse as JSON array
                fbd_data = json.loads(fbd_raw)
                return {
                    'type': 'json_data',
                    'data': fbd_data,
                    'entries': len(fbd_data) if isinstance(fbd_data, list) else 1
                }
            else:
                # Simple value
                return {
                    'type': 'simple_value',
                    'value': fbd_raw
                }
        except Exception as e:
            logger.error(f"Error parsing FBD_NTYPE data: {e}")
            return None

    def parse_ota_info_data(self, ota_raw):
        """Parse OTA_INFO (Over-The-Air update info) data."""
        try:
            if isinstance(ota_raw, str) and ota_raw.startswith('['):
                # Parse as JSON array
                ota_data = json.loads(ota_raw)
                return {
                    'type': 'json_data',
                    'data': ota_data,
                    'entries': len(ota_data) if isinstance(ota_data, list) else 1
                }
            else:
                # Simple value (like version info)
                return {
                    'type': 'info_value',
                    'value': ota_raw
                }
        except Exception as e:
            logger.error(f"Error parsing OTA_INFO data: {e}")
            return None

    def display_map_info(self, map_data, map_key):
        """Display map information."""
        if not map_data:
            print(f"  ❌ {map_key}: No valid data")
            return
            
        print(f"\n📍 {map_key}:")
        print(f"  • Coordinates: {map_data['coordinate_count']} points")
        print(f"  • Raw data length: {map_data['raw_length']} characters")
        
        if map_data['boundary']:
            b = map_data['boundary']
            width = abs(b['x2'] - b['x1'])
            height = abs(b['y2'] - b['y1'])
            print(f"  • Boundary: ({b['x1']}, {b['y1']}) to ({b['x2']}, {b['y2']})")
            print(f"  • Dimensions: {width} x {height} units")
            
        if map_data['total_area'] is not None:
            print(f"  • Total Area: {map_data['total_area']} sq units")
            
        if map_data['map_index'] is not None:
            print(f"  • Map Index: {map_data['map_index']}")
            
        if map_data['coordinate_count'] > 0:
            coords = map_data['coordinates']
            # Show first few and last few coordinates
            if len(coords) <= 6:
                print(f"  • Sample coords: {coords}")
            else:
                print(f"  • First 3 coords: {coords[:3]}")
                print(f"  • Last 3 coords: {coords[-3:]}")

    def display_fbd_ntype_info(self, fbd_data, fbd_key):
        """Display FBD_NTYPE (Forbidden Area Type) information."""
        if not fbd_data:
            print(f"  ❌ {fbd_key}: No valid data")
            return
            
        print(f"\n🚫 {fbd_key}:")
        if fbd_data['type'] == 'json_data':
            print(f"  • Type: JSON data with {fbd_data['entries']} entries")
            print(f"  • Data: {fbd_data['data']}")
            
            # Try to interpret the data structure
            if isinstance(fbd_data['data'], list):
                for idx, entry in enumerate(fbd_data['data']):
                    print(f"    Entry {idx}: {entry}")
        else:
            print(f"  • Type: Simple value")
            print(f"  • Value: {fbd_data['value']}")

    def display_ota_info(self, ota_data, ota_key):
        """Display OTA_INFO (Over-The-Air update info) information."""
        if not ota_data:
            print(f"  ❌ {ota_key}: No valid data")
            return
            
        print(f"\n🔄 {ota_key}:")
        if ota_data['type'] == 'json_data':
            print(f"  • Type: JSON data with {ota_data['entries']} entries")
            print(f"  • Data: {ota_data['data']}")
            
            # Try to interpret as version/update info
            if isinstance(ota_data['data'], list) and len(ota_data['data']) >= 2:
                print(f"    Version info: {ota_data['data'][0]}, {ota_data['data'][1]}")
        else:
            print(f"  • Type: Version/Info value")
            print(f"  • Value: {ota_data['value']}")

    def display_schedule_info(self, schedule_data):
        """Display schedule information."""
        print("\n" + "="*80)
        print("📅 SCHEDULE CONFIGURATION")
        print("="*80)
        
        if schedule_data['type'] == 'info':
            print(f"Schedule Info: {schedule_data['value']}")
        else:
            print(f"Version: {schedule_data['version']}")
            print(f"Number of schedules: {len(schedule_data['schedules'])}")
            
            for idx, schedule in enumerate(schedule_data['schedules']):
                day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
                day_name = day_names[schedule[0]] if 0 <= schedule[0] < 7 else f"Day {schedule[0]}"
                
                print(f"\n📆 Schedule {idx + 1} ({day_name}):")
                print(f"  • Day: {schedule[0]} ({day_name})")
                print(f"  • Enabled: {'✅ Yes' if schedule[1] else '❌ No'}")
                print(f"  • Name: '{schedule[2]}'")
                
                # Decode the schedule data
                encoded_data = schedule[3]
                print(f"  • Encoded Data: {encoded_data}")
                
                if encoded_data:
                    decoded = self.decode_schedule_data(encoded_data)
                    if isinstance(decoded, dict):
                        print(f"  📋 Decoded Schedule:")
                        print(f"    - Format: {decoded.get('format', 'Unknown')}")
                        print(f"    - Raw bytes ({decoded['length']}): {decoded['raw_bytes']}")
                        
                        if decoded.get('time_periods'):
                            print(f"    - 🕐 Time Periods:")
                            for period in decoded['time_periods']:
                                if 'error' in period:
                                    print(f"      Period {period.get('period', '?')}: ❌ {period['error']}")
                                else:
                                    print(f"      � Period {period['period']}:")
                                    print(f"        • ID: {period['identifier']}")
                                    print(f"        • Time bytes: {period['time_bytes']}")
                                    print(f"        • Possible interpretations:")
                                    for interp in period['interpretations']:
                                        print(f"          - {interp}")
                                    print(f"        • Raw: {period['raw_hex']}")
                        
                        elif decoded.get('raw_interpretation'):
                            print(f"    - 🕐 Time Analysis:")
                            for interp in decoded['raw_interpretation']:
                                print(f"      • {interp}")
                        
                        if decoded.get('parse_error'):
                            print(f"    - ⚠️ Parse error: {decoded['parse_error']}")
                    else:
                        print(f"  📋 Decode result: {decoded}")

    def analyze_comprehensive_data(self):
        """Retrieve and analyze comprehensive device data with all data types."""
        try:
            print("\n🧪 Retrieving comprehensive device data...")
            
            # Check device state
            if not self.protocol or not self.protocol._cloud_base:
                print("❌ Device protocol or cloud base not available")
                return
            
            print(f"Cloud base connected: {self.protocol._cloud_base.connected}")
            print(f"API strings initialized: {self.protocol._cloud_base._api_strings is not None}")
            
            # Use REST API getDeviceData endpoint to retrieve all hierarchical device data
            # This replaces the legacy prop.s_ai_config approach with current REST API call
            print("🎯 Calling REST API getDeviceData endpoint...")
            s = self.protocol._cloud_base._api_strings
            api_response = self.protocol._cloud_base._api_call(
                f"{s[23]}/{s[26]}/{s[44]}",
                {"did": self.protocol._device_id}
            )
            
            if api_response is None or "data" not in api_response:
                print("❌ No data returned from getDeviceData endpoint")
                return
                
            data = api_response["data"]
            print(f"Response type: {type(data)}")
            print(f"Response keys: {list(data.keys())[:10] if isinstance(data, dict) else 'Not a dict'}...")
            
            if not data:
                print("❌ No data returned")
                return
                
            # The data comes back directly as key-value pairs from getDeviceData endpoint
            comprehensive_data = data
            print(f"✅ Retrieved {len(comprehensive_data)} data items")
            
            # Dump raw device data to JSON file
            self.dump_device_data_to_json(comprehensive_data)
            
            # Categorize and analyze all data types
            settings_data = {}
            schedule_data = {}
            map_data = {}
            fbd_ntype_data = {}
            ota_info_data = {}
            other_data = {}
            
            for key, value in comprehensive_data.items():
                if key.startswith("SETTINGS"):
                    settings_data[key] = value
                elif key.startswith("SCHEDULE"):
                    schedule_data[key] = value
                elif key.startswith("MAP"):
                    map_data[key] = value
                elif key.startswith("FBD_NTYPE"):
                    fbd_ntype_data[key] = value
                elif key.startswith("OTA_INFO"):
                    ota_info_data[key] = value
                else:
                    other_data[key] = value
            
            print(f"\n📦 Data categorization:")
            print(f"  • SETTINGS: {len(settings_data)} items")
            print(f"  • SCHEDULE: {len(schedule_data)} items")  
            print(f"  • MAP: {len(map_data)} items")
            print(f"  • FBD_NTYPE: {len(fbd_ntype_data)} items")
            print(f"  • OTA_INFO: {len(ota_info_data)} items")
            print(f"  • Other: {len(other_data)} items")
            
            # Analyze SETTINGS data
            if settings_data:
                print("\n" + "="*50)
                print("⚙️  SETTINGS ANALYSIS")
                print("="*50)
                
                for key, value in settings_data.items():
                    print(f"\n🔍 Analyzing {key}...")
                    parsed = self.parse_settings_data(value)
                    if parsed:
                        self.display_advanced_features(parsed)
                    else:
                        print(f"  ❌ {key}: Could not parse settings data")
                        print(f"      Raw data: {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}")
            
            # Analyze SCHEDULE data  
            if schedule_data:
                print("\n" + "="*50)
                print("📅 SCHEDULE ANALYSIS")
                print("="*50)
                
                for key, value in schedule_data.items():
                    parsed = self.parse_schedule_data(value)
                    self.display_schedule_info(parsed)
            
            # Analyze MAP data
            if map_data:
                print("\n" + "="*50)
                print("�️  MAP ANALYSIS")
                print("="*50)
                print(f"Found {len(map_data)} MAP entries - analyzing coordinate and boundary data...")
                
                for key, value in map_data.items():
                    parsed = self.parse_map_data(value)
                    self.display_map_info(parsed, key)
            
            # Analyze FBD_NTYPE data
            if fbd_ntype_data:
                print("\n" + "="*50)
                print("� FORBIDDEN AREA TYPE ANALYSIS")
                print("="*50)
                
                for key, value in fbd_ntype_data.items():
                    parsed = self.parse_fbd_ntype_data(value)
                    self.display_fbd_ntype_info(parsed, key)
            
            # Analyze OTA_INFO data
            if ota_info_data:
                print("\n" + "="*50)
                print("🔄 OTA UPDATE INFO ANALYSIS")
                print("="*50)
                
                for key, value in ota_info_data.items():
                    parsed = self.parse_ota_info_data(value)
                    self.display_ota_info(parsed, key)
            
            # Show any other unrecognized data
            if other_data:
                print("\n" + "="*50)
                print("❓ OTHER/UNRECOGNIZED DATA")
                print("="*50)
                
                for key, value in other_data.items():
                    print(f"\n🔍 {key}:")
                    print(f"  • Value: {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}")
                    print(f"  • Type: {type(value).__name__}")
            
            print("\n" + "="*80)
            print("✅ COMPREHENSIVE ANALYSIS COMPLETE")
            print("="*80)
            print(f"📊 Total entries analyzed: {len(comprehensive_data)}")
            print(f"⚙️  Settings: {len(settings_data)} | 📅 Schedules: {len(schedule_data)}")
            print(f"🗺️  Maps: {len(map_data)} | 🚫 FBD Types: {len(fbd_ntype_data)} | 🔄 OTA Info: {len(ota_info_data)}")
                
        except Exception as e:
            logger.error(f"Error analyzing comprehensive data: {e}")
            import traceback
            traceback.print_exc()
                
        except Exception as e:
            logger.error(f"Error analyzing comprehensive data: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Main execution method."""
        try:
            if not self.connect_to_device():
                return
            
            self.analyze_comprehensive_data()
            
        except Exception as e:
            logger.error(f"Error in main execution: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.protocol:
                try:
                    self.protocol.disconnect()
                except Exception as e:
                    logger.warning(f"Error during disconnect: {e}")

def main():
    analyzer = DeviceDataAnalyzer()
    analyzer.run()

if __name__ == "__main__":
    main()
