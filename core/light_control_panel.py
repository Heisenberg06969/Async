"""
Async 2.0: Interactive Light Control Panel & Dual Color/White Charts.
Provides:
  1. White Chart: Continuous temperature gradient (Warm Amber 2700K -> Neutral 4500K -> Cool Daylight 6500K)
     with draggable circular handle, value pill badge, and custom brightness slider.
  2. Color Chart: 2D Hue-Saturation spectrum with draggable circular handle,
     active color badge, preset swatches, and custom brightness slider.
  3. Master Hardware Power ON/OFF Toggle with instant live status.
  4. Quick resume buttons for Audio Reactive & Screen Ambilight sync.
  5. 100% clean typography with zero emojis.
"""

from typing import Tuple, List, Optional
import math

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QGraphicsDropShadowEffect
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QImage, QPainterPath,
    QLinearGradient, QFont, QMouseEvent, QCursor
)
from PySide6.QtCore import Qt, QPointF, QRectF, Signal


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
    """Returns clean human-readable name for a given HSV coordinate."""
    if sat < 0.15:
        return "Pastel White"
    h = hue % 360.0
    if h < 18 or h >= 345:
        return "Red"
    elif h < 45:
        return "Orange"
    elif h < 70:
        return "Yellow"
    elif h < 160:
        return "Green"
    elif h < 195:
        return "Cyan"
    elif h < 255:
        return "Blue"
    elif h < 290:
        return "Purple"
    else:
        return "Magenta"


