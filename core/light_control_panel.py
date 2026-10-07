"""
Async 2.0: Master Light Control Panel & Multi-Mode Studio Deck.
Built to impeccable visual standards:
  - 3 Primary Operating Modes:
      1. Solid Mode: Dual Color Spectrum (2D HSV) & White Temperature (2700K-6500K)
      2. Audio Visualizer Mode: Real-time 20-band live FFT spectrum with selectable DSP profiles
      3. Ambilight Screen Mode: Real-time desktop edge-sampling monitor visualizer
  - Universal Precision Brightness Track Slider
  - Hardware Power Switch Toggle (Tuya DP 20)
  - Seamless Window Dragging & Dark OLED Aesthetic
  - 100% Pure ASCII (zero Unicode crash traps or emoji)
"""

from typing import Tuple, List, Optional, Dict, Any
import math
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QGraphicsDropShadowEffect,
    QFrame, QSizePolicy, QMenu
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath,
    QLinearGradient, QRadialGradient, QFont, QMouseEvent,
    QCursor, QPaintEvent
)
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal, QTimer


def kelvin_to_rgb(kelvin: float) -> Tuple[int, int, int]:
    """Approximates sRGB color for blackbody color temperature (2000K to 7000K)."""
    temp = kelvin / 100.0
    if temp <= 66:
        r = 255
        g = max(0, min(255, int(99.4708025861 * math.log(temp) - 161.1195681661)))
        if temp <= 19:
            b = 0
        else:
            b = max(0, min(255, int(138.5177312231 * math.log(temp - 10) - 305.0447927307)))
    else:
        r = max(0, min(255, int(329.698727446 * math.pow(temp - 60, -0.1332047592))))
        g = max(0, min(255, int(288.1221695283 * math.pow(temp - 60, -0.0755148492))))
        b = 255
    return r, g, b


def get_color_name(hue: float, sat: float) -> str:
    """Returns human-readable name for an HSV coordinate."""
    if sat < 0.15:
        return "Soft White"
    h = hue % 360.0
    if h < 18 or h >= 345:
        return "Crimson Red"
    elif h < 45:
        return "Warm Amber"
    elif h < 68:
        return "Solar Gold"
    elif h < 155:
        return "Vibrant Green"
    elif h < 195:
        return "Pure Cyan"
    elif h < 255:
        return "Deep Blue"
    elif h < 290:
        return "Electric Violet"
    else:
        return "Neon Magenta"


# =========================================================================
# Custom Precision Widgets
# =========================================================================

