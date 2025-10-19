#!/usr/bin/env python3
"""
Real-time Dreame mower monitor.

Features:
 1. Poll REST get_properties for all known production properties + additional discovery properties every N seconds (default 120).
 2. Listen to MQTT push messages simultaneously.
 3. Automatically download mission data files when mission completion event (4:1) is received.
 4. Persist all captured data into per-run directory: dev/logs/<TIMESTAMP>/

Directory layout (per run):
    dev/logs/<TS>/rest_api/<siid>_<piid>.jsonl
        JSON Lines file (one JSON object per line) accumulating timestamped samples for that property.

    dev/logs/<TS>/mqtt/properties_changed/<siid>_<piid>.jsonl
    dev/logs/<TS>/mqtt/event_occured/<siid>_<eiid>.jsonl
    dev/logs/<TS>/mqtt/props/<key>.jsonl
    dev/logs/<TS>/mqtt/unknown/<method>.jsonl
    dev/logs/<TS>/mqtt/mission_data_downloads.jsonl
        Each file is a JSON Lines file (one JSON object per line), optimized for append.
    
    dev/logs/<TS>/mission_data/<file_path>
        Downloaded mission data files with preserved hierarchical structure.

Properties polled:
 - All production properties from custom_components/dreame_mower/dreame/const.py
 - Additional discovery properties: 1:2, 1:3, 1:5 (serial number)

Notes:
 - This script reuses production PropertyIdentifier objects for consistency.
 - No adaptive probing - focuses on stable periodic sampling of known properties.
 - Mission data files are automatically downloaded when event 4:1 occurs.

CLI Examples:
  .venv/bin/python dev/realtime_monitor.py
  .venv/bin/python dev/realtime_monitor.py --interval-seconds 90
  .venv/bin/python dev/realtime_monitor.py --duration-minutes 30
  .venv/bin/python dev/realtime_monitor.py --no-mqtt
  .venv/bin/python dev/realtime_monitor.py --no-rest
  .venv/bin/python dev/realtime_monitor.py --once-rest --no-mqtt

Exit with Ctrl+C.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime

# Ensure repo root importable (same pattern as other dev scripts)
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from custom_components.dreame_mower.dreame.cloud.cloud_device import (  # noqa: E402
    DreameMowerCloudDevice,
)
from custom_components.dreame_mower.dreame.const import (  # noqa: E402
    PROPERTY_1_1,
    POSE_COVERAGE_PROPERTY,
    SERVICE1_PROPERTY_50,
    SERVICE1_PROPERTY_51,
    SERVICE1_COMPLETION_FLAG_PROPERTY,
    BLUETOOTH_PROPERTY,
    STATUS_PROPERTY,
    DEVICE_CODE_PROPERTY,
    SCHEDULING_TASK_PROPERTY,
    SCHEDULING_DND_PROPERTY,
    SCHEDULING_SUMMARY_PROPERTY,
    MOWER_CONTROL_STATUS_PROPERTY,
    POWER_STATE_PROPERTY,
    SERVICE2_PROPERTY_60,
    SERVICE2_PROPERTY_62,
    SERVICE2_PROPERTY_64,
    SERVICE2_PROPERTY_65,
    BATTERY_PROPERTY,
    CHARGING_STATUS_PROPERTY,
    TASK_STATUS_PROPERTY,
    SERVICE5_PROPERTY_105,
    BMS_PHASE_PROPERTY,
    SERVICE5_ENERGY_INDEX_PROPERTY,
    SERVICE5_PROPERTY_108,
)

log = logging.getLogger("realtime_monitor")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# File extension for logs (use .jsonl for JSON Lines)
EXT = ".jsonl"

# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    # Regular colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    # Background colors
    BG_BLACK = "\033[40m"
    BG_BLUE = "\033[44m"

# --- Known REST properties (from production const.py + additional discovery properties) ---
# Build from production PropertyIdentifier objects
PRODUCTION_PROPERTIES = [
    PROPERTY_1_1,
    POSE_COVERAGE_PROPERTY,
    SERVICE1_PROPERTY_50,
    SERVICE1_PROPERTY_51,
    SERVICE1_COMPLETION_FLAG_PROPERTY,
    BLUETOOTH_PROPERTY,
    STATUS_PROPERTY,
    DEVICE_CODE_PROPERTY,
    SCHEDULING_TASK_PROPERTY,
    SCHEDULING_DND_PROPERTY,
    SCHEDULING_SUMMARY_PROPERTY,
    MOWER_CONTROL_STATUS_PROPERTY,
    POWER_STATE_PROPERTY,
    SERVICE2_PROPERTY_60,
    SERVICE2_PROPERTY_62,
    SERVICE2_PROPERTY_64,
    SERVICE2_PROPERTY_65,
    BATTERY_PROPERTY,
    CHARGING_STATUS_PROPERTY,
    TASK_STATUS_PROPERTY,
    SERVICE5_PROPERTY_105,
    BMS_PHASE_PROPERTY,
    SERVICE5_ENERGY_INDEX_PROPERTY,
    SERVICE5_PROPERTY_108,
]

# Additional properties for discovery (not yet in production)
ADDITIONAL_PROPERTIES = [
    (1, 2),   # CAPABILITY_FLAG_A (not in production)
    (1, 3),   # CAPABILITY_FLAG_B (not in production)
    (1, 5),   # SERIAL_NUMBER (useful for identification)
]

# Combine all properties for polling
KNOWN_PROPERTY_PULL: List[Tuple[int, int]] = []
KNOWN_PROPERTY_NAMES: Dict[Tuple[int, int], str] = {}

# Add production properties
for prop in PRODUCTION_PROPERTIES:
    KNOWN_PROPERTY_PULL.append((prop.siid, prop.piid))
    KNOWN_PROPERTY_NAMES[(prop.siid, prop.piid)] = prop.name

# Add additional discovery properties
for siid, piid in ADDITIONAL_PROPERTIES:
    KNOWN_PROPERTY_PULL.append((siid, piid))
    if (siid, piid) == (1, 2):
        KNOWN_PROPERTY_NAMES[(siid, piid)] = "capability_flag_a"
    elif (siid, piid) == (1, 3):
        KNOWN_PROPERTY_NAMES[(siid, piid)] = "capability_flag_b"
    elif (siid, piid) == (1, 5):
        KNOWN_PROPERTY_NAMES[(siid, piid)] = "serial_number"

# --- Credential loading (copied logic style from probe_rest_properties) ---

def _load_creds_from_launch() -> Dict[str, str]:
    launch_json_path = ROOT_DIR / ".vscode" / "launch.json"
    with open(launch_json_path, "r", encoding="utf-8") as f:
        launch_config = json.load(f)
    configs = launch_config.get("configurations", [])
    # choose first config containing 'CLI' else fallback to first
    debug_config = next((c for c in configs if "CLI" in c.get("name", "")), configs[0] if configs else None)
    if not debug_config:
        raise RuntimeError("No configurations in launch.json")
    args = debug_config.get("args", [])

    def get_arg(flag: str, default: str = "") -> str:
        return args[args.index(flag) + 1] if flag in args else default

    username = get_arg("--username")
    password = get_arg("--password")
    device_id = get_arg("--device_id")
    country = get_arg("--country", "eu") or "eu"
    if not username or not password or not device_id:
        raise RuntimeError("Missing required credentials: --username --password --device_id in launch.json args")
    return {"username": username, "password": password, "device_id": device_id, "country": country}

# --- File writing helpers ---
class JsonlFile:
    """Append-only JSON Lines writer. Thread-safe.

    Each call to `append` writes a single JSON object as one line (newline-terminated).
    This is resilient for long-running logging and efficient on-disk.
    """
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, obj: Any):
        line = json.dumps(obj, ensure_ascii=False)
        with self._lock:
            # Open in append mode and write the single line
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

# Manager to lazily create file objects per key
class FileStoreManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._files: Dict[str, JsonlFile] = {}
        self._lock = threading.Lock()

    def get(self, rel_path: str) -> JsonlFile:
        with self._lock:
            if rel_path not in self._files:
                path = self.base_dir / rel_path
                self._files[rel_path] = JsonlFile(path)
            return self._files[rel_path]

# --- Monitor class ---
class RealtimeMonitor:
    def __init__(
        self,
        interval_seconds: int = 120,
        duration_minutes: float | None = None,
        log_root: Path | None = None,
        enable_rest: bool = True,
        enable_mqtt: bool = True,
        once_rest: bool = False,
        status_interval: int = 1,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.duration_minutes = duration_minutes
        self.enable_rest = enable_rest
        self.enable_mqtt = enable_mqtt
        self.once_rest = once_rest
        self.stop_event = threading.Event()
        # human-readable start timestamp for log dir
        self.start_ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        self.log_root = log_root or (ROOT_DIR / "dev" / "logs" / self.start_ts)
        self.rest_dir = self.log_root / "rest_api"
        self.mqtt_dir = self.log_root / "mqtt"
        self._creds: Dict[str, str] | None = None
        self._device: DreameMowerCloudDevice | None = None
        self._rest_thread: threading.Thread | None = None
        self._connected_once = False
        self._filestore = FileStoreManager(self.log_root)
        self._start_time = 0.0
        # Runtime counters and status
        self._rest_poll_count = 0
        self._rest_sample_count = 0
        self._mqtt_message_count = 0
        self._status_interval = status_interval  # seconds (can be overridden by CLI)
        self._status_thread: threading.Thread | None = None
        # Keep track of recent MQTT messages for display
        self._recent_mqtt_messages: deque[str] = deque(maxlen=5)
        self._mqtt_lock = threading.Lock()

    # --- Setup & connection ---
    def load_creds(self):
        if not self._creds:
            self._creds = _load_creds_from_launch()
            log.info("Loaded credentials for device %s", self._creds["device_id"])
        # return credentials for callers
        return self._creds

    def connect(self):
        creds = self.load_creds()
        self._device = DreameMowerCloudDevice(
            username=creds["username"],
            password=creds["password"],
            country=creds["country"],
            account_type="dreame",
            device_id=creds["device_id"],
        )
        # Ensure cloud base session for REST even if MQTT disabled
        log.info("Connecting to cloud…")
        if not self._device._cloud_base.connect():
            raise RuntimeError("Cloud connection failed")
        log.info("Cloud connected")
        if self.enable_mqtt:
            log.info("Establishing MQTT connection…")
            ok = self._device.connect(
                message_callback=self._on_mqtt_message,
                connected_callback=lambda: log.info("MQTT connected"),
                disconnected_callback=lambda: log.warning("MQTT disconnected"),
            )
            if not ok:
                log.warning("MQTT connect returned False")
        self._connected_once = True

    # --- REST polling ---
    def _rest_poll_loop(self):
        assert self._device is not None
        log.info("REST polling thread started (interval=%ds, properties=%d)", self.interval_seconds, len(KNOWN_PROPERTY_PULL))
        while not self.stop_event.is_set():
            started = time.time()
            self.poll_once()
            self._rest_poll_count += 1
            if self.once_rest:
                log.info("--once-rest specified; stopping after single poll")
                self.stop_event.set()
                break
            # Sleep remaining interval
            elapsed = time.time() - started
            remaining = max(0.0, self.interval_seconds - elapsed)
            if self.stop_event.wait(remaining):
                break
        log.info("REST polling thread exiting")

    def poll_once(self):
        if not self.enable_rest:
            return
        if not self._device:
            return
        params = [{"siid": s, "piid": p} for (s, p) in KNOWN_PROPERTY_PULL]
        ts = datetime.now().astimezone().isoformat()
        try:
            result_list = self._device.get_properties(params)
        except Exception as e:
            log.error("get_properties batch failed: %s", e)
            return
        if not isinstance(result_list, list):
            log.warning("Unexpected get_properties result shape: %r", result_list)
            return
        # Index results by (siid,piid)
        for item in result_list:
            try:
                siid = int(item.get("siid"))
                piid = int(item.get("piid"))
                code = int(item.get("code", -1))
            except Exception:
                continue
            key = f"rest_api/{siid}_{piid}{EXT}"
            value = item.get("value") if code == 0 else None
            sample = {
                "timestamp": ts,
                "siid": siid,
                "piid": piid,
                "code": code,
                **({"value": value} if code == 0 else {"error": item.get("description") or item.get("message") or "non-zero"}),
                "name": KNOWN_PROPERTY_NAMES.get((siid, piid)),
            }
            self._filestore.get(key).append(sample)
            self._rest_sample_count += 1

    # --- MQTT handling ---
    def _on_mqtt_message(self, data: Dict[str, Any]):
        method = data.get("method", "unknown")
        ts = datetime.now().astimezone().isoformat()
        # count message
        try:
            self._mqtt_message_count += 1
        except Exception:
            pass
        
        # Create human-readable message summary for display
        msg_summary = self._format_mqtt_message_summary(method, data)
        with self._mqtt_lock:
            self._recent_mqtt_messages.append(msg_summary)
        if method == "properties_changed" and isinstance(data.get("params"), list):
            for param in data["params"]:
                if not isinstance(param, dict):
                    continue
                if "siid" in param and "piid" in param:
                    try:
                        siid = int(param["siid"])
                        piid = int(param["piid"])
                    except Exception:
                        continue
                    key = f"mqtt/properties_changed/{siid}_{piid}{EXT}"
                    sample = {"timestamp": ts, "raw": param}
                    self._filestore.get(key).append(sample)
        elif method == "event_occured" and isinstance(data.get("params"), dict):
            params = data["params"]
            siid = params.get("siid")
            eiid = params.get("eiid")
            if siid is not None and eiid is not None:
                key = f"mqtt/event_occured/{siid}_{eiid}{EXT}"
                sample = {"timestamp": ts, "raw": params}
                self._filestore.get(key).append(sample)
                # Handle mission completion event (4:1) - download data file if available
                if siid == 4 and eiid == 1:
                    self._handle_mission_completion_event(params, ts)
        elif method == "props" and isinstance(data.get("params"), dict):
            params = data["params"]
            for k, v in params.items():
                safe_key = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(k))
                key = f"mqtt/props/{safe_key}{EXT}"
                sample = {"timestamp": ts, "value": v, "raw": {k: v}}
                self._filestore.get(key).append(sample)
        else:
            # Unknown method: store whole message in its own file keyed by method
            classifier = method or "unknown"
            safe_method = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in classifier)
            key = f"mqtt/unknown/{safe_method}{EXT}"
            sample = {"timestamp": ts, "raw": data}
            self._filestore.get(key).append(sample)
        # Minimal inline progress summary
        if method != "properties_changed":
            log.debug("MQTT message handled method=%s", method)

    def _format_mqtt_message_summary(self, method: str, data: Dict[str, Any]) -> str:
        """Format MQTT message for compact display."""
        now = datetime.now().astimezone().strftime("%H:%M:%S")
        
        if method == "properties_changed":
            params = data.get("params", [])
            if isinstance(params, list) and params:
                # Show first property change
                first = params[0]
                if isinstance(first, dict) and "siid" in first and "piid" in first:
                    siid, piid = first["siid"], first["piid"]
                    value = first.get("value", "?")
                    name = KNOWN_PROPERTY_NAMES.get((siid, piid), f"{siid}:{piid}")
                    suffix = f" +{len(params)-1}" if len(params) > 1 else ""
                    return f"{now} property_change: {name}={value}{suffix}"
            return f"{now} properties_changed: {len(params)} props"
        
        elif method == "event_occured":
            params = data.get("params", {})
            if isinstance(params, dict):
                siid = params.get("siid")
                eiid = params.get("eiid")
                if siid == 4 and eiid == 1:
                    return f"{now} event: Mission completed (4:1)"
                return f"{now} event: {siid}:{eiid}"
            return f"{now} event_occured"
        
        elif method == "props":
            params = data.get("params", {})
            if isinstance(params, dict):
                keys = list(params.keys())
                if keys:
                    first_key = keys[0]
                    first_val = params[first_key]
                    suffix = f" +{len(keys)-1}" if len(keys) > 1 else ""
                    return f"{now} props: {first_key}={first_val}{suffix}"
            return f"{now} props update"
        
        else:
            return f"{now} {method}"

    def _handle_mission_completion_event(self, params: Dict[str, Any], ts: str):
        """Handle mission completion event (4:1) and download mission data file if available."""
        try:
            arguments = params.get("arguments", [])
            if not isinstance(arguments, list):
                return
            
            # Extract data file path from event arguments (piid 9)
            data_file_path = None
            for arg in arguments:
                if isinstance(arg, dict) and arg.get("piid") == 9:
                    data_file_path = arg.get("value")
                    break
            
            if not data_file_path or not isinstance(data_file_path, str) or data_file_path == "":
                log.debug("Mission completion event has no data file path")
                return
            
            if not self._device:
                log.warning("Device not initialized, cannot download mission data")
                return
            
            log.info("Mission completion event detected, downloading: %s", data_file_path)
            
            # Get download URL from cloud API
            download_url = self._device.get_file_download_url(data_file_path)
            if not download_url:
                log.warning("Failed to get download URL for: %s", data_file_path)
                return
            
            # Download the file
            import requests
            resp = requests.get(download_url, timeout=30)
            resp.raise_for_status()
            content = resp.text
            
            # Save to mission_data directory inside log_root
            mission_data_dir = self.log_root / "mission_data"
            mission_data_dir.mkdir(exist_ok=True)
            
            # Preserve the hierarchical path structure
            save_path = mission_data_dir / data_file_path
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with save_path.open("w", encoding="utf-8") as f:
                f.write(content)
            
            log.info("Mission data file downloaded successfully: %s", save_path)
            
            # Also log the download event
            key = f"mqtt/mission_data_downloads{EXT}"
            sample = {
                "timestamp": ts,
                "file_path": data_file_path,
                "download_url": download_url,
                "saved_to": str(save_path),
                "size_bytes": len(content)
            }
            self._filestore.get(key).append(sample)
            
        except Exception as ex:
            log.error("Failed to download mission data file: %s", ex)

    def _status_worker(self):
        """Background thread printing multi-line status periodically."""
        # ANSI codes for cursor control
        CURSOR_UP = "\033[{}A"  # Move cursor up N lines
        CLEAR_LINE = "\033[2K"  # Clear entire line
        CURSOR_START = "\r"     # Move cursor to start of line
        
        prev_lines = 0
        first_display = True
        
        while not self.stop_event.wait(self._status_interval):
            uptime = int(time.time() - self._start_time) if self._start_time else 0
            hrs, rem = divmod(uptime, 3600)
            mins, secs = divmod(rem, 60)
            
            # Build status line with colors
            status_line = (
                f"{Colors.BRIGHT_CYAN}{Colors.BOLD}Alive{Colors.RESET} "
                f"{Colors.BRIGHT_WHITE}{hrs:02d}:{mins:02d}:{secs:02d}{Colors.RESET} | "
                f"{Colors.BRIGHT_GREEN}REST polls{Colors.RESET}={Colors.GREEN}{self._rest_poll_count}{Colors.RESET} | "
                f"{Colors.BRIGHT_MAGENTA}MQTT msgs{Colors.RESET}={Colors.MAGENTA}{self._mqtt_message_count}{Colors.RESET}"
            )
            
            # Get recent MQTT messages
            with self._mqtt_lock:
                recent_msgs = list(self._recent_mqtt_messages)
            
            # Build output lines
            lines = [status_line]
            if recent_msgs:
                lines.append(f"{Colors.BRIGHT_YELLOW}Recent MQTT:{Colors.RESET}")
                for msg in recent_msgs:
                    lines.append(f"  {Colors.CYAN}→{Colors.RESET} {msg}")
            
            # Move cursor up to overwrite previous output (except on first display)
            if not first_display and prev_lines > 0:
                print(CURSOR_UP.format(prev_lines), end="")
            
            # Clear and print each line
            for line in lines:
                print(CLEAR_LINE + CURSOR_START + line)
            
            # If new output has fewer lines, clear the remaining old lines
            if len(lines) < prev_lines:
                for _ in range(prev_lines - len(lines)):
                    print(CLEAR_LINE)
            
            prev_lines = len(lines)
            first_display = False
        
        # ensure terminal moves to next line when stopping
        print()

    # --- Lifecycle ---
    def start(self):
        if not self._connected_once:
            self.connect()
        self._start_time = time.time()
        if self.enable_rest:
            self._rest_thread = threading.Thread(target=self._rest_poll_loop, daemon=True)
            self._rest_thread.start()
        # Start status thread
        if self._status_thread is None:
            self._status_thread = threading.Thread(target=self._status_worker, daemon=True)
            self._status_thread.start()
        log.info("Logging directory: %s", self.log_root)

    def run_forever(self):
        self.start()
        try:
            while not self.stop_event.is_set():
                if self.duration_minutes is not None:
                    elapsed = time.time() - self._start_time
                    if elapsed >= self.duration_minutes * 60:
                        log.info("Duration reached (%.1f min). Stopping.", elapsed / 60.0)
                        break
                time.sleep(1.0)
        except KeyboardInterrupt:
            log.info("Interrupted by user")
        finally:
            self.stop()

    def stop(self):
        self.stop_event.set()
        if self._rest_thread and self._rest_thread.is_alive():
            self._rest_thread.join(timeout=5)
        if self._device:
            try:
                self._device.disconnect()
            except Exception:
                pass
        log.info("Monitor stopped")

# --- CLI ---

def parse_args():
    p = argparse.ArgumentParser(description="Realtime monitor (REST polling + MQTT logging + mission data download)")
    p.add_argument("--interval-seconds", type=int, default=120, help="REST polling interval (default 120)")
    p.add_argument("--duration-minutes", type=float, default=None, help="Optional total runtime; omit for infinite")
    p.add_argument("--log-root", default=None, help="Optional override for log root directory (default dev/logs/<TS>)")
    p.add_argument("--no-rest", action="store_true", help="Disable REST polling")
    p.add_argument("--no-mqtt", action="store_true", help="Disable MQTT subscription")
    p.add_argument("--once-rest", action="store_true", help="Perform exactly one REST poll then exit (implies no duration loop unless MQTT enabled)")
    p.add_argument("--status-interval", type=int, default=1, help="Seconds between inline status updates (default 1)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    log_root = Path(args.log_root) if args.log_root else None
    monitor = RealtimeMonitor(
        interval_seconds=args.interval_seconds,
        duration_minutes=None if args.once_rest and args.no_mqtt else args.duration_minutes,
        log_root=log_root,
        enable_rest=(not args.no_rest),
        enable_mqtt=(not args.no_mqtt),
        once_rest=args.once_rest,
        status_interval=args.status_interval,
    )
    monitor.run_forever()
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
