"""
Screen Sync / Ambilight Engine for Async.
Captures real-time desktop screen pixels using hardware-accelerated PySide6 DWM composition,
detects and crops movie letterboxing, boosts cinematic saturation, and applies
buttery-smooth Exponential Moving Average (EMA) temporal smoothing for smart ambient lighting.
"""

import sys
import time
import colorsys
import logging
import threading
from typing import Tuple, Optional
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
    def __init__(self, target_fps: int = 30, smoothing: float = 0.28, letterbox_crop: bool = True):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / max(1, target_fps)
        self.smoothing = smoothing
        self.letterbox_crop = letterbox_crop
        self.saturation_boost = 1.30

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
        logger.info(f"ScreenSync Engine started (Target: {self.target_fps} FPS)")

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

    def _capture_loop(self):
        """High-performance capture worker loop."""
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
                    # Check top 4 rows and bottom 4 rows
                    top_bar = arr[:4, :, :].mean()
                    bot_bar = arr[-4:, :, :].mean()
                    if top_bar < 9.0 and bot_bar < 9.0:
                        # Exclude black bars to avoid muting movie color
                        arr = arr[4:-4, :, :]

                # Compute mean RGB
                r_raw, g_raw, b_raw = arr.mean(axis=(0, 1))

                # Cinematic Saturation & Brightness enhancement
                r_norm, g_norm, b_norm = r_raw / 255.0, g_raw / 255.0, b_raw / 255.0
                h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)

                if s > 0.04:
                    s = min(1.0, s * self.saturation_boost + 0.05)

                # Ensure minimum ambient illumination during dark movie scenes (12%)
                v_boosted = max(0.12, v)

                # Convert back to enhanced RGB
                r_enh, g_enh, b_enh = colorsys.hsv_to_rgb(h, s, v_boosted)
                target_r = r_enh * 255.0
                target_g = g_enh * 255.0
                target_b = b_enh * 255.0

                # Exponential Moving Average (EMA Smoothing)
                alpha = self.smoothing
                self._r = self._r * (1.0 - alpha) + target_r * alpha
                self._g = self._g * (1.0 - alpha) + target_g * alpha
                self._b = self._b * (1.0 - alpha) + target_b * alpha

                out_rgb = (int(np.clip(self._r, 0, 255)),
                           int(np.clip(self._g, 0, 255)),
                           int(np.clip(self._b, 0, 255)))

                out_hsv = (round(h * 360.0, 1),
                           round(s * 100.0, 1),
                           round(v_boosted * 100.0, 1))

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