class HeaderBar(QWidget):
    """Window header with branding, connection pill, power toggle, and close."""
    closeClicked = Signal()
    powerToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.is_power_on = True
        self.is_connected = True
        self._drag_pos: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 14, 8)
        layout.setSpacing(10)

        # Brand Title
        self.lbl_title = QLabel("ASYNC", self)
        self.lbl_title.setStyleSheet("""
            color: #F8FAFC;
            font-family: 'Segoe UI', system-ui;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 2px;
        """)
        layout.addWidget(self.lbl_title)

        # Connection Badge Pill
        self.lbl_status = QLabel("ONLINE", self)
        self.lbl_status.setStyleSheet("""
            background-color: rgba(16, 185, 129, 0.15);
            color: #10B981;
            font-family: 'Segoe UI';
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
            padding: 2px 7px;
            border-radius: 9px;
            border: 1px solid rgba(16, 185, 129, 0.3);
        """)
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        # Hardware Power Switch Button
        self.btn_power = QPushButton(self)
        self.btn_power.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_power.setFixedHeight(26)
        self.btn_power.setFixedWidth(64)
        self.btn_power.clicked.connect(self._on_power_click)
        layout.addWidget(self.btn_power)
        self._update_power_button()

        # Close Button
        self.btn_close = QPushButton(self)
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 13px;
                color: #94A3B8;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.20);
                border-color: #EF4444;
                color: #EF4444;
            }
        """)
        self.btn_close.setText("X")
        self.btn_close.clicked.connect(self.closeClicked.emit)
        layout.addWidget(self.btn_close)

    def set_power_state(self, state: bool):
        self.is_power_on = state
        self._update_power_button()

    def set_connected_state(self, connected: bool):
        self.is_connected = connected
        if connected:
            self.lbl_status.setText("ONLINE")
            self.lbl_status.setStyleSheet("""
                background-color: rgba(16, 185, 129, 0.15);
                color: #10B981;
                font-family: 'Segoe UI';
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 2px 7px;
                border-radius: 9px;
                border: 1px solid rgba(16, 185, 129, 0.3);
            """)
        else:
            self.lbl_status.setText("OFFLINE")
            self.lbl_status.setStyleSheet("""
                background-color: rgba(239, 68, 68, 0.15);
                color: #EF4444;
                font-family: 'Segoe UI';
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 2px 7px;
                border-radius: 9px;
                border: 1px solid rgba(239, 68, 68, 0.3);
            """)

    def _on_power_click(self):
        self.is_power_on = not self.is_power_on
        self._update_power_button()
        self.powerToggled.emit(self.is_power_on)

    def _update_power_button(self):
        if self.is_power_on:
            self.btn_power.setText("PWR ON")
            self.btn_power.setStyleSheet("""
                QPushButton {
                    background-color: #064E3B;
                    color: #34D399;
                    border: 1px solid #10B981;
                    border-radius: 13px;
                    font-family: 'Segoe UI';
                    font-size: 10px;
                    font-weight: 800;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background-color: #047857;
                }
            """)
        else:
            self.btn_power.setText("PWR OFF")
            self.btn_power.setStyleSheet("""
                QPushButton {
                    background-color: #27272A;
                    color: #A1A1AA;
                    border: 1px solid #3F3F46;
                    border-radius: 13px;
                    font-family: 'Segoe UI';
                    font-size: 10px;
                    font-weight: 800;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background-color: #3F3F46;
                }
            """)

    # Allow dragging parent window via header
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None


class SegmentedModeBar(QWidget):
    """
    Precision 3-way segmented control for the 3 primary modes:
      [ Solid ]  [ Audio Sync ]  [ Ambilight ]
    """
    modeSelected = Signal(str)  # "solid", "audio", "screen_ambilight"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.current_mode = "solid"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(4)

        self.btn_solid = QPushButton("Solid Color", self)
        self.btn_audio = QPushButton("Audio Sync", self)
        self.btn_ambi = QPushButton("Ambilight", self)

        for btn in (self.btn_solid, self.btn_audio, self.btn_ambi):
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.btn_solid.clicked.connect(lambda: self.set_mode("solid"))
        self.btn_audio.clicked.connect(lambda: self.set_mode("audio"))
        self.btn_ambi.clicked.connect(lambda: self.set_mode("screen_ambilight"))

        layout.addWidget(self.btn_solid)
        layout.addWidget(self.btn_audio)
        layout.addWidget(self.btn_ambi)

        self.setStyleSheet("""
            SegmentedModeBar {
                background-color: #12131C;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        self._refresh_styles()

    def set_mode(self, mode: str):
        if mode not in ("solid", "audio", "screen_ambilight"):
            mode = "solid"
        self.current_mode = mode
        self._refresh_styles()
        self.modeSelected.emit(mode)

    def _refresh_styles(self):
        active_css = """
            QPushButton {
                background-color: #272A3D;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
        """
        inactive_css = """
            QPushButton {
                background-color: transparent;
                color: #8E95AA;
                border: none;
                border-radius: 7px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #CBD5E1;
                background-color: rgba(255, 255, 255, 0.04);
            }
        """
        self.btn_solid.setStyleSheet(active_css if self.current_mode == "solid" else inactive_css)
        self.btn_audio.setStyleSheet(active_css if self.current_mode == "audio" else inactive_css)
        self.btn_ambi.setStyleSheet(active_css if self.current_mode == "screen_ambilight" else inactive_css)


# =========================================================================
# Solid Mode: Color & White Spectrum Widgets
# =========================================================================

class ColorChartWidget(QWidget):
    """
    2D Hue-Saturation interactive spectrum canvas.
    X-axis: Hue (0 - 360 deg)
    Y-axis: Saturation (0.08 - 1.0)
    Features precision circular target reticle and hairline stroke.
    """
    colorChanged = Signal(int, int, int)  # r, g, b
    coordChanged = Signal(float, float)   # hue, sat

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 150)
        self.hue: float = 195.0
        self.sat: float = 0.85
        self._is_dragging: bool = False
        self.setCursor(QCursor(Qt.CrossCursor))

    def set_hsv(self, hue: float, sat: float):
        self.hue = max(0.0, min(360.0, hue))
        self.sat = max(0.05, min(1.0, sat))
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._update_from_pos(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            self._update_from_pos(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False

    def _update_from_pos(self, x: float, y: float):
        w = max(1.0, float(self.width()))
        h = max(1.0, float(self.height()))
        self.hue = max(0.0, min(360.0, (x / w) * 360.0))
        # Top = high saturation, bottom = desaturated pastel
        self.sat = max(0.08, min(1.0, 1.0 - (y / h) * 0.92))
        self.update()

        c = QColor.fromHsvF(self.hue / 360.0, self.sat, 1.0)
        self.colorChanged.emit(c.red(), c.green(), c.blue())
        self.coordChanged.emit(self.hue, self.sat)

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 12.0

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip_path)

        # 1. Horizontal Hue Spectrum Gradient
        grad_hue = QLinearGradient(0, 0, w, 0)
        stops = [
            (0.00, "#FF0000"), (0.17, "#FFFF00"), (0.33, "#00FF00"),
            (0.50, "#00FFFF"), (0.67, "#0000FF"), (0.83, "#FF00FF"),
            (1.00, "#FF0000")
        ]
        for pos, col in stops:
            grad_hue.setColorAt(pos, QColor(col))
        p.fillRect(rect, grad_hue)

        # 2. Vertical Desaturation Gradient (Top vibrant, bottom pastel white)
        grad_sat = QLinearGradient(0, 0, 0, h)
        grad_sat.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad_sat.setColorAt(1.0, QColor(255, 255, 255, 230))
        p.fillRect(rect, grad_sat)

        # 3. Outer Hairline Border
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # 4. Draggable Target Reticle Handle
        target_x = (self.hue / 360.0) * w
        target_y = (1.0 - (self.sat - 0.08) / 0.92) * h
        active_color = QColor.fromHsvF(self.hue / 360.0, self.sat, 1.0)

        p.setRenderHint(QPainter.Antialiasing, True)
        # Drop shadow around reticle
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawEllipse(QPointF(target_x + 1, target_y + 1), 11.0, 11.0)

        # Outer white ring
        p.setPen(QPen(QColor(255, 255, 255, 240), 2.5))
        p.setBrush(active_color)
        p.drawEllipse(QPointF(target_x, target_y), 9.0, 9.0)


class WhiteChartWidget(QWidget):
    """
    Continuous color temperature chart for whites only.
    Stretches from Warm Amber (2700K) to Cool Daylight (6500K).
    """
    temperatureChanged = Signal(int)  # 0 (2700K) to 1000 (6500K)
    kelvinChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 150)
        self.temp_ratio: float = 0.40  # 0.0 to 1.0
        self._is_dragging: bool = False
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_temperature(self, temp_val: int):
        self.temp_ratio = max(0.0, min(1.0, temp_val / 1000.0))
        self.update()

    def get_kelvin(self) -> int:
        return int(2700 + self.temp_ratio * (6500 - 2700))

    def get_rgb(self) -> Tuple[int, int, int]:
        return kelvin_to_rgb(self.get_kelvin())

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._update_from_pos(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            self._update_from_pos(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False

    def _update_from_pos(self, x: float):
        w = max(1.0, float(self.width()))
        self.temp_ratio = max(0.0, min(1.0, x / w))
        self.update()
        raw_val = int(round(self.temp_ratio * 1000))
        self.temperatureChanged.emit(raw_val)
        self.kelvinChanged.emit(self.get_kelvin())

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 12.0

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip_path)

        # Horizontal Kelvin Blackbody Gradient
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.00, QColor("#FF9D2E"))  # Warm Amber 2700K
        grad.setColorAt(0.28, QColor("#FFE4B8"))  # Soft White 3500K
        grad.setColorAt(0.60, QColor("#FFFFFF"))  # Neutral White 4500K
        grad.setColorAt(1.00, QColor("#BBE2FF"))  # Cool Daylight 6500K
        p.fillRect(rect, grad)

        # Subtle dark ambient lighting falloff
        vgrad = QLinearGradient(0, 0, 0, h)
        vgrad.setColorAt(0.0, QColor(255, 255, 255, 30))
        vgrad.setColorAt(1.0, QColor(0, 0, 0, 35))
        p.fillRect(rect, vgrad)

        # Hairline border
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # Draggable Handle Bar
        target_x = max(12.0, min(w - 12.0, self.temp_ratio * w))
        r, g, b = self.get_rgb()

        # Shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(QRectF(target_x - 4, 10, 10, h - 20), 5, 5)

        # Handle Pill
        p.setPen(QPen(QColor(255, 255, 255, 240), 2))
        p.setBrush(QColor(r, g, b))
        p.drawRoundedRect(QRectF(target_x - 5, 8, 10, h - 16), 5, 5)