class WhiteChartWidget(QWidget):
    """
    Continuous color temperature chart for whites only (Warm Amber to Cool Daylight).
    Renders with rounded corners, custom circular draggable handle, and temperature pill badge.
    """
    temperatureChanged = Signal(int)  # 0 (2700K Warm) to 1000 (6500K Cold)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 140)
        self.temp_ratio: float = 0.35  # 0.0 to 1.0 (corresponds to 0..1000)
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
        self.temperatureChanged.emit(int(round(self.temp_ratio * 1000)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 16.0

        # Clip to smooth rounded rect
        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip_path)

        # 1. Horizontal White Temperature Gradient
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor("#FF9D2E"))   # Warm Amber 2700K
        grad.setColorAt(0.30, QColor("#FFE4B8"))  # Soft Warm 3200K
        grad.setColorAt(0.60, QColor("#FFFFFF"))  # Neutral White 4500K
        grad.setColorAt(1.0, QColor("#BBE2FF"))   # Cool Daylight 6500K
        p.fillRect(rect, grad)

        # 2. Subtle lighting gloss overlay
        gloss = QLinearGradient(0, 0, 0, h)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 45))
        gloss.setColorAt(1.0, QColor(0, 0, 0, 30))
        p.fillRect(rect, gloss)

        # 3. Value Pill Badge in Top-Left
        kelvin = self.get_kelvin()
        badge_text = f"{int(self.temp_ratio * 1000)} ({kelvin}K)"
        font = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(font)

        badge_w = 90.0
        badge_h = 24.0
        badge_rect = QRectF(12, 12, badge_w, badge_h)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 12, 12)
        p.fillPath(badge_path, QColor(15, 23, 42, 160))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawPath(badge_path)

        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # 4. Circular Draggable Ring Handle
        handle_x = max(18.0, min(w - 18.0, self.temp_ratio * w))
        handle_y = h * 0.60

        # Soft outer shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(QPointF(handle_x, handle_y + 1), 16, 16)

        # Outer white ring
        p.setPen(QPen(QColor(255, 255, 255, 255), 3.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(handle_x, handle_y), 15, 15)

        # Subtle dark outline on outer ring for high contrast against white
        p.setPen(QPen(QColor(15, 23, 42, 80), 1.0))
        p.drawEllipse(QPointF(handle_x, handle_y), 17, 17)


class ColorChartWidget(QWidget):
    """
    2D interactive color spectrum chart for all colors.
    Horizontal X = Full Hue (0..360 deg), Vertical Y = Saturation (top pastel to bottom vibrant).
    Features circular draggable handle and active color name badge.
    """
    colorChanged = Signal(float, float, float)  # hue (0..360), sat (0..1), val (1.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 140)
        self.hue: float = 210.0   # Default Blue
        self.sat: float = 0.85
        self.val: float = 1.0
        self._cached_image: Optional[QImage] = None
        self._is_dragging: bool = False
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_hsv(self, h: float, s: float, v: float = 1.0):
        self.hue = h % 360.0
        self.sat = max(0.0, min(1.0, s))
        self.val = max(0.0, min(1.0, v))
        self.update()

    def get_rgb(self) -> Tuple[int, int, int]:
        c = QColor.fromHsvF(self.hue / 360.0, self.sat, self.val)
        return c.red(), c.green(), c.blue()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_spectrum_cache()

    def _render_spectrum_cache(self):
        w = max(1, self.width())
        h = max(1, self.height())
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)

        for y in range(h):
            # Top of chart is soft/pastel (sat=0.08), bottom is full rich saturation (sat=1.0)
            sat = 0.08 + 0.92 * (y / float(h - 1)) if h > 1 else 1.0
            for x in range(w):
                hue = (x / float(w - 1)) if w > 1 else 0.0
                col = QColor.fromHsvF(hue, sat, 1.0)
                img.setPixelColor(x, y, col)

        self._cached_image = img

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
        rx = max(0.0, min(1.0, x / w))
        ry = max(0.0, min(1.0, y / h))

        self.hue = rx * 360.0
        self.sat = 0.08 + 0.92 * ry
        self.update()
        self.colorChanged.emit(self.hue, self.sat, self.val)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = 16.0

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip_path)

        # 1. Draw Spectrum Image
        if self._cached_image is None or self._cached_image.width() != int(w) or self._cached_image.height() != int(h):
            self._render_spectrum_cache()
        if self._cached_image:
            p.drawImage(0, 0, self._cached_image)

        # 2. Pill Badge in Top-Left (Color Name)
        color_name = get_color_name(self.hue, self.sat)
        font = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(font)

        badge_w = 75.0
        badge_h = 24.0
        badge_rect = QRectF(12, 12, badge_w, badge_h)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 12, 12)
        p.fillPath(badge_path, QColor(15, 23, 42, 160))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawPath(badge_path)

        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(badge_rect, Qt.AlignCenter, color_name)

        # 3. Circular Draggable Ring Handle
        rx = self.hue / 360.0
        ry = max(0.0, min(1.0, (self.sat - 0.08) / 0.92))
        handle_x = max(18.0, min(w - 18.0, rx * w))
        handle_y = max(18.0, min(h - 18.0, ry * h))

        # Soft shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(handle_x, handle_y + 1), 16, 16)

        # Outer white ring
        p.setPen(QPen(QColor(255, 255, 255, 255), 3.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(handle_x, handle_y), 15, 15)

        # Subtle dark ring
        p.setPen(QPen(QColor(15, 23, 42, 80), 1.0))
        p.drawEllipse(QPointF(handle_x, handle_y), 17, 17)


class BrightnessSliderWidget(QWidget):
    """
    Sleek pill-shaped Brightness slider matching the user's screenshot.
    Renders custom sun vector icon, percentage text, and live color gradient fill.
    """
    brightnessChanged = Signal(int)  # 1 to 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setMinimumWidth(320)
        self.brightness: int = 100
        self.fill_color: QColor = QColor("#FF9E2C")
        self._is_dragging: bool = False
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_brightness(self, value: int):
        self.brightness = max(1, min(100, int(value)))
        self.update()

    def set_fill_color(self, color: QColor):
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
        w = max(1.0, float(self.width()))
        ratio = max(0.01, min(1.0, x / w))
        self.brightness = int(round(ratio * 100))
        self.update()
        self.brightnessChanged.emit(self.brightness)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0, 0, w, h)
        radius = h / 2.0

        # 1. Background dark pill track
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.setBrush(QColor("#202230"))
        p.drawRoundedRect(rect, radius, radius)

        # 2. Active fill gradient matching current bulb light
        fill_w = max(radius * 2.0, (self.brightness / 100.0) * w)
        fill_rect = QRectF(0, 0, fill_w, h)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip_path)

        grad = QLinearGradient(0, 0, fill_w, 0)
        c1 = QColor(self.fill_color)
        c2 = QColor(self.fill_color).darker(115)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)

        p.setPen(Qt.NoPen)
        p.fillRect(fill_rect, grad)

        # 3. Draw Clean Sun Icon on left
        p.setClipping(False)
        sun_cx = 28.0
        sun_cy = h / 2.0
        sun_color = QColor(255, 255, 255, 240)
        p.setPen(QPen(sun_color, 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(sun_cx, sun_cy), 5.5, 5.5)

        # Sun rays (8 rays)
        for i in range(8):
            angle = i * (math.pi / 4.0)
            r1 = 8.5
            r2 = 11.5
            x1 = sun_cx + r1 * math.cos(angle)
            y1 = sun_cy + r1 * math.sin(angle)
            x2 = sun_cx + r2 * math.cos(angle)
            y2 = sun_cy + r2 * math.sin(angle)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 4. Brightness Percentage Text
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 255))
        text = f"{self.brightness}%"
        p.drawText(QRectF(48, 0, 100, h), Qt.AlignVCenter | Qt.AlignLeft, text)


