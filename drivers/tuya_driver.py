"""
Local Wi-Fi Tuya / Havells Bulb Driver for Async.
Controls Havells Smart Bulbs (Tuya protocol 3.3/3.4) directly over LAN port 6668
with zero cloud delay, non-blocking background queue, active health check watchdog,
auto-reconnect recovery, and dry-run preview fallback.
"""

import time
import logging
import threading
from typing import Optional, Tuple
import tinytuya

logger = logging.getLogger("Async.TuyaDriver")

class HavellsLocalBulb:
    def __init__(
        self,
        device_id: str,
        ip_address: str,
        local_key: str = "",
        version: float = 3.3,
        min_interval: float = 0.05 # ~20 state changes/sec max
    ):
        self.device_id = device_id
        self.ip_address = ip_address
        self.local_key = local_key
        self.version = version
        self.min_interval = min_interval

        self.device: Optional[tinytuya.BulbDevice] = None
        self.is_connected: bool = False
        self.dry_run: bool = not bool(local_key and len(local_key) == 16)

        # Health & Telemetry
        self.ping_ms: float = 0.0
        self.last_health_check: float = 0.0
        self.consecutive_errors: int = 0
        self.last_send_time: float = 0.0
        self.last_hsv: Tuple[float, float, float] = (0.0, 0.0, 0.0)

        # Threading for non-blocking I/O and health watchdog
        self._target_hsv: Optional[Tuple[float, float, float]] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        if not self.dry_run:
            self._connect()
            self._start_worker()
        else:
            logger.info("TuyaDriver initialized in DRY-RUN mode (waiting for 16-char local_key).")

    def _connect(self) -> bool:
        """Initializes persistent socket to bulb."""
        try:
            if self.device:
                try:
                    self.device._check_socket_close(force=True)
                except Exception:
                    pass

            self.device = tinytuya.BulbDevice(
                dev_id=self.device_id,
                address=self.ip_address,
                local_key=self.local_key,
                version=self.version
            )
            self.device.set_socketPersistent(True) # Keep socket open for high throughput
            self.device.set_socketTimeout(1.5) # Fail fast if socket drops

            # Ensure bulb is powered on and in colour mode
            t0 = time.time()
            self.device.set_multiple_values({"20": True, "21": "colour"}, nowait=True)
            self.ping_ms = round((time.time() - t0) * 1000, 1)

            self.is_connected = True
            self.consecutive_errors = 0
            self.last_health_check = time.time()
            logger.info(f"Connected to Havells bulb at {self.ip_address}:6668 ({self.ping_ms}ms)")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to bulb: {e}")
            self.is_connected = False
            return False

    def _start_worker(self):
        """Starts background worker thread for asynchronous frame dispatch & health checks."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._worker_loop, name="TuyaBulbWorker", daemon=True)
            self._worker_thread.start()

    def _worker_loop(self):
        """Dedicated background loop handling rate-limited transmissions and health checks."""
        while not self._stop_event.is_set():
            now = time.time()

            # 1. Active Health Check & Watchdog (Every 3.5 seconds)
            if self.is_connected and (now - self.last_health_check >= 3.5):
                self._run_health_check()
            elif not self.is_connected and (now - self.last_health_check >= 2.0):
                # Auto-reconnect if offline
                self._connect()

            # 2. Process HSV Updates
            with self._lock:
                target = self._target_hsv

            if target is not None and self.is_connected and self.device:
                hue, saturation, value = target

                # Check rate limit
                if (now - self.last_send_time) >= self.min_interval:
                    dh = abs(hue - self.last_hsv[0])
                    ds = abs(saturation - self.last_hsv[1])
                    dv = abs(value - self.last_hsv[2])

                    # Only send if significant change
                    if dh >= 2.0 or ds >= 2.0 or dv >= 1.5:
                        self._send_hsv_payload(hue, saturation, value)

            # Sleep tiny slice to prevent CPU spinning while keeping response immediate
            time.sleep(0.01)

    def _send_hsv_payload(self, hue: float, saturation: float, value: float):
        """Encodes and transmits DPS 24 payload."""
        try:
            h_val = int(round(hue)) % 360
            s_val = max(0, min(1000, int(round(saturation * 10.0))))
            v_val = max(0, min(1000, int(round(value * 10.0))))
            hex_str = f"{h_val:04x}{s_val:04x}{v_val:04x}"

            self.device.set_value(24, hex_str, nowait=True)
            self.last_send_time = time.time()
            self.last_hsv = (hue, saturation, value)
            self.consecutive_errors = 0
        except Exception as e:
            self.consecutive_errors += 1
            logger.debug(f"Transmission error ({self.consecutive_errors}): {e}")
            if self.consecutive_errors >= 3:
                logger.warning("Multiple send errors detected. Marking offline for auto-reconnect.")
                self.is_connected = False

    def _run_health_check(self):
        """
        Sends heartbeat or status probe to verify bulb is actively executing commands.
        If bulb does not answer or socket has hung, automatically forces reconnection.
        """
        self.last_health_check = time.time()
        try:
            t0 = time.time()
            self.device.heartbeat()
            self.ping_ms = max(1.0, round((time.time() - t0) * 1000, 1))
            self.is_connected = True
            self.consecutive_errors = 0
        except Exception as e:
            logger.warning(f"Health check failed ({e}). Re-establishing bulb connection...")
            self.is_connected = False
            self._connect()

    def update_key(self, local_key: str):
        """Updates local_key dynamically and connects."""
        self.local_key = local_key
        if len(local_key) == 16:
            self.dry_run = False
            self._connect()
            self._start_worker()

    def set_hsv(self, hue: float, saturation: float, value: float):
        """
        Non-blocking thread-safe HSV update.
        Pushes target state to background worker thread immediately.
        """
        if self.dry_run:
            return
        with self._lock:
            self._target_hsv = (hue, saturation, value)

    def close(self):
        """Cleanly stops background worker thread and closes socket."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        self._worker_thread = None

        if self.device:
            try:
                self.device._check_socket_close(force=True)
            except Exception:
                pass
            self.device = None
            self.is_connected = False