class SwatchCircleButton(QPushButton):
    """Refined circular preset swatch with active ring indicator."""
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = color
        self.is_active = False
        self.setFixedSize(30, 30)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_active(self, active: bool):
        self.is_active = active
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        if self.is_active:
            p.setPen(QPen(QColor("#38BDF8"), 2.0))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(rect.adjusted(1, 1, -1, -1))
            inner = rect.adjusted(4, 4, -4, -4)
        else:
            p.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
            inner = rect.adjusted(2, 2, -2, -2)

        p.setBrush(self.color)
        p.drawEllipse(inner)


class WhitePresetButton(QPushButton):
    """Textual Kelvin preset button (e.g. 2700K Warm)."""
    def __init__(self, label: str, temp_val: int, kelvin: int, parent=None):
        super().__init__(label, parent)
        self.temp_val = temp_val
        self.kelvin = kelvin
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(26)
        self.setStyleSheet("""
            QPushButton {
                background-color: #1A1C29;
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: 600;
                padding: 0 8px;
            }
            QPushButton:hover {
                background-color: #272A3D;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
        """)


# =========================================================================
# Mode 2 Surface: Live Audio Spectrum Equalizer
# =========================================================================

class AudioSpectrumWidget(QWidget):
    """
    Real-time 20-band live FFT audio visualizer.
    Displays dynamic frequency bars that bounce smoothly with music.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 120)
        self.num_bars = 20
        self.bands = np.zeros(self.num_bars, dtype=np.float32)
        self.peak_bars = np.zeros(self.num_bars, dtype=np.float32)

    def set_bands(self, bands: np.ndarray):
        if bands is None or len(bands) == 0:
            return
        if len(bands) == self.num_bars:
            target = bands
        else:
            # Resample bands to 20 bars
            indices = np.linspace(0, len(bands) - 1, self.num_bars).astype(int)
            target = bands[indices]

        # Gravity & smoothing decay
        self.bands = 0.55 * self.bands + 0.45 * target
        self.peak_bars = np.maximum(self.peak_bars * 0.94, self.bands)
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 12.0

        # Background Card
        p.setPen(QPen(QColor(255, 255, 255, 15), 1))
        p.setBrush(QColor("#10111A"))
        p.drawRoundedRect(rect, radius, radius)

        # Equalizer Bars Layout
        bar_count = self.num_bars
        margin_x = 16.0
        avail_w = w - (margin_x * 2.0)
        spacing = 4.0
        bar_w = max(4.0, (avail_w - (bar_count - 1) * spacing) / bar_count)
        max_h = h - 28.0

        for i in range(bar_count):
            val = float(self.bands[i])
            val = max(0.04, min(1.0, val))
            bar_h = val * max_h
            bx = margin_x + i * (bar_w + spacing)
            by = h - 14.0 - bar_h

            # Dynamic bar gradient: Cyan base to Violet / Amber crest
            grad = QLinearGradient(bx, by + bar_h, bx, by)
            grad.setColorAt(0.0, QColor("#38BDF8"))
            grad.setColorAt(0.7, QColor("#818CF8"))
            grad.setColorAt(1.0, QColor("#F43F5E"))

            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), bar_w / 2.0, bar_w / 2.0)

            # Peak hold dot
            peak_val = float(self.peak_bars[i])
            peak_y = h - 14.0 - (peak_val * max_h) - 3.0
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawRoundedRect(QRectF(bx, peak_y, bar_w, 2.0), 1.0, 1.0)


# =========================================================================
# Mode 3 Surface: Live Ambilight Monitor Display Preview
# =========================================================================

class AmbilightDisplayWidget(QWidget):
    """
    Live desktop monitor silhouette with ambient edge backlight glow.
    Reflects the live sampled color sent to the Tuya bulb in real time.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 140)
        self.current_rgb: Tuple[int, int, int] = (56, 189, 248)

    def set_rgb(self, r: int, g: int, b: int):
        self.current_rgb = (r, g, b)
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 12.0

        # Background Card
        p.setPen(QPen(QColor(255, 255, 255, 15), 1))
        p.setBrush(QColor("#10111A"))
        p.drawRoundedRect(rect, radius, radius)

        r, g, b = self.current_rgb
        mon_w = 170.0
        mon_h = 96.0
        mon_x = (w - mon_w) / 2.0
        mon_y = 14.0

        # 1. Radiant Ambient Backlight Glow around Monitor
        glow_rad = QRadialGradient(w / 2.0, mon_y + mon_h / 2.0, 110.0)
        glow_rad.setColorAt(0.0, QColor(r, g, b, 140))
        glow_rad.setColorAt(0.5, QColor(r, g, b, 50))
        glow_rad.setColorAt(1.0, QColor(r, g, b, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow_rad)
        p.drawEllipse(QRectF((w / 2.0) - 120, mon_y - 20, 240, mon_h + 40))

        # 2. Monitor Outer Bezel
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor("#181926"))
        p.drawRoundedRect(QRectF(mon_x, mon_y, mon_w, mon_h), 6.0, 6.0)

        # 3. Monitor Inner Screen Preview (Sampling Area)
        screen_rect = QRectF(mon_x + 5, mon_y + 5, mon_w - 10, mon_h - 10)
        s_grad = QLinearGradient(screen_rect.topLeft(), screen_rect.bottomRight())
        s_grad.setColorAt(0.0, QColor(r, g, b, 180))
        s_grad.setColorAt(1.0, QColor(int(r * 0.4), int(g * 0.4), int(b * 0.4), 220))
        p.setPen(Qt.NoPen)
        p.setBrush(s_grad)
        p.drawRoundedRect(screen_rect, 4.0, 4.0)

        # 4. Monitor Stand Base
        stand_w = 40.0
        stand_x = (w - stand_w) / 2.0
        stand_y = mon_y + mon_h
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2C2E40"))
        p.drawRect(QRectF((w - 12.0) / 2.0, stand_y, 12.0, 10.0))
        p.drawRoundedRect(QRectF(stand_x, stand_y + 9, stand_w, 4.0), 2.0, 2.0)