class SwatchCircleButton(QPushButton):
    """Circular preset color swatch chip."""
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(36, 36)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        p.setPen(QPen(QColor(255, 255, 255, 60), 1.5))
        p.setBrush(self.color)
        p.drawEllipse(rect.adjusted(2, 2, -2, -2))


class LightControlPanel(QDialog):
    """
    Master Async 2.0 Light Control Panel.
    Integrates:
      - Color Chart & White Chart in a clean tabbed view
      - Hardware Power ON/OFF Toggle
      - Brightness Controls
      - Seamless Quick-Return to Audio & Screen Ambilight Sync
      - 100% emoji-free professional UI
    """
    modeSelected = Signal(str)           # "static_white", "static_color", "screen_ambilight", "bass_pulse"
    powerToggled = Signal(bool)          # True / False
    whiteChanged = Signal(int, int)      # brightness (1..100), temperature (0..1000)
    colorChanged = Signal(int, int, int) # r, g, b

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Async Light Controller")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(400, 520)

        self.is_power_on: bool = True
        self.active_tab: str = "color"
        self.current_brightness: int = 100

        self._build_ui()
        self._apply_dark_theme()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Card container with rounded corners and OLED background
        self.card = QWidget(self)
        self.card.setObjectName("ControlCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(16)

        # 1. Top Header: Tabs (Color / White) + Power Button + Close Button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        # Tab: Color
        self.btn_tab_color = QPushButton("Color", self.card)
        self.btn_tab_color.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_tab_color.clicked.connect(lambda: self.switch_tab("color"))

        # Tab: White
        self.btn_tab_white = QPushButton("White", self.card)
        self.btn_tab_white.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_tab_white.clicked.connect(lambda: self.switch_tab("white"))

        header_layout.addWidget(self.btn_tab_color)
        header_layout.addWidget(self.btn_tab_white)
        header_layout.addStretch()

        # Hardware Power Button (ON / OFF)
        self.btn_power = QPushButton("POWER: ON", self.card)
        self.btn_power.setObjectName("PowerButton")
        self.btn_power.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_power.clicked.connect(self._toggle_power)
        header_layout.addWidget(self.btn_power)

        # Close [X] Button
        self.btn_close = QPushButton("X", self.card)
        self.btn_close.setObjectName("CloseButton")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.clicked.connect(self.hide)
        header_layout.addWidget(self.btn_close)

        card_layout.addLayout(header_layout)

        # 2. Stacked Content: Page 0 = Color, Page 1 = White
        self.stack = QStackedWidget(self.card)

        # Page 0: Color Page
        page_color = QWidget()
        page_color_layout = QVBoxLayout(page_color)
        page_color_layout.setContentsMargins(0, 0, 0, 0)
        page_color_layout.setSpacing(14)

        # Presets Row (Color)
        color_presets_layout = QHBoxLayout()
        color_presets_layout.setSpacing(10)
        for hex_col in ["#FF2244", "#00E676", "#2979FF", "#FFB300", "#D500F9"]:
            sw = SwatchCircleButton(QColor(hex_col), page_color)
            sw.clicked.connect(lambda checked=False, c=hex_col: self._apply_color_preset(c))
            color_presets_layout.addWidget(sw)

        # Plus button to add current color
        self.btn_add_color = QPushButton("+", page_color)
        self.btn_add_color.setObjectName("AddPresetButton")
        self.btn_add_color.setFixedSize(36, 36)
        self.btn_add_color.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_add_color.clicked.connect(self._add_current_color_preset)
        color_presets_layout.addWidget(self.btn_add_color)
        self.color_presets_layout = color_presets_layout

        color_presets_layout.addStretch()
        page_color_layout.addLayout(color_presets_layout)

        # 2D Color Chart
        self.color_chart = ColorChartWidget(page_color)
        self.color_chart.colorChanged.connect(self._on_color_chart_changed)
        page_color_layout.addWidget(self.color_chart)

        self.stack.addWidget(page_color)

        # Page 1: White Page
        page_white = QWidget()
        page_white_layout = QVBoxLayout(page_white)
        page_white_layout.setContentsMargins(0, 0, 0, 0)
        page_white_layout.setSpacing(14)

        # Presets Row (White)
        white_presets_layout = QHBoxLayout()
        white_presets_layout.setSpacing(10)
        white_presets = [
            ("#FFB766", 0),     # Warm Amber (2700K)
            ("#FFE4CE", 300),   # Soft White (3500K)
            ("#FFFFFF", 600),   # Neutral White (4500K)
            ("#D9EBFF", 1000)   # Cool Daylight (6500K)
        ]
        for hex_col, temp in white_presets:
            sw = SwatchCircleButton(QColor(hex_col), page_white)
            sw.clicked.connect(lambda checked=False, t=temp: self._apply_white_preset(t))
            white_presets_layout.addWidget(sw)

        self.btn_add_white = QPushButton("+", page_white)
        self.btn_add_white.setObjectName("AddPresetButton")
        self.btn_add_white.setFixedSize(36, 36)
        self.btn_add_white.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_add_white.clicked.connect(self._add_current_white_preset)
        white_presets_layout.addWidget(self.btn_add_white)
        self.white_presets_layout = white_presets_layout

        white_presets_layout.addStretch()
        page_white_layout.addLayout(white_presets_layout)

        # White Chart
        self.white_chart = WhiteChartWidget(page_white)
        self.white_chart.temperatureChanged.connect(self._on_white_chart_changed)
        page_white_layout.addWidget(self.white_chart)

        self.stack.addWidget(page_white)

        card_layout.addWidget(self.stack)

        # 3. Brightness Slider Section
        lbl_bright = QLabel("Brightness", self.card)
        lbl_bright.setObjectName("SectionHeader")
        card_layout.addWidget(lbl_bright)

        self.bright_slider = BrightnessSliderWidget(self.card)
        self.bright_slider.brightnessChanged.connect(self._on_brightness_slider_changed)
        card_layout.addWidget(self.bright_slider)

        # 4. Quick Return to Sync Modes
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(10)

        self.btn_resume_audio = QPushButton("Audio Reactive Sync", self.card)
        self.btn_resume_audio.setObjectName("SyncButton")
        self.btn_resume_audio.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_resume_audio.clicked.connect(lambda: self.modeSelected.emit("bass_pulse"))

        self.btn_resume_ambilight = QPushButton("Ambilight Screen Sync", self.card)
        self.btn_resume_ambilight.setObjectName("SyncButton")
        self.btn_resume_ambilight.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_resume_ambilight.clicked.connect(lambda: self.modeSelected.emit("screen_ambilight"))

        quick_layout.addWidget(self.btn_resume_audio)
        quick_layout.addWidget(self.btn_resume_ambilight)
        card_layout.addLayout(quick_layout)

        main_layout.addWidget(self.card)

        # Initial Tab state
        self.switch_tab("color")

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget#ControlCard {
                background-color: #141520;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
            }
            QLabel#SectionHeader {
                color: #E2E8F0;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#CloseButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                color: #94A3B8;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#CloseButton:hover {
                background-color: rgba(239, 68, 68, 0.2);
                color: #EF4444;
                border-color: #EF4444;
            }
            QPushButton#PowerButton {
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 12px;
                letter-spacing: 0.5px;
            }
            QPushButton#AddPresetButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px dashed rgba(255, 255, 255, 0.25);
                border-radius: 18px;
                color: #CBD5E1;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#AddPresetButton:hover {
                background-color: rgba(255, 255, 255, 0.18);
                color: #FFFFFF;
                border-color: #38BDF8;
            }
            QPushButton#SyncButton {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
                color: #CBD5E1;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
                padding: 8px 12px;
            }
            QPushButton#SyncButton:hover {
                background-color: rgba(56, 189, 248, 0.15);
                color: #38BDF8;
                border-color: #38BDF8;
            }
        """)
        self._update_power_button_style()

    def _update_power_button_style(self):
        if self.is_power_on:
            self.btn_power.setText("POWER: ON")
            self.btn_power.setStyleSheet("""
                QPushButton#PowerButton {
                    background-color: rgba(16, 185, 129, 0.18);
                    border: 1px solid #10B981;
                    color: #10B981;
                }
                QPushButton#PowerButton:hover {
                    background-color: rgba(16, 185, 129, 0.32);
                }
            """)
        else:
            self.btn_power.setText("POWER: OFF")
            self.btn_power.setStyleSheet("""
                QPushButton#PowerButton {
                    background-color: rgba(100, 116, 139, 0.20);
                    border: 1px solid #64748B;
                    color: #94A3B8;
                }
                QPushButton#PowerButton:hover {
                    background-color: rgba(100, 116, 139, 0.35);
                }
            """)

    def set_power_state(self, is_on: bool):
        self.is_power_on = is_on
        self._update_power_button_style()

    def _toggle_power(self):
        self.is_power_on = not self.is_power_on
        self._update_power_button_style()
        self.powerToggled.emit(self.is_power_on)

    def switch_tab(self, tab_name: str):
        self.active_tab = tab_name
        if tab_name == "color":
            self.stack.setCurrentIndex(0)
            self.btn_tab_color.setStyleSheet("""
                font-family: 'Segoe UI'; font-size: 16px; font-weight: bold;
                background: transparent; border: none; color: #00A3FF; padding: 4px 6px;
            """)
            self.btn_tab_white.setStyleSheet("""
                font-family: 'Segoe UI'; font-size: 16px; font-weight: bold;
                background: transparent; border: none; color: #94A3B8; padding: 4px 6px;
            """)
            r, g, b = self.color_chart.get_rgb()
            self.bright_slider.set_fill_color(QColor(r, g, b))
        else:
            self.stack.setCurrentIndex(1)
            self.btn_tab_white.setStyleSheet("""
                font-family: 'Segoe UI'; font-size: 16px; font-weight: bold;
                background: transparent; border: none; color: #00A3FF; padding: 4px 6px;
            """)
            self.btn_tab_color.setStyleSheet("""
                font-family: 'Segoe UI'; font-size: 16px; font-weight: bold;
                background: transparent; border: none; color: #94A3B8; padding: 4px 6px;
            """)
            r, g, b = self.white_chart.get_rgb()
            self.bright_slider.set_fill_color(QColor(r, g, b))

    def _on_color_chart_changed(self, h: float, s: float, v: float):
        r, g, b = self.color_chart.get_rgb()
        self.bright_slider.set_fill_color(QColor(r, g, b))
        self.modeSelected.emit("static_color")
        self.colorChanged.emit(r, g, b)

    def _on_white_chart_changed(self, temp: int):
        r, g, b = self.white_chart.get_rgb()
        self.bright_slider.set_fill_color(QColor(r, g, b))
        self.modeSelected.emit("static_white")
        self.whiteChanged.emit(self.current_brightness, temp)

    def _on_brightness_slider_changed(self, b: int):
        self.current_brightness = b
        if self.active_tab == "white":
            temp = int(round(self.white_chart.temp_ratio * 1000))
            self.modeSelected.emit("static_white")
            self.whiteChanged.emit(self.current_brightness, temp)
        else:
            r, g, b_val = self.color_chart.get_rgb()
            self.modeSelected.emit("static_color")
            self.colorChanged.emit(r, g, b_val)

    def _apply_color_preset(self, hex_col: str):
        c = QColor(hex_col)
        self.color_chart.set_hsv(c.hue(), c.saturationF(), 1.0)
        self.switch_tab("color")
        self._on_color_chart_changed(c.hue(), c.saturationF(), 1.0)

    def _apply_white_preset(self, temp: int):
        self.white_chart.set_temperature(temp)
        self.switch_tab("white")
        self._on_white_chart_changed(temp)

    def _add_current_color_preset(self):
        r, g, b = self.color_chart.get_rgb()
        col = QColor(r, g, b)
        sw = SwatchCircleButton(col, self)
        sw.clicked.connect(lambda checked=False, c=col.name(): self._apply_color_preset(c))
        # Insert before '+' button
        idx = self.color_presets_layout.indexOf(self.btn_add_color)
        self.color_presets_layout.insertWidget(idx, sw)

    def _add_current_white_preset(self):
        temp = int(round(self.white_chart.temp_ratio * 1000))
        r, g, b = self.white_chart.get_rgb()
        col = QColor(r, g, b)
        sw = SwatchCircleButton(col, self)
        sw.clicked.connect(lambda checked=False, t=temp: self._apply_white_preset(t))
        idx = self.white_presets_layout.indexOf(self.btn_add_white)
        self.white_presets_layout.insertWidget(idx, sw)
