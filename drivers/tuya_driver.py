"""
Local Wi-Fi Tuya / Havells Bulb Driver for Async (Version 2.0).
Controls Havells Smart Bulbs (Tuya protocol 3.3/3.4) directly over LAN port 6668
with zero cloud delay, Peak-Preserving Cadence rate limiting, socket buffer draining,
and sub-second self-healing watchdog (<350ms auto-recovery).
"""

import socket
import select
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
        min_interval: float = 0.062 # ~16 FPS max safe cadence for microcontroller TCP buffers
    ):
        self.device_id = device_id
        self.ip_address = ip_address
        self.local_key = local_key
        self.version = version
        self.min_interval = min_interval

        self.device: Optional[tinytuya.BulbDevice] = None
        self.is_connected: bool = False
        self.dry_run: bool = not bool(local_key and len(local_key) == 16)

        # Health, Telemetry & Rate Tracking
        self.ping_ms: float = 0.0
        self.last_health_check: float = 0.0
        self.consecutive_errors: int = 0
        self.last_send_time: float = 0.0
        self.last_hsv: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.last_white: Tuple[int, int] = (100, 500)
        self.reconnect_count: int = 0
        self.packets_sent: int = 0
        self.packets_per_sec: float = 0.0
        self._pps_counter: int = 0
        self._pps_timer: float = time.time()

        # Operational States (Power, Mode, Targets)
        self.is_power_on: bool = True
        self.current_mode: str = "colour"
        self._mode_switched: bool = False
        self._target_hsv: Optional[Tuple[float, float, float]] = None
        self._target_white: Optional[Tuple[int, int]] = None
        self._lock = threading.Lock()
        self._reconnect_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._is_reconnecting: bool = False

        if not self.dry_run:
            self._connect()
            self._start_worker()
        else:
            logger.info("TuyaDriver 2.0 initialized in DRY-RUN mode (waiting for 16-char local_key).")

    def _connect(self) -> bool:
        """Initializes persistent, low-latency socket session to the smart bulb."""
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
            # Async 2.0: Ultra-low latency TCP stack tuning
            self.device.set_socketPersistent(True) # Keep socket open for real-time streaming
            self.device.set_socketNODELAY(True)    # RFC 896: Disable Nagle algorithm (instant packet dispatch)
            self.device.set_socketTimeout(0.35)    # 350ms fail-fast timeout (never hang for seconds)
            self.device.set_socketRetryLimit(1)    # 1 attempt only: fail immediately to trigger sub-second recovery
            self.device.set_socketRetryDelay(0.02)

            # Turn on bulb and lock mode to colour
            t0 = time.time()
            self.device.set_multiple_values({"20": True, "21": "colour"}, nowait=True)
            self.ping_ms = round((time.time() - t0) * 1000, 1)

            self.is_connected = True
            self.consecutive_errors = 0
            self.last_health_check = time.time()
            logger.info(f"Connected to Havells bulb at {self.ip_address}:6668 ({self.ping_ms}ms | Version 2.0 Engine)")
            return True
        except Exception as e:
            logger.warning(f"Connection to bulb failed: {e}")
            self.is_connected = False
            return False

    def _fast_reconnect(self, reason: str = "Stall detected"):
        """
        Sub-second socket recovery (<350ms).
        Safely tears down the stalled socket and re-establishes TCP session
        without blocking the main render or audio capture loop.
        """
        with self._reconnect_lock:
            if self.dry_run or self._is_reconnecting:
                return
            self._is_reconnecting = True
            self.is_connected = False
            self.reconnect_count += 1
            t0 = time.time()
            logger.warning(f"Sub-second recovery triggered ({reason}). Reconnect #{self.reconnect_count}")
            try:
                if self.device:
                    try:
                        self.device._check_socket_close(force=True)
                    except Exception:
                        pass
                success = self._connect()
                elapsed = round((time.time() - t0) * 1000, 1)
                if success:
                    logger.info(f"Sub-second socket recovery successful in {elapsed}ms!")
            except Exception as e:
                logger.error(f"Fast reconnect attempt failed: {e}")
            finally:
                self._is_reconnecting = False

    def _start_worker(self):
        """Starts background worker thread for asynchronous frame dispatch & health checks."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._worker_loop, name="TuyaBulbWorker", daemon=True)
            self._worker_thread.start()

    def _worker_loop(self):
        """Dedicated background loop handling rate-limited transmissions, buffer draining, and sub-second recovery."""
        while not self._stop_event.is_set():
            now = time.time()

            # PPS Telemetry calculation
            if now - self._pps_timer >= 1.0:
                self.packets_per_sec = round(self._pps_counter / (now - self._pps_timer), 1)
                self._pps_counter = 0
                self._pps_timer = now

            # 1. Drain incoming TCP socket buffer & detect EOF / OS exceptions immediately (<10ms)
            if self.is_connected and self.device and not self._is_reconnecting:
                try:
                    sock = getattr(self.device, "socket", None)
                    if sock and sock.fileno() != -1:
                        rlist, _, xlist = select.select([sock], [], [sock], 0.0)
                        if xlist:
                            self._fast_reconnect("Socket exception from OS")
                            time.sleep(0.04)
                            continue
                        elif rlist:
                            chunk = sock.recv(2048)
                            if not chunk:
                                self._fast_reconnect("Socket EOF (bulb closed connection)")
                                time.sleep(0.04)
                                continue
                except (socket.error, OSError) as e:
                    self._fast_reconnect(f"Socket poll exception: {e}")
                    time.sleep(0.04)
                    continue

            # 2. Sub-second Liveness Watchdog (Every 1.2s during quiet / idle periods)
            if self.is_connected and not self._is_reconnecting:
                if (now - self.last_send_time >= 1.2) and (now - self.last_health_check >= 1.2):
                    self._run_health_check()
            elif not self.is_connected and not self._is_reconnecting:
                if now - self.last_health_check >= 0.8:
                    self._fast_reconnect("Auto-reconnect while offline")

            # 3. Peak-Preserving Cadence Dispatcher
            with self._lock:
                target_mode = self.current_mode
                mode_switched = self._mode_switched
                target_hsv = self._target_hsv
                target_white = self._target_white

            if self.is_connected and self.device and not self._is_reconnecting:
                if target_mode == "white" and target_white is not None:
                    bright, temp = target_white
                    db = abs(bright - self.last_white[0])
                    dt = abs(temp - self.last_white[1])
                    time_since_send = now - self.last_send_time

                    if mode_switched or (time_since_send >= 0.050 and (db >= 1 or dt >= 4)):
                        if self._send_white_payload(bright, temp, force_mode=mode_switched):
                            if mode_switched:
                                with self._lock:
                                    self._mode_switched = False

                elif target_mode == "colour" and target_hsv is not None:
                    hue, saturation, value = target_hsv
                    dh = abs(hue - self.last_hsv[0])
                    ds = abs(saturation - self.last_hsv[1])
                    dv = abs(value - self.last_hsv[2])

                    time_since_send = now - self.last_send_time

                    # Peak / Trough Extremum detection
                    is_peak = (value >= 90.0 and dv >= 15.0)
                    is_trough = (value <= 32.0 and dv >= 15.0)

                    should_send = False
                    if mode_switched:
                        should_send = True
                    elif is_peak or is_trough:
                        if time_since_send >= 0.050:
                            should_send = True
                    else:
                        if time_since_send >= self.min_interval:
                            if dh >= 2.0 or ds >= 2.0 or dv >= 1.5:
                                should_send = True

                    if should_send:
                        if self._send_hsv_payload(hue, saturation, value, force_mode=mode_switched):
                            if mode_switched:
                                with self._lock:
                                    self._mode_switched = False

            # Sleep tiny slice to prevent CPU spinning while keeping response immediate
            time.sleep(0.008)

    def _send_hsv_payload(self, hue: float, saturation: float, value: float, force_mode: bool = False) -> bool:
        """Encodes and transmits DPS 24 payload with instant error capture."""
        try:
            h_val = int(round(hue)) % 360
            s_val = max(0, min(1000, int(round(saturation * 10.0))))
            v_val = max(0, min(1000, int(round(value * 10.0))))
            hex_str = f"{h_val:04x}{s_val:04x}{v_val:04x}"

            if force_mode:
                self.device.set_multiple_values({"20": True, "21": "colour"}, nowait=True)
                self.device.set_value(24, hex_str, nowait=True)
            else:
                self.device.set_value(24, hex_str, nowait=True)

            self.last_send_time = time.time()
            self.last_hsv = (hue, saturation, value)
            self.consecutive_errors = 0
            self._pps_counter += 1
            self.packets_sent += 1
            return True
        except Exception as e:
            self.consecutive_errors += 1
            logger.warning(f"Transmission error on send: {e}. Initiating sub-second recovery...")
            self._fast_reconnect(f"Send error: {e}")
            return False

    def _send_white_payload(self, brightness: int, colourtemp: int, force_mode: bool = False) -> bool:
        """Encodes and transmits DP 21='white', DP 22 (brightness), DP 23 (temp)."""
        try:
            b_val = max(10, min(1000, int(brightness * 10)))
            t_val = max(0, min(1000, int(colourtemp)))

            if force_mode:
                self.device.set_multiple_values({"20": True, "21": "white"}, nowait=True)
                self.device.set_multiple_values({"22": b_val, "23": t_val}, nowait=True)
            else:
                payload = {"20": True, "22": b_val, "23": t_val}
                self.device.set_multiple_values(payload, nowait=True)

            self.last_send_time = time.time()
            self.last_white = (brightness, colourtemp)
            self.consecutive_errors = 0
            self._pps_counter += 1
            self.packets_sent += 1
            return True
        except Exception as e:
            self.consecutive_errors += 1
            logger.warning(f"Transmission error on white send: {e}. Initiating sub-second recovery...")
            self._fast_reconnect(f"White send error: {e}")
            return False

    def set_power(self, power: bool):
        """Sets hardware bulb power (DP 20: True/False)."""
        self.is_power_on = power
        if self.dry_run or not self.device or not self.is_connected:
            return
        try:
            self.device.set_value(20, bool(power), nowait=True)
            logger.info(f"Bulb power set to {'ON' if power else 'OFF'} (DP 20)")
        except Exception as e:
            logger.warning(f"Error setting bulb power: {e}")
            self._fast_reconnect(f"Power toggle error: {e}")

    def set_white(self, brightness: int = 100, colourtemp: int = 500):
        """
        Sets bulb to white mode (DP 21: 'white').
        brightness: 1 to 100 (percentage)
        colourtemp: 0 to 1000 (0=Warm 2700K, 1000=Cold 6500K)
        """
        if self.dry_run:
            return
        with self._lock:
            if self.current_mode != "white":
                self.current_mode = "white"
                self._mode_switched = True
                self.last_white = (-999, -999)
                self.last_hsv = (-999.0, -999.0, -999.0)
            self._target_white = (max(1, min(100, int(brightness))), max(0, min(1000, int(colourtemp))))

    def set_hsv(self, hue: float, saturation: float, value: float):
        """
        Non-blocking thread-safe HSV update.
        Pushes target state to background worker thread immediately.
        """
        if self.dry_run:
            return
        with self._lock:
            if self.current_mode != "colour":
                self.current_mode = "colour"
                self._mode_switched = True
                self.last_white = (-999, -999)
                self.last_hsv = (-999.0, -999.0, -999.0)
            self._target_hsv = (hue, saturation, value)

    def _run_health_check(self):
        """
        Lightweight heartbeat probe with 350ms timeout.
        If bulb does not answer or socket has hung, immediately recovers.
        """
        self.last_health_check = time.time()
        try:
            t0 = time.time()
            self.device.heartbeat()
            self.ping_ms = max(1.0, round((time.time() - t0) * 1000, 1))
            self.is_connected = True
            self.consecutive_errors = 0
        except Exception as e:
            logger.warning(f"Heartbeat probe failed ({e}). Re-establishing bulb connection...")
            self._fast_reconnect(f"Heartbeat failed: {e}")

    def update_key(self, local_key: str):
        """Updates local_key dynamically and connects."""
        self.local_key = local_key
        if len(local_key) == 16:
            self.dry_run = False
            self._connect()
            self._start_worker()

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