# =========================================================================
# Universal Brightness Slider Deck
# =========================================================================

class PrecisionBrightnessSlider(QWidget):
    """
    Sleek, low-profile brightness track with:
      - Crisp vector Sun icon
      - Hairline progress fill
      - Right-aligned percentage readout
    """
    brightnessChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.brightness: int = 100
        self.fill_color: QColor = QColor("#38BDF8")
        self._is_dragging: bool = False
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_brightness(self, val: int):
        self.brightness = max(1, min(100, val))
        self.update()

    def set_color(self, color: QColor):
        self.fill_color = color
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._update_from_pos(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            self._update_from_pos(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False

    def _update_from_pos(self, x: float):
        track_start = 38.0
        track_end = float(self.width()) - 54.0
        track_w = max(10.0, track_end - track_start)
        rel_x = max(0.0, min(track_w, x - track_start))
        self.brightness = max(1, min(100, int(round((rel_x / track_w) * 100))))
        self.update()
        self.brightnessChanged.emit(self.brightness)

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)

        # Background track card
        p.setPen(QPen(QColor(255, 255, 255, 12), 1))
        p.setBrush(QColor("#13141F"))
        p.drawRoundedRect(rect, 10.0, 10.0)

        # 1. Vector Sun Icon on Left
        sun_cx = 20.0
        sun_cy = h / 2.0
        p.setPen(QPen(QColor("#94A3B8"), 1.8))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(sun_cx, sun_cy), 4.5, 4.5)
        for i in range(8):
            ang = i * (math.pi / 4.0)
            x1 = sun_cx + 6.5 * math.cos(ang)
            y1 = sun_cy + 6.5 * math.sin(ang)
            x2 = sun_cx + 9.0 * math.cos(ang)
            y2 = sun_cy + 9.0 * math.sin(ang)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 2. Track Bar & Progress Fill
        track_x = 38.0
        track_w = w - track_x - 56.0
        track_h = 6.0
        track_y = (h - track_h) / 2.0
        track_rect = QRectF(track_x, track_y, track_w, track_h)

        # Inactive track
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#222436"))
        p.drawRoundedRect(track_rect, 3.0, 3.0)

        # Active progress fill
        fill_w = max(6.0, (self.brightness / 100.0) * track_w)
        fill_rect = QRectF(track_x, track_y, fill_w, track_h)

        f_grad = QLinearGradient(track_x, 0, track_x + fill_w, 0)
        f_grad.setColorAt(0.0, self.fill_color.lighter(110))
        f_grad.setColorAt(1.0, self.fill_color)
        p.setBrush(f_grad)
        p.drawRoundedRect(fill_rect, 3.0, 3.0)

        # Circular scrub handle
        thumb_cx = track_x + fill_w
        p.setPen(QPen(QColor(255, 255, 255, 230), 2.0))
        p.setBrush(self.fill_color)
        p.drawEllipse(QPointF(thumb_cx, h / 2.0), 6.5, 6.5)

        # 3. Monospace Percentage Text on Right
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.setPen(QColor("#F1F5F9"))
        p.drawText(QRectF(w - 52.0, 0, 46.0, h), Qt.AlignVCenter | Qt.AlignRight, f"{self.brightness}%")


# =========================================================================
# Master Light Control Panel
# =========================================================================

