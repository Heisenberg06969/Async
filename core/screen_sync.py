"""
Screen Sync / Ambilight Engine for Async (Version 2.0).
Captures real-time desktop screen pixels using hardware-accelerated PySide6 DWM composition,
detects and crops movie letterboxing, boosts cinematic saturation, and features:
  1. Asymmetric Transient Strobe Engine: High-speed tracking of fast edits, car edit flash shakes,
     and strobe sequences (100% peak <-> 28% trough oscillation without 100% brightness plateauing).
  2. Dynamic Cinema EMA: Silky-smooth Exponential Moving Average for relaxed movie watching.
  3. Microsecond-synchronized RGB and HSV dual pipelines.
"""

import sys
import time
import colorsys
import logging
import threading
from typing import Tuple, Optional, Dict, Any
import numpy as np

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

logger = logging.getLogger("Async.ScreenSync")

class ScreenSyncEngine:
    def __init__(
        self,
        target_fps: int = 30,
        smoothing: float = 0.28,
        letterbox_crop: bool = True,
        strobe_boost: bool = True
    ):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / max(1, target_fps)
        self.smoothing = smoothing
        self.letterbox_crop = letterbox_crop
        self.saturation_boost = 1.30

        # Async 2.0: Transient Strobe & Fast Edit Engine
        self.strobe_boost: bool = strobe_boost
        self.strobe_sensitivity: float = 0.16 # Minimum luminance swing to trigger flash/drop detection
        self.strobe_floor: float = 0.26 # Trough brightness floor (26%) during strobe dips
        self.is_strobe_active: bool = False
        self._last_luma: float = 0.0
        self._last_flash_time: float = 0.0
        self._last_drop_time: float = 0.0
        self._strobe_decay_timer: float = 0.0
        self._strobe_trough_hold: float = 0.0

        self.is_running = False
        self.is_enabled = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Smoothed color state
        self._r: float = 0.0
        self._g: float = 0.0
        self._b: float = 0.0
        self.current_rgb: Tuple[int, int, int] = (0, 0, 0)
        self.current_hsv: Tuple[float, float, float] = (0.0, 0.0, 0.0)

        # Qt App reference
        self._app = None
        self._screen = None

    def _init_qt(self) -> bool:
        if not HAS_PYSIDE:
            logger.error("PySide6 is not installed. ScreenSync requires PySide6.")
            return False
        try:
            self._app = QGuiApplication.instance() or QGuiApplication(sys.argv)
            self._screen = QGuiApplication.primaryScreen()
            return self._screen is not None
        except Exception as e:
            logger.error(f"Failed to initialize Qt Screen Capture: {e}")
            return False

    def start(self):
        """Starts the background screen capture thread."""
        if self.is_running:
            return

        if not self._init_qt():
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._capture_loop, name="AsyncScreenSync", daemon=True)
        self._thread.start()
        logger.info(f"ScreenSync Engine 2.0 started (Target: {self.target_fps} FPS | Strobe Boost: {self.strobe_boost})")

    def stop(self):
        """Stops the capture thread."""
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def enable(self):
        """Enables active screen sampling."""
        self.is_enabled = True

    def disable(self):
        """Suspends active screen sampling to save CPU/GPU cycles."""
        self.is_enabled = False

    def set_smoothing(self, smoothing: float):
        """Sets EMA smoothing factor (0.05 = very slow/smooth, 0.9 = instant/fast)."""
        self.smoothing = max(0.05, min(1.0, float(smoothing)))

    def set_letterbox_crop(self, enabled: bool):
        self.letterbox_crop = bool(enabled)

    def set_saturation_boost(self, boost: float):
        self.saturation_boost = max(1.0, min(2.0, float(boost)))

    def set_strobe_boost(self, enabled: bool):
        """Toggles fast-edit flash shake / strobe boost mode."""
        self.strobe_boost = bool(enabled)
        if not self.strobe_boost:
            self.is_strobe_active = False

    def set_strobe_sensitivity(self, sensitivity: float):
        """Sets sensitivity threshold for strobe detection (0.05 to 0.40)."""
        self.strobe_sensitivity = max(0.05, min(0.40, float(sensitivity)))

    def set_strobe_floor(self, floor_val: float):
        """Sets trough brightness floor (0.10 to 0.45)."""
        self.strobe_floor = max(0.10, min(0.45, float(floor_val)))

    def _capture_loop(self):
        """High-performance capture worker loop with Transient Strobe tracking."""
        while self.is_running:
            t0 = time.time()

            if not self.is_enabled or not self._screen:
                time.sleep(0.05)
                continue

            try:
                # Grab primary desktop window (0 = entire virtual desktop)
                pix = self._screen.grabWindow(0)
                if pix.isNull():
                    time.sleep(0.02)
                    continue

                # Scale down directly in native Qt C++ (48x27 = 16:9 downsampled grid)
                small_pix = pix.scaled(48, 27, Qt.IgnoreAspectRatio, Qt.FastTransformation)
                img = small_pix.toImage().convertToFormat(QImage.Format_RGB888)
                ptr = img.constBits()
                arr = np.frombuffer(ptr, dtype=np.uint8).reshape((27, 48, 3))

                # Letterbox Detection (e.g. 21:9 or cinematic black bars on 16:9 screen)
                if self.letterbox_crop:
                    top_bar = arr[:4, :, :].mean()
                    bot_bar = arr[-4:, :, :].mean()
                    if top_bar < 9.0 and bot_bar < 9.0:
                        arr = arr[4:-4, :, :]

                # Compute mean RGB
                r_raw, g_raw, b_raw = arr.mean(axis=(0, 1))

                # Normalize RGB & Convert to HSV
                r_norm, g_norm, b_norm = r_raw / 255.0, g_raw / 255.0, b_raw / 255.0
                h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)

                # Saturation boost for vibrant ambient illumination
                if s > 0.04:
                    s = min(1.0, s * self.saturation_boost + 0.05)

                now = time.time()
                # Photometric perceived luminance: Y = 0.299R + 0.587G + 0.114B
                current_luma = 0.299 * r_norm + 0.587 * g_norm + 0.114 * b_norm
                dluma = current_luma - self._last_luma
                self._last_luma = current_luma

                # Transient Strobe & Shake Detection
                if self.strobe_boost:
                    # Flash attack detection (sharp positive surge)
                    if dluma >= self.strobe_sensitivity and current_luma > 0.35:
                        self._last_flash_time = now
                        self.is_strobe_active = True
                        self._strobe_decay_timer = now + 0.42 # Keep strobe tracking armed for 420ms
                        self._strobe_trough_hold = 0.0

                    # Strobe drop / trough detection (sharp negative cut or immediate post-flash frame)
                    if dluma <= -self.strobe_sensitivity or (
                        (now - self._last_flash_time <= 0.28) and (current_luma < 0.65) and (dluma < -0.06)
                    ):
                        self._last_drop_time = now
                        self._strobe_trough_hold = now + 0.075 # Hold trough for 75ms to overcome bulb PWM slew
                        self.is_strobe_active = True
                        self._strobe_decay_timer = now + 0.42

                    # Decay strobe active state if scene stabilizes
                    if now > self._strobe_decay_timer:
                        self.is_strobe_active = False

                # Calculate effective target brightness and smoothing rate
                if self.strobe_boost and self.is_strobe_active:
                    # High-tempo Strobe / Shake Mode active!
                    in_trough = (now < self._strobe_trough_hold) or (
                        (now - self._last_drop_time <= 0.10) and (current_luma < 0.60)
                    )

                    if in_trough:
                        # Plunge to contrast trough floor (e.g. 26-28% rather than plateauing at 90%)
                        effective_v = max(0.08, min(self.strobe_floor, current_luma * 0.50))
                        alpha = 0.88 # Snap fast to low trough
                    else:
                        # Peak Flash!
                        effective_v = 1.0 # 100% full burst
                        alpha = 0.95 # Instant attack
                        if current_luma > 0.70:
                            # White-hot flare tint on extreme bursts
                            s = max(0.0, s * 0.40)
                else:
                    # Standard Ambient Cinema Mode (Buttery smooth EMA)
                    effective_v = max(0.12, v)
                    alpha = self.smoothing

                # Convert enhanced target color back to RGB
                r_enh, g_enh, b_enh = colorsys.hsv_to_rgb(h, s, effective_v)
                target_r = r_enh * 255.0
                target_g = g_enh * 255.0
                target_b = b_enh * 255.0

                # Asymmetric Exponential Moving Average (EMA)
                self._r = self._r * (1.0 - alpha) + target_r * alpha
                self._g = self._g * (1.0 - alpha) + target_g * alpha
                self._b = self._b * (1.0 - alpha) + target_b * alpha

                out_rgb = (int(np.clip(self._r, 0, 255)),
                           int(np.clip(self._g, 0, 255)),
                           int(np.clip(self._b, 0, 255)))

                # Synchronize HSV directly with effective_v
                out_hsv = (round(h * 360.0, 1),
                           round(s * 100.0, 1),
                           round(effective_v * 100.0, 1))

                with self._lock:
                    self.current_rgb = out_rgb
                    self.current_hsv = out_hsv

            except Exception as e:
                logger.error(f"Error in ScreenSync capture loop: {e}")

            elapsed = time.time() - t0
            sleep_time = max(0.005, self.frame_interval - elapsed)
            time.sleep(sleep_time)

    def get_color(self) -> Tuple[Tuple[int, int, int], Tuple[float, float, float]]:
        """Returns the latest smoothed (rgb, hsv) color tuple."""
        with self._lock:
            return self.current_rgb, self.current_hsv

    def get_status(self) -> Dict[str, Any]:
        """Returns engine configuration and live strobe metrics."""
        with self._lock:
            return {
                "enabled": self.is_enabled,
                "strobe_boost": self.strobe_boost,
                "strobe_active": self.is_strobe_active,
                "strobe_floor": round(self.strobe_floor * 100.0, 1),
                "strobe_sensitivity": round(self.strobe_sensitivity * 100.0, 1),
                "smoothing": self.smoothing
            }