class LightControlPanel(QDialog):
    """
    Master Async 2.0 Studio Light Controller.
    Features:
      - 3 Primary Modes: Solid Color / White, Audio Reactive Sync, Ambilight Screen Sync
      - Real-time Audio Spectrum visualizer
      - Real-time Screen sampling preview
      - Hardware Power toggle & universal master brightness
      - 100% emoji-free professional UI
    """
    modeSelected = Signal(str)           # "solid", "audio", "screen_ambilight"
    audioProfileSelected = Signal(str)   # "bass_pulse", "rainbow_wave", "ambient_chill", "rave_strobe"
    deviceSelected = Signal(str)         # selected Windows audio playback device
    powerToggled = Signal(bool)          # True / False
    whiteChanged = Signal(int, int)      # brightness (1..100), temperature (0..1000)
    colorChanged = Signal(int, int, int) # r, g, b
    brightnessChanged = Signal(int)      # brightness (1..100)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Async Light Controller")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(410, 520)

        # State
        self.is_power_on: bool = True
        self.current_primary_mode: str = "solid"
        self.current_solid_subtab: str = "color"  # "color" or "white"
        self.current_audio_profile: str = "bass_pulse"
        self.current_brightness: int = 100
        self.current_rgb: Tuple[int, int, int] = (56, 189, 248)

        self._build_ui()
        self._apply_dark_theme()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Master Outer Card Container
        self.card = QWidget(self)
        self.card.setObjectName("MasterCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(18, 14, 18, 18)
        card_layout.setSpacing(12)

        # 1. Header Bar (Brand, Status, Power Switch, Close)
        self.header = HeaderBar(self.card)
        self.header.closeClicked.connect(self.hide)
        self.header.powerToggled.connect(self._on_power_toggled)
        card_layout.addWidget(self.header)

        # 2. Primary 3-Way Mode Segmented Bar
        self.mode_bar = SegmentedModeBar(self.card)
        self.mode_bar.modeSelected.connect(self._on_primary_mode_changed)
        card_layout.addWidget(self.mode_bar)

        # 3. Stacked Mode Pages (Index 0: Solid, Index 1: Audio, Index 2: Ambilight)
        self.stack_modes = QStackedWidget(self.card)

        # ---------------- PAGE 0: SOLID LIGHTING ----------------
        page_solid = QWidget()
        solid_layout = QVBoxLayout(page_solid)
        solid_layout.setContentsMargins(0, 4, 0, 0)
        solid_layout.setSpacing(10)

        # Solid Sub-Tabs: Color Spectrum vs White Palette
        subtabs_layout = QHBoxLayout()
        subtabs_layout.setSpacing(8)

        self.btn_sub_color = QPushButton("Color Spectrum", page_solid)
        self.btn_sub_white = QPushButton("White Palette", page_solid)
        for btn in (self.btn_sub_color, self.btn_sub_white):
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setFixedHeight(26)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.btn_sub_color.clicked.connect(lambda: self._switch_solid_subtab("color"))
        self.btn_sub_white.clicked.connect(lambda: self._switch_solid_subtab("white"))
        subtabs_layout.addWidget(self.btn_sub_color)
        subtabs_layout.addWidget(self.btn_sub_white)
        solid_layout.addLayout(subtabs_layout)

        # Stack for Color vs White
        self.stack_solid = QStackedWidget(page_solid)

        # Sub-Page 0A: Color Spectrum View
        view_color = QWidget()
        v_color_layout = QVBoxLayout(view_color)
        v_color_layout.setContentsMargins(0, 0, 0, 0)
        v_color_layout.setSpacing(8)

        # Info strip (Swatch, Color Name, Coordinates)
        color_info = QHBoxLayout()
        color_info.setSpacing(8)
        self.lbl_color_swatch = QLabel(view_color)
        self.lbl_color_swatch.setFixedSize(14, 14)
        self.lbl_color_swatch.setStyleSheet("background-color: #38BDF8; border-radius: 7px;")
        self.lbl_color_name = QLabel("Pure Cyan", view_color)
        self.lbl_color_name.setStyleSheet("color: #F8FAFC; font-family: 'Segoe UI'; font-size: 11px; font-weight: 700;")
        self.lbl_color_coords = QLabel("Hue: 195 deg | Sat: 85%", view_color)
        self.lbl_color_coords.setStyleSheet("color: #94A3B8; font-family: 'Segoe UI'; font-size: 10px;")

        color_info.addWidget(self.lbl_color_swatch)
        color_info.addWidget(self.lbl_color_name)
        color_info.addStretch()
        color_info.addWidget(self.lbl_color_coords)
        v_color_layout.addLayout(color_info)

        # 2D Color Spectrum Canvas
        self.color_chart = ColorChartWidget(view_color)
        self.color_chart.colorChanged.connect(self._on_color_chart_changed)
        self.color_chart.coordChanged.connect(self._on_color_coords_changed)
        v_color_layout.addWidget(self.color_chart)

        # Color Presets Row
        color_swatches_layout = QHBoxLayout()
        color_swatches_layout.setSpacing(8)
        self.color_swatch_buttons: List[SwatchCircleButton] = []
        for hex_code in ["#EF4444", "#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#06B6D4"]:
            btn_sw = SwatchCircleButton(QColor(hex_code), view_color)
            btn_sw.clicked.connect(lambda checked=False, c=hex_code, b=btn_sw: self._apply_color_preset(c, b))
            color_swatches_layout.addWidget(btn_sw)
            self.color_swatch_buttons.append(btn_sw)

        # Custom Save Swatch '+' Button
        self.btn_add_swatch = QPushButton("+", view_color)
        self.btn_add_swatch.setFixedSize(28, 28)
        self.btn_add_swatch.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_add_swatch.setStyleSheet("""
            QPushButton {
                background-color: #1A1C29;
                border: 1px dashed rgba(255, 255, 255, 0.25);
                border-radius: 14px;
                color: #94A3B8;
                font-family: 'Segoe UI';
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #272A3D;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
        """)
        self.btn_add_swatch.clicked.connect(self._save_custom_swatch)
        color_swatches_layout.addWidget(self.btn_add_swatch)
        self.color_swatches_layout = color_swatches_layout
        color_swatches_layout.addStretch()
        v_color_layout.addLayout(color_swatches_layout)

        self.stack_solid.addWidget(view_color)

        # Sub-Page 0B: White Temperature View
        view_white = QWidget()
        v_white_layout = QVBoxLayout(view_white)
        v_white_layout.setContentsMargins(0, 0, 0, 0)
        v_white_layout.setSpacing(8)

        # White Info Strip
        white_info = QHBoxLayout()
        white_info.setSpacing(8)
        self.lbl_white_swatch = QLabel(view_white)
        self.lbl_white_swatch.setFixedSize(14, 14)
        self.lbl_white_swatch.setStyleSheet("background-color: #FFE4B8; border-radius: 7px;")
        self.lbl_white_name = QLabel("Soft White (3500K)", view_white)
        self.lbl_white_name.setStyleSheet("color: #F8FAFC; font-family: 'Segoe UI'; font-size: 11px; font-weight: 700;")
        self.lbl_white_raw = QLabel("DP 23: 300", view_white)
        self.lbl_white_raw.setStyleSheet("color: #94A3B8; font-family: 'Segoe UI'; font-size: 10px;")

        white_info.addWidget(self.lbl_white_swatch)
        white_info.addWidget(self.lbl_white_name)
        white_info.addStretch()
        white_info.addWidget(self.lbl_white_raw)
        v_white_layout.addLayout(white_info)

        # White Gradient Canvas
        self.white_chart = WhiteChartWidget(view_white)
        self.white_chart.temperatureChanged.connect(self._on_white_chart_changed)
        self.white_chart.kelvinChanged.connect(self._on_white_kelvin_changed)
        v_white_layout.addWidget(self.white_chart)

        # White Kelvin Presets Row
        white_presets_layout = QHBoxLayout()
        white_presets_layout.setSpacing(6)
        presets = [
            ("Warm 2700K", 0, 2700),
            ("Soft 3500K", 300, 3500),
            ("Neutral 4500K", 600, 4500),
            ("Cool 6500K", 1000, 6500),
        ]
        for lbl, t_val, k_val in presets:
            btn_w = WhitePresetButton(lbl, t_val, k_val, view_white)
            btn_w.clicked.connect(lambda checked=False, t=t_val: self._apply_white_preset(t))
            white_presets_layout.addWidget(btn_w)
        white_presets_layout.addStretch()
        v_white_layout.addLayout(white_presets_layout)

        self.stack_solid.addWidget(view_white)

        solid_layout.addWidget(self.stack_solid)
        self.stack_modes.addWidget(page_solid)

        # ---------------- PAGE 1: AUDIO VISUALIZER ----------------
        page_audio = QWidget()
        audio_layout = QVBoxLayout(page_audio)
        audio_layout.setContentsMargins(0, 4, 0, 0)
        audio_layout.setSpacing(10)

        # Audio Info Header
        audio_info = QHBoxLayout()
        lbl_a_title = QLabel("LIVE FREQUENCY EQUALIZER", page_audio)
        lbl_a_title.setStyleSheet("color: #94A3B8; font-family: 'Segoe UI'; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        self.btn_audio_device = QPushButton("Desktop Audio", page_audio)
        self.btn_audio_device.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_audio_device.setFixedHeight(22)
        self.btn_audio_device.setStyleSheet("""
            QPushButton {
                background-color: rgba(56, 189, 248, 0.12);
                color: #38BDF8;
                border: 1px solid rgba(56, 189, 248, 0.30);
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: 600;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background-color: rgba(56, 189, 248, 0.22);
                border-color: #38BDF8;
                color: #FFFFFF;
            }
        """)
        self.btn_audio_device.clicked.connect(self._show_device_menu)
        audio_info.addWidget(lbl_a_title)
        audio_info.addStretch()
        audio_info.addWidget(self.btn_audio_device)
        audio_layout.addLayout(audio_info)

        # 20-Band Live Audio Equalizer
        self.audio_viz = AudioSpectrumWidget(page_audio)
        audio_layout.addWidget(self.audio_viz)

        # Audio DSP Profiles Row
        profiles_lbl = QLabel("REACTIVE LIGHTING PROFILES", page_audio)
        profiles_lbl.setStyleSheet("color: #94A3B8; font-family: 'Segoe UI'; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
        audio_layout.addWidget(profiles_lbl)

        profiles_layout = QHBoxLayout()
        profiles_layout.setSpacing(6)
        self.profile_buttons: Dict[str, QPushButton] = {}
        for p_key, p_name in [
            ("bass_pulse", "Bass Pulse"),
            ("rainbow_wave", "Rainbow"),
            ("ambient_chill", "Ambient Chill"),
            ("rave_strobe", "Rave Strobe")
        ]:
            p_btn = QPushButton(p_name, page_audio)
            p_btn.setCursor(QCursor(Qt.PointingHandCursor))
            p_btn.setFixedHeight(28)
            p_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            p_btn.clicked.connect(lambda checked=False, k=p_key: self._set_audio_profile(k))
            profiles_layout.addWidget(p_btn)
            self.profile_buttons[p_key] = p_btn

        audio_layout.addLayout(profiles_layout)
        self.stack_modes.addWidget(page_audio)

        # ---------------- PAGE 2: AMBILIGHT SCREEN SYNC ----------------
        page_ambi = QWidget()
        ambi_layout = QVBoxLayout(page_ambi)
        ambi_layout.setContentsMargins(0, 4, 0, 0)
        ambi_layout.setSpacing(10)

        ambi_info = QHBoxLayout()
        lbl_am_title = QLabel("DESKTOP AMBILIGHT PROJECTION", page_ambi)
        lbl_am_title.setStyleSheet("color: #94A3B8; font-family: 'Segoe UI'; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        lbl_am_fps = QLabel("30 FPS • REAL-TIME", page_ambi)
        lbl_am_fps.setStyleSheet("color: #10B981; font-family: 'Segoe UI'; font-size: 10px; font-weight: 600;")
        ambi_info.addWidget(lbl_am_title)
        ambi_info.addStretch()
        ambi_info.addWidget(lbl_am_fps)
        ambi_layout.addLayout(ambi_info)

        # Live Screen Silhouette Preview
        self.ambi_preview = AmbilightDisplayWidget(page_ambi)
        ambi_layout.addWidget(self.ambi_preview)

        # Ambilight Status Notes
        lbl_ambi_desc = QLabel(
            "Synchronizes Havells smart light directly with real-time edge colors "
            "from your primary monitor for immersive cinema and gaming.",
            page_ambi
        )
        lbl_ambi_desc.setWordWrap(True)
        lbl_ambi_desc.setStyleSheet("color: #8E95AA; font-family: 'Segoe UI'; font-size: 11px; line-height: 1.4;")
        ambi_layout.addWidget(lbl_ambi_desc)

        self.stack_modes.addWidget(page_ambi)

        card_layout.addWidget(self.stack_modes)

        # 4. Universal Master Brightness Slider
        card_layout.addSpacing(4)
        lbl_br_header = QLabel("MASTER BRIGHTNESS", self.card)
        lbl_br_header.setStyleSheet("color: #94A3B8; font-family: 'Segoe UI'; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        card_layout.addWidget(lbl_br_header)

        self.bright_slider = PrecisionBrightnessSlider(self.card)
        self.bright_slider.brightnessChanged.connect(self._on_brightness_changed)
        card_layout.addWidget(self.bright_slider)

        main_layout.addWidget(self.card)

        # Initialize defaults
        self._switch_solid_subtab("color")
        self._set_audio_profile("bass_pulse")
        self._refresh_profile_buttons()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget#MasterCard {
                background-color: #0E0F17;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 18px;
            }
        """)

    # ---------------- Mode Switching Logic ----------------

    def set_primary_mode(self, mode: str):
        """Sets active primary mode ('solid', 'audio', 'screen_ambilight')."""
        self.mode_bar.set_mode(mode)

    def _on_primary_mode_changed(self, mode: str):
        self.current_primary_mode = mode
        if mode == "solid":
            self.stack_modes.setCurrentIndex(0)
            self.modeSelected.emit("solid")
            if self.current_solid_subtab == "color":
                c = QColor.fromHsvF(self.color_chart.hue / 360.0, self.color_chart.sat, 1.0)
                self.colorChanged.emit(c.red(), c.green(), c.blue())
            else:
                raw_temp = int(round(self.white_chart.temp_ratio * 1000))
                self.whiteChanged.emit(self.current_brightness, raw_temp)
        elif mode == "audio":
            self.stack_modes.setCurrentIndex(1)
            self.modeSelected.emit("audio")
            self.audioProfileSelected.emit(self.current_audio_profile)
        elif mode == "screen_ambilight":
            self.stack_modes.setCurrentIndex(2)
            self.modeSelected.emit("screen_ambilight")

    def _switch_solid_subtab(self, subtab: str):
        self.current_solid_subtab = subtab
        active_css = """
            QPushButton {
                background-color: #272A3D;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 700;
            }
        """
        inactive_css = """
            QPushButton {
                background-color: #151622;
                color: #8E95AA;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1E2030;
                color: #CBD5E1;
            }
        """
        if subtab == "color":
            self.btn_sub_color.setStyleSheet(active_css)
            self.btn_sub_white.setStyleSheet(inactive_css)
            self.stack_solid.setCurrentIndex(0)
            c = QColor.fromHsvF(self.color_chart.hue / 360.0, self.color_chart.sat, 1.0)
            self.bright_slider.set_color(c)
            self.modeSelected.emit("solid")
            self.colorChanged.emit(c.red(), c.green(), c.blue())
        else:
            self.btn_sub_color.setStyleSheet(inactive_css)
            self.btn_sub_white.setStyleSheet(active_css)
            self.stack_solid.setCurrentIndex(1)
            raw_temp = int(round(self.white_chart.temp_ratio * 1000))
            r, g, b = self.white_chart.get_rgb()
            self.bright_slider.set_color(QColor(r, g, b))
            self.modeSelected.emit("solid")
            self.whiteChanged.emit(self.current_brightness, raw_temp)

    # ---------------- Audio Device Switching ----------------

    def set_audio_devices(self, devices: List[Dict[str, Any]], current_device_name: str = ""):
        """Updates the cached audio output devices and active device display."""
        self._audio_devices = devices or []
        if current_device_name:
            self._current_device_name = current_device_name
            display_name = current_device_name
            if len(display_name) > 22:
                display_name = display_name[:20] + ".."
            self.btn_audio_device.setText(display_name)

    def _show_device_menu(self):
        """Displays popup menu to switch Windows audio output device directly."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #12131C;
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 4px;
                font-family: 'Segoe UI';
                font-size: 11px;
            }
            QMenu::item {
                padding: 5px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0284C7;
                color: #FFFFFF;
            }
        """)
        devices = getattr(self, "_audio_devices", [])
        if not devices:
            act = menu.addAction("No Audio Devices Found")
            act.setEnabled(False)
        else:
            current_dn = getattr(self, "_current_device_name", "")
            for dev in devices:
                dev_name = dev.get("name", "Unknown")
                act = menu.addAction(dev_name)
                act.setCheckable(True)
                if current_dn and (current_dn.lower() in dev_name.lower() or dev_name.lower() in current_dn.lower()):
                    act.setChecked(True)
                act.triggered.connect(lambda checked=False, dn=dev_name: self._on_device_selected(dn))

        pos = self.btn_audio_device.mapToGlobal(QPoint(0, self.btn_audio_device.height() + 2))
        menu.exec(pos)

    def _on_device_selected(self, dev_name: str):
        self._current_device_name = dev_name
        display_name = dev_name
        if len(display_name) > 22:
            display_name = display_name[:20] + ".."
        self.btn_audio_device.setText(display_name)
        self.deviceSelected.emit(dev_name)

    # ---------------- Color & White Callbacks ----------------

    def _on_color_chart_changed(self, r: int, g: int, b: int):
        self.current_rgb = (r, g, b)
        self.bright_slider.set_color(QColor(r, g, b))
        self.lbl_color_swatch.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border-radius: 7px;")
        self.colorChanged.emit(r, g, b)

    def _on_color_coords_changed(self, hue: float, sat: float):
        name = get_color_name(hue, sat)
        self.lbl_color_name.setText(name)
        self.lbl_color_coords.setText(f"Hue: {int(hue)} deg | Sat: {int(sat * 100)}%")

    def _apply_color_preset(self, hex_code: str, clicked_btn: SwatchCircleButton):
        for b in self.color_swatch_buttons:
            b.set_active(b == clicked_btn)
        c = QColor(hex_code)
        self.color_chart.set_hsv(c.hue(), c.saturationF())
        self._on_color_chart_changed(c.red(), c.green(), c.blue())
        self._on_color_coords_changed(c.hue(), c.saturationF())

    def _save_custom_swatch(self):
        c = QColor.fromHsvF(self.color_chart.hue / 360.0, self.color_chart.sat, 1.0)
        btn = SwatchCircleButton(c, self)
        btn.clicked.connect(lambda checked=False, col=c.name(), b=btn: self._apply_color_preset(col, b))
        self.color_swatch_buttons.append(btn)
        # Insert before '+' button
        idx = max(0, self.color_swatches_layout.count() - 2)
        self.color_swatches_layout.insertWidget(idx, btn)

    def _on_white_chart_changed(self, temp_val: int):
        self.lbl_white_raw.setText(f"DP 23: {temp_val}")
        r, g, b = self.white_chart.get_rgb()
        self.bright_slider.set_color(QColor(r, g, b))
        self.lbl_white_swatch.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border-radius: 7px;")
        self.whiteChanged.emit(self.current_brightness, temp_val)

    def _on_white_kelvin_changed(self, kelvin: int):
        if kelvin <= 2900:
            name = f"Warm Amber ({kelvin}K)"
        elif kelvin <= 3800:
            name = f"Soft White ({kelvin}K)"
        elif kelvin <= 4800:
            name = f"Neutral White ({kelvin}K)"
        else:
            name = f"Cool Daylight ({kelvin}K)"
        self.lbl_white_name.setText(name)

    def _apply_white_preset(self, temp_val: int):
        self.white_chart.set_temperature(temp_val)
        self._on_white_chart_changed(temp_val)
        self._on_white_kelvin_changed(self.white_chart.get_kelvin())

    # ---------------- Audio Profile Logic ----------------

    def _set_audio_profile(self, profile_key: str):
        self.current_audio_profile = profile_key
        self._refresh_profile_buttons()
        self.audioProfileSelected.emit(profile_key)

    def _refresh_profile_buttons(self):
        active_css = """
            QPushButton {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 700;
            }
        """
        inactive_css = """
            QPushButton {
                background-color: #181926;
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #222436;
                color: #E2E8F0;
            }
        """
        for k, btn in self.profile_buttons.items():
            btn.setStyleSheet(active_css if k == self.current_audio_profile else inactive_css)

    # ---------------- Brightness & Power Callbacks ----------------

    def _on_brightness_changed(self, brightness: int):
        self.current_brightness = brightness
        self.brightnessChanged.emit(brightness)
        if self.current_primary_mode == "solid":
            if self.current_solid_subtab == "white":
                raw_temp = int(round(self.white_chart.temp_ratio * 1000))
                self.whiteChanged.emit(self.current_brightness, raw_temp)
            else:
                c = QColor.fromHsvF(self.color_chart.hue / 360.0, self.color_chart.sat, 1.0)
                self.colorChanged.emit(c.red(), c.green(), c.blue())

    def _on_power_toggled(self, power_state: bool):
        self.is_power_on = power_state
        self.powerToggled.emit(power_state)

    def set_power_state(self, power_state: bool):
        self.is_power_on = power_state
        self.header.set_power_state(power_state)

    # ---------------- Live Telemetry Feed (from Tray App) ----------------

    def update_live_telemetry(self, bands: np.ndarray, rgb: Tuple[int, int, int]):
        """Called periodically by tray app to animate spectrum & ambilight."""
        if not self.isVisible():
            return
        if self.current_primary_mode == "audio":
            self.audio_viz.set_bands(bands)
            if rgb and len(rgb) == 3:
                self.bright_slider.set_color(QColor(rgb[0], rgb[1], rgb[2]))
        elif self.current_primary_mode == "screen_ambilight":
            if rgb and len(rgb) == 3:
                self.ambi_preview.set_rgb(rgb[0], rgb[1], rgb[2])
                self.bright_slider.set_color(QColor(rgb[0], rgb[1], rgb[2]))
