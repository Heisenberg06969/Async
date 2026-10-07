"""
Async 2.0: Windows System Tray Application.
Provides a completely frictionless, zero-terminal background experience:
  - Lives silently in the Windows System Tray (notification area near the clock).
  - Dynamic tray icon glows in real time with the active smart light color.
  - Left-Click: Instantly toggles between Screen Ambilight and Audio Reactive sync.
  - Right-Click: Native Windows menu for modes, algorithms, audio device switcher,
    strobe boost, power toggle, and Windows startup auto-run.
  - Double-Click: Opens the 60 FPS Room Simulator in browser on demand (no auto-open).
  - Zero terminal popup: Runs windowless via pythonw.exe or Async.vbs.
"""

import os
import sys
import time
import json
import logging
import threading
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import numpy as np

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QAction, QActionGroup, QFont
)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from core.audio_capture import AudioCapture
from core.dsp_engine import DSPEngine
from core.color_mapper import ColorMapper
from core.screen_sync import ScreenSyncEngine
from core.media_session import WindowsMediaSession
from drivers.tuya_driver import HavellsLocalBulb
from web.server import AsyncWebServer
from core.light_control_panel import LightControlPanel, kelvin_to_rgb

# Headless stdout/stderr protection when launched via pythonw.exe
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Configure logging to file when running headless
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "async_tray.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Async.Tray")

def uncaught_exception_handler(exc_type, exc_val, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_val, exc_tb)
        return
    logger.critical("Uncaught Exception in Async Tray App:", exc_info=(exc_type, exc_val, exc_tb))

sys.excepthook = uncaught_exception_handler

CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
    return {
        "bulb": {
            "ip": "192.168.0.51",
            "device_id": "d7e976ee92d693ac5c6e6u",
            "local_key": "",
            "version": 3.3
        },
        "audio": {"bands": 24, "chunk_size": 1024, "gravity": 0.82},
        "visuals": {"mode": "bass_pulse", "bar_coloring": "bulb"}
    }

def get_startup_vbs_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Async.vbs"

def is_startup_enabled() -> bool:
    return get_startup_vbs_path().exists()

def set_startup_enabled(enable: bool):
    vbs_path = get_startup_vbs_path()
    if enable:
        vbs_path.parent.mkdir(parents=True, exist_ok=True)
        script_dir = Path(__file__).parent.resolve()
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        content = (
            'Set WshShell = CreateObject("WScript.Shell")\r\n'
            f'WshShell.CurrentDirectory = "{script_dir}"\r\n'
            f'WshShell.Run """{pythonw}"" ""{script_dir / "app_tray.py"}""", 0, False\r\n'
        )
        try:
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Registered Windows startup launcher at {vbs_path}")
        except Exception as e:
            logger.error(f"Failed to write startup VBS: {e}")
    else:
        if vbs_path.exists():
            try:
                vbs_path.unlink()
                logger.info(f"Removed Windows startup launcher from {vbs_path}")
            except Exception as e:
                logger.error(f"Failed to remove startup VBS: {e}")

def create_orb_icon(r: int, g: int, b: int, is_connected: bool = True, is_strobe: bool = False, is_light_on: bool = True) -> QIcon:
    """Generates an antialiased glowing orb icon for the system tray matching the light's current live state."""
    size = 32
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    if not is_light_on:
        # Dim off state
        halo = QColor(100, 116, 139, 40)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(2, 2, size - 4, size - 4)

        core = QColor(71, 85, 105, 180)
        p.setBrush(QBrush(core))
        p.drawEllipse(6, 6, size - 12, size - 12)
    else:
        # Outer luminous ambient halo
        halo_alpha = 90 if is_connected else 25
        halo = QColor(r, g, b, halo_alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(2, 2, size - 4, size - 4)

        # Inner solid vibrant core
        core_alpha = 255 if is_connected else 120
        core = QColor(r, g, b, core_alpha)
        p.setBrush(QBrush(core))
        p.drawEllipse(6, 6, size - 12, size - 12)

    # Mini badge dot (bottom-right): Purple=Strobe active, Green=Connected, Red=Disconnected
    if is_strobe:
        badge_col = QColor(244, 63, 94) # Rose / Neon flash
    elif is_connected:
        badge_col = QColor(74, 222, 128) # Emerald Green
    else:
        badge_col = QColor(239, 68, 68) # Red offline
    
    p.setBrush(QBrush(badge_col))
    p.setPen(QPen(QColor(15, 23, 42), 1.5))
    p.drawEllipse(size - 10, size - 10, 8, 8)

    p.end()
    return QIcon(pix)

class AsyncTrayApp(QObject):
    state_updated = Signal()

    def __init__(self, app: QApplication, local_server: Optional[QLocalServer] = None):
        super().__init__()
        self.app = app
        self.local_server = local_server
        if self.local_server:
            self.local_server.newConnection.connect(self._on_duplicate_instance)
        self.config = load_config()

        bulb_cfg = self.config.get("bulb", {})
        audio_cfg = self.config.get("audio", {})
        visuals_cfg = self.config.get("visuals", {})

        self.num_bands = audio_cfg.get("bands", 24)
        self.chunk_size = audio_cfg.get("chunk_size", 1024)
        self.gravity = audio_cfg.get("gravity", 0.82)
        self.initial_mode = visuals_cfg.get("mode", "bass_pulse")

        # Hardware Light Power State
        self.light_power: bool = True

        # Initialize Core Engines
        self.audio = AudioCapture(chunk_size=self.chunk_size)
        self.dsp = DSPEngine(num_bands=self.num_bands, chunk_size=self.chunk_size, gravity=self.gravity)
        self.mapper = ColorMapper(mode=self.initial_mode)
        self.screen_sync = ScreenSyncEngine(target_fps=30, smoothing=0.28, letterbox_crop=True, strobe_boost=True)
        self.media = WindowsMediaSession()

        self.bulb = HavellsLocalBulb(
            device_id=bulb_cfg.get("device_id", ""),
            ip_address=bulb_cfg.get("ip", ""),
            local_key=bulb_cfg.get("local_key", ""),
            version=bulb_cfg.get("version", 3.3)
        )

        # Shared Engine State
        self.current_rgb: Tuple[int, int, int] = (132, 209, 10)
        self.current_hsv: Tuple[float, float, float] = (83.0, 95.0, 82.0)
        self.current_bands = np.zeros(self.num_bands, dtype=np.float32)
        self.latest_metrics: Dict[str, Any] = {}
        self.devices_refresh_flag = [True]
        self.speaker_devices_cache = []
        self._lock = threading.Lock()
        self._is_running = True
        self.control_panel: Optional[LightControlPanel] = None
        self.current_sync_mode: str = self.initial_mode
        self.master_brightness: int = 100

        # Initialize Web Server (runs in background for on-demand simulator)
        self.web_server = AsyncWebServer(port=5050, on_command=self._handle_web_command)
        self.web_server.start()

        # Start Engines
        self.screen_sync.start()
        if self.mapper.mode == "screen_ambilight":
            self.screen_sync.enable()
        self.media.start()

        try:
            self.audio.start()
            self.dsp.set_sample_rate(self.audio.sample_rate)
        except Exception as e:
            logger.error(f"Error starting audio capture: {e}")

        # Start Background Engine Thread (Audio capture & Bulb transmission)
        self.worker_thread = threading.Thread(target=self._engine_loop, name="AsyncTrayWorker", daemon=True)
        self.worker_thread.start()

        # Initialize System Tray
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_menu = QMenu()

        # Tray Icon Style: Default to official brand logo
        self.icon_style = "brand"  # "brand" or "orb"
        self._current_tray_style = None

        self.brand_icon_path = Path(__file__).parent / "assets" / "icon.ico"
        if not self.brand_icon_path.exists():
            self.brand_icon_path = Path(__file__).parent / "assets" / "tray_icon_32.png"

        if self.brand_icon_path.exists():
            self.brand_icon = QIcon(str(self.brand_icon_path))
        else:
            self.brand_icon = None

        self._build_tray_menu()

        # Initial icon
        if self.brand_icon and not self.brand_icon.isNull():
            self.tray_icon.setIcon(self.brand_icon)
            self._current_tray_style = "brand"
        else:
            initial_icon = create_orb_icon(132, 209, 10, self.bulb.is_connected, False, self.light_power)
            self.tray_icon.setIcon(initial_icon)
            self._current_tray_style = "orb"

        self.tray_icon.setToolTip("Async 2.0: Room Lighting Sync\nLeft-click: Toggle Ambilight\nRight-click: Menu")

        # Hook tray interactions
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # UI Refresh Timer (Refreshes icon glow and status tooltip at 10 FPS)
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(100)
        self.ui_timer.timeout.connect(self._refresh_tray_state)
        self.ui_timer.start()

        # Telemetry Timer (Feeds real-time FFT spectrum & monitor preview to panel at 30 FPS)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.setInterval(33)
        self.telemetry_timer.timeout.connect(self._on_telemetry_tick)
        self.telemetry_timer.start()
        # Initial startup confirmation toast
        self.tray_icon.showMessage(
            "Async 2.0",
            "Running silently in your System Tray.\nLeft-Click: Toggle Ambilight | Right-Click: Menu",
            QSystemTrayIcon.Information,
            3000
        )

        logger.info("Async 2.0 System Tray successfully initialized.")

    def _on_duplicate_instance(self):
        """Called when a user attempts to launch a second instance of the app."""
        if self.local_server:
            conn = self.local_server.nextPendingConnection()
            if conn:
                conn.disconnectFromServer()
        self.tray_icon.showMessage(
            "Async 2.0",
            "Async is already running in your System Tray!\nLeft-click the glowing icon to toggle Ambilight.",
            QSystemTrayIcon.Information,
            3000
        )

    def _handle_web_command(self, cmd: dict):
        action = cmd.get("action")
        if action == "set_mode":
            new_mode = cmd.get("mode")
            if new_mode in self.mapper.MODES:
                self.mapper.set_mode(new_mode)
                if new_mode == "screen_ambilight":
                    self.screen_sync.enable()
                else:
                    self.screen_sync.disable()
        elif action == "toggle_ambilight":
            self._toggle_ambilight()
        elif action == "set_ambilight":
            enabled = bool(cmd.get("enabled", True))
            if enabled:
                self.mapper.set_mode("screen_ambilight")
                self.screen_sync.enable()
            else:
                target = getattr(self.mapper, "_last_audio_mode", "bass_pulse")
                self.mapper.set_mode(target)
                self.screen_sync.disable()
        elif action == "set_algorithm":
            new_algo = cmd.get("algorithm")
            if new_algo in self.mapper.ALGORITHMS:
                self.mapper.set_algorithm(new_algo)
        elif action == "set_audio_source":
            new_src = cmd.get("source")
            if new_src in self.audio.SOURCES:
                self.audio.switch_source(new_src)
                self.dsp.set_sample_rate(self.audio.sample_rate)
                self.dsp.reset()
                self.devices_refresh_flag[0] = True
        elif action == "set_speaker_device":
            target_dev = cmd.get("device")
            self.audio.select_speaker_device(target_dev)
            self.dsp.set_sample_rate(self.audio.sample_rate)
            self.dsp.reset()
            self.devices_refresh_flag[0] = True
        elif action == "set_bass_flash":
            self.mapper.set_bass_flash(cmd.get("enabled", True))
        elif action == "set_flash_intensity":
            self.mapper.set_flash_intensity(float(cmd.get("intensity", 1.0)))
        elif action == "set_flash_threshold":
            self.dsp.set_kick_threshold(float(cmd.get("threshold", 0.38)))
        elif action == "set_flash_style":
            self.mapper.set_flash_style(cmd.get("style", "white_flare"))
        elif action == "trigger_flash":
            self.mapper.trigger_flash(float(cmd.get("intensity", 1.0)))
        elif action == "set_strobe_boost":
            self.screen_sync.set_strobe_boost(cmd.get("enabled", True))
        elif action == "set_strobe_sensitivity":
            self.screen_sync.set_strobe_sensitivity(float(cmd.get("sensitivity", 0.16)))
        elif action == "set_strobe_floor":
            self.screen_sync.set_strobe_floor(float(cmd.get("floor", 0.26)))
        elif action == "media_play_pause":
            self.media.toggle_play_pause()
        elif action == "media_next":
            self.media.next_track()
        elif action == "media_previous":
            self.media.previous_track()

    def _build_tray_menu(self):
        """Constructs the native Windows right-click tray menu (100% emoji-free)."""
        self.tray_menu.clear()

        # 1. Status Header
        self.act_status = QAction("Async 2.0 (Connecting...)", self.tray_menu)
        font = QFont()
        font.setBold(True)
        self.act_status.setFont(font)
        self.act_status.setEnabled(False)
        self.tray_menu.addAction(self.act_status)

        self.tray_menu.addSeparator()

        # 2. Open Light Controls (White Chart, Color Chart, Power ON/OFF)
        act_open_controls = QAction("Color & White Controls...", self.tray_menu)
        act_open_controls.triggered.connect(self.show_control_panel)
        font_ctrl = QFont()
        font_ctrl.setBold(True)
        act_open_controls.setFont(font_ctrl)
        self.tray_menu.addAction(act_open_controls)

        # 3. Light Power Toggle
        self.act_power = QAction(f"Light Power: {'ON' if self.light_power else 'OFF'}", self.tray_menu)
        self.act_power.setCheckable(True)
        self.act_power.setChecked(self.light_power)
        self.act_power.toggled.connect(self._on_toggle_power)
        self.tray_menu.addAction(self.act_power)

        self.tray_menu.addSeparator()

        # 4. Ambilight Screen Sync Toggle
        self.act_ambilight = QAction("Ambilight Screen Sync", self.tray_menu)
        self.act_ambilight.setCheckable(True)
        self.act_ambilight.setChecked(self.mapper.mode == "screen_ambilight")
        self.act_ambilight.toggled.connect(self._on_toggle_ambilight_action)
        self.tray_menu.addAction(self.act_ambilight)

        # 5. Fast-Edit Strobe Boost Toggle
        self.act_strobe = QAction("Fast-Edit Strobe Boost", self.tray_menu)
        self.act_strobe.setCheckable(True)
        self.act_strobe.setChecked(self.screen_sync.strobe_boost)
        self.act_strobe.toggled.connect(lambda chk: self.screen_sync.set_strobe_boost(chk))
        self.tray_menu.addAction(self.act_strobe)

        # 6. Bass Flash Toggle
        self.act_flash = QAction("Bass Flash on Kicks", self.tray_menu)
        self.act_flash.setCheckable(True)
        self.act_flash.setChecked(self.mapper.bass_flash_enabled)
        self.act_flash.toggled.connect(lambda chk: self.mapper.set_bass_flash(chk))
        self.tray_menu.addAction(self.act_flash)

        self.tray_menu.addSeparator()

        # 7. Lighting Modes Submenu
        modes_menu = self.tray_menu.addMenu("Lighting Modes")
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)

        mode_defs = [
            ("Beat Flare (Bass Reactive)", "bass_pulse"),
            ("Rainbow Wave (Continuous)", "rainbow_wave"),
            ("Ambient Chill (Breathing)", "ambient_chill"),
            ("Rave Strobe (Club Flash)", "rave_strobe")
        ]
        self.mode_actions = {}
        for label, m_key in mode_defs:
            act = QAction(label, modes_menu)
            act.setCheckable(True)
            if self.mapper.mode == m_key:
                act.setChecked(True)
            act.triggered.connect(lambda checked, mk=m_key: self._set_audio_mode(mk))
            self.mode_group.addAction(act)
            modes_menu.addAction(act)
            self.mode_actions[m_key] = act

        # 8. Decision Algorithms Submenu
        algos_menu = self.tray_menu.addMenu("Music Algorithms")
        self.algo_group = QActionGroup(self)
        self.algo_group.setExclusive(True)

        algo_defs = [
            ("Harmonic Flow (Melody)", "harmonic_flow"),
            ("Timbre Warmth (Centroid)", "spectral_centroid"),
            ("Chroma Pitch (Circle of 5ths)", "chroma_pitch"),
            ("RGB Physics (Wave bands)", "rgb_projection")
        ]
        self.algo_actions = {}
        for label, a_key in algo_defs:
            act = QAction(label, algos_menu)
            act.setCheckable(True)
            if self.mapper.algorithm == a_key:
                act.setChecked(True)
            act.triggered.connect(lambda checked, ak=a_key: self.mapper.set_algorithm(ak))
            self.algo_group.addAction(act)
            algos_menu.addAction(act)
            self.algo_actions[a_key] = act

        # 9. Audio Output Device Submenu
        self.devices_menu = self.tray_menu.addMenu("Audio Device")
        self._populate_audio_devices_menu()

        self.tray_menu.addSeparator()

        # 10. Tray Icon Style Submenu
        icon_menu = self.tray_menu.addMenu("Tray Icon Style")
        self.act_style_brand = QAction("Official Async Logo", icon_menu)
        self.act_style_brand.setCheckable(True)
        self.act_style_brand.setChecked(self.icon_style == "brand")
        self.act_style_brand.triggered.connect(lambda: self._set_icon_style("brand"))

        self.act_style_orb = QAction("Dynamic Live RGB Orb", icon_menu)
        self.act_style_orb.setCheckable(True)
        self.act_style_orb.setChecked(self.icon_style == "orb")
        self.act_style_orb.triggered.connect(lambda: self._set_icon_style("orb"))

        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        style_group.addAction(self.act_style_brand)
        style_group.addAction(self.act_style_orb)

        icon_menu.addAction(self.act_style_brand)
        icon_menu.addAction(self.act_style_orb)

        # 11. Open Room Simulator
        act_open_sim = QAction("Open Room Simulator (Web)", self.tray_menu)
        act_open_sim.triggered.connect(self._open_web_simulator)
        self.tray_menu.addAction(act_open_sim)

        # 12. Run on Windows Startup Toggle
        self.act_startup = QAction("Run on Windows Startup", self.tray_menu)
        self.act_startup.setCheckable(True)
        self.act_startup.setChecked(is_startup_enabled())
        self.act_startup.toggled.connect(lambda chk: set_startup_enabled(chk))
        self.tray_menu.addAction(self.act_startup)

        self.tray_menu.addSeparator()

        # 13. Exit
        act_exit = QAction("Exit Async", self.tray_menu)
        act_exit.triggered.connect(self.quit_app)
        self.tray_menu.addAction(act_exit)

        self.tray_icon.setContextMenu(self.tray_menu)

    def _populate_audio_devices_menu(self):
        """Populates the Audio Device submenu with Windows audio output endpoints."""
        self.devices_menu.clear()
        devices = self.audio.get_speaker_devices()
        current_name = self.audio.get_clean_device_name()

        group = QActionGroup(self)
        group.setExclusive(True)

        for dev in devices:
            dev_name = dev["name"]
            act = QAction(dev_name, self.devices_menu)
            act.setCheckable(True)
            if dev_name.lower() in current_name.lower() or current_name.lower() in dev_name.lower():
                act.setChecked(True)
            act.triggered.connect(lambda checked, dn=dev_name: self._select_audio_device(dn))
            group.addAction(act)
            self.devices_menu.addAction(act)

        if self.control_panel:
            self.control_panel.set_audio_devices(devices, current_name)

    def _select_audio_device(self, dev_name: str):
        self.audio.select_speaker_device(dev_name)
        self.dsp.set_sample_rate(self.audio.sample_rate)
        self.dsp.reset()
        self._populate_audio_devices_menu()
        if self.control_panel:
            self.control_panel.set_audio_devices(self.speaker_devices_cache or self.audio.get_speaker_devices(), dev_name)
        self.tray_icon.showMessage("Async Audio", f"Switched to: {dev_name}", QSystemTrayIcon.Information, 1200)

    def _on_toggle_power(self, checked: bool):
        self.light_power = checked
        self.bulb.set_power(checked)
        if self.control_panel:
            self.control_panel.set_power_state(checked)
        if hasattr(self, "act_power"):
            self.act_power.setText(f"Light Power: {'ON' if checked else 'OFF'}")
            self.act_power.setChecked(checked)
        status_msg = "Light Power: ON" if checked else "Light Power: OFF"
        self.tray_icon.showMessage("Async 2.0", status_msg, QSystemTrayIcon.Information, 1000)

    def _on_white_changed(self, brightness: int, temp: int):
        self.current_sync_mode = "static_white"
        self.bulb.set_white(brightness, temp)
        r, g, b = kelvin_to_rgb(int(2700 + (temp / 1000.0) * (6500 - 2700)))
        scale = max(0.05, brightness / 100.0)
        with self._lock:
            self.current_rgb = (int(r * scale), int(g * scale), int(b * scale))

    def _on_color_changed(self, r: int, g: int, b: int):
        self.current_sync_mode = "static_color"
        c = QColor(r, g, b)
        hue = float(c.hue()) if c.hue() >= 0 else 0.0
        sat = float(c.saturationF() * 100.0)
        val = float(self.control_panel.current_brightness if self.control_panel else 100)
        self.bulb.set_hsv(hue, sat, val)
        with self._lock:
            scale = val / 100.0
            self.current_rgb = (int(r * scale), int(g * scale), int(b * scale))
            self.current_hsv = (hue, sat, val)

    def _on_mode_selected(self, mode: str):
        if mode == "solid":
            self.screen_sync.disable()
            self.act_ambilight.setChecked(False)
            if self.control_panel:
                if self.control_panel.current_solid_subtab == "white":
                    self.current_sync_mode = "static_white"
                    raw_temp = int(round(self.control_panel.white_chart.temp_ratio * 1000))
                    self.bulb.set_white(self.control_panel.current_brightness, raw_temp)
                else:
                    self.current_sync_mode = "static_color"
                    c = QColor.fromHsvF(self.control_panel.color_chart.hue / 360.0, self.control_panel.color_chart.sat, 1.0)
                    self.bulb.set_hsv(self.control_panel.color_chart.hue, self.control_panel.color_chart.sat * 100.0, float(self.control_panel.current_brightness))
            self.tray_icon.showMessage("Async 2.0", "Solid Light Mode Active", QSystemTrayIcon.Information, 1000)
        elif mode == "audio":
            self.screen_sync.disable()
            self.act_ambilight.setChecked(False)
            target = getattr(self.control_panel, "current_audio_profile", "bass_pulse") if self.control_panel else "bass_pulse"
            self.current_sync_mode = target
            self.mapper.set_mode(target)
            if target in self.mode_actions:
                self.mode_actions[target].setChecked(True)
            with self._lock:
                hsv = self.current_hsv
            scale = max(0.01, self.master_brightness / 100.0)
            scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
            self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
            self.tray_icon.showMessage("Async 2.0", f"Audio Sync: {target.replace('_', ' ').title()}", QSystemTrayIcon.Information, 1000)
        elif mode == "screen_ambilight":
            self.current_sync_mode = "screen_ambilight"
            self.mapper.set_mode("screen_ambilight")
            self.screen_sync.enable()
            self.act_ambilight.setChecked(True)
            _, hsv = self.screen_sync.get_color()
            scale = max(0.01, self.master_brightness / 100.0)
            scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
            self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
            self.tray_icon.showMessage("Async 2.0", "Ambilight ON (Screen Sync)", QSystemTrayIcon.Information, 1000)

    def _on_audio_profile_selected(self, profile: str):
        self.screen_sync.disable()
        self.act_ambilight.setChecked(False)
        self.current_sync_mode = profile
        self.mapper.set_mode(profile)
        if profile in self.mode_actions:
            self.mode_actions[profile].setChecked(True)
        with self._lock:
            hsv = self.current_hsv
        scale = max(0.01, self.master_brightness / 100.0)
        scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
        self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
        self.tray_icon.showMessage("Async 2.0", f"Profile: {profile.replace('_', ' ').title()}", QSystemTrayIcon.Information, 1000)

    def _on_brightness_changed(self, brightness: int):
        self.master_brightness = brightness
        if self.current_sync_mode == "static_white":
            if self.control_panel:
                temp = int(round(self.control_panel.white_chart.temp_ratio * 1000))
                self.bulb.set_white(brightness, temp)
        elif self.current_sync_mode == "static_color":
            if self.control_panel:
                h = self.control_panel.color_chart.hue
                s = self.control_panel.color_chart.sat * 100.0
                self.bulb.set_hsv(h, s, float(brightness))

    def _on_telemetry_tick(self):
        if self.control_panel and self.control_panel.isVisible():
            with self._lock:
                bands = self.current_bands.copy()
                rgb = self.current_rgb
            self.control_panel.update_live_telemetry(bands, rgb)
            self.control_panel.header.set_connected_state(self.bulb.is_connected)

    def show_control_panel(self):
        """Displays the sleek OLED Light Control Panel."""
        if self.control_panel is None:
            self.control_panel = LightControlPanel()
            self.control_panel.powerToggled.connect(self._on_toggle_power)
            self.control_panel.whiteChanged.connect(self._on_white_changed)
            self.control_panel.colorChanged.connect(self._on_color_changed)
            self.control_panel.modeSelected.connect(self._on_mode_selected)
            self.control_panel.audioProfileSelected.connect(self._on_audio_profile_selected)
            self.control_panel.deviceSelected.connect(self._select_audio_device)
            self.control_panel.brightnessChanged.connect(self._on_brightness_changed)

        if self.control_panel.isVisible():
            self.control_panel.hide()
            return

        # Synchronize UI state with current active app mode
        if self.current_sync_mode == "screen_ambilight":
            self.control_panel.set_primary_mode("screen_ambilight")
        elif self.current_sync_mode == "static_white":
            self.control_panel.set_primary_mode("solid")
            self.control_panel._switch_solid_subtab("white")
        elif self.current_sync_mode == "static_color":
            self.control_panel.set_primary_mode("solid")
            self.control_panel._switch_solid_subtab("color")
        else:
            self.control_panel.set_primary_mode("audio")
            if hasattr(self.control_panel, "_set_audio_profile"):
                self.control_panel._set_audio_profile(self.current_sync_mode)

        self.control_panel.set_audio_devices(
            self.speaker_devices_cache or self.audio.get_speaker_devices(),
            self.audio.get_clean_device_name()
        )
        self.control_panel.set_power_state(self.light_power)
        self.control_panel.header.set_connected_state(self.bulb.is_connected)

        screen = QApplication.primaryScreen().availableGeometry()
        x = max(10, screen.right() - self.control_panel.width() - 16)
        y = max(10, screen.bottom() - self.control_panel.height() - 16)
        self.control_panel.move(x, y)
        self.control_panel.show()
        self.control_panel.raise_()
        self.control_panel.activateWindow()

    def _on_toggle_ambilight_action(self, checked: bool):
        if checked:
            if self.mapper.mode != "screen_ambilight":
                self.mapper._last_audio_mode = self.mapper.mode
            self.current_sync_mode = "screen_ambilight"
            self.mapper.set_mode("screen_ambilight")
            self.screen_sync.enable()
            if self.control_panel:
                self.control_panel.set_primary_mode("screen_ambilight")
            _, hsv = self.screen_sync.get_color()
            scale = max(0.01, self.master_brightness / 100.0)
            scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
            self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
            self.tray_icon.showMessage("Async 2.0", "Ambilight ON (Screen Sync)", QSystemTrayIcon.Information, 1200)
        else:
            target = getattr(self.mapper, "_last_audio_mode", "bass_pulse")
            self.current_sync_mode = target
            self.mapper.set_mode(target)
            self.screen_sync.disable()
            if self.control_panel:
                self.control_panel.set_primary_mode("audio")
                if hasattr(self.control_panel, "_set_audio_profile"):
                    self.control_panel._set_audio_profile(target)
            with self._lock:
                hsv = self.current_hsv
            scale = max(0.01, self.master_brightness / 100.0)
            scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
            self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
            self.tray_icon.showMessage("Async 2.0", f"Audio Sync: {target.upper()}", QSystemTrayIcon.Information, 1200)

    def _toggle_ambilight(self):
        """Toggles Ambilight and syncs menu checkmark state."""
        is_on = self.mapper.toggle_ambilight()
        if is_on:
            self.current_sync_mode = "screen_ambilight"
            self.screen_sync.enable()
            self.act_ambilight.setChecked(True)
            if self.control_panel:
                self.control_panel.set_primary_mode("screen_ambilight")
            _, hsv = self.screen_sync.get_color()
            scale = max(0.01, self.master_brightness / 100.0)
            scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
            self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
            self.tray_icon.showMessage("Async 2.0", "Ambilight ON (Screen Sync)", QSystemTrayIcon.Information, 1200)
        else:
            self.screen_sync.disable()
            self.act_ambilight.setChecked(False)
            target = getattr(self.mapper, "_last_audio_mode", "bass_pulse")
            self.current_sync_mode = target
            if self.control_panel:
                self.control_panel.set_primary_mode("audio")
                if hasattr(self.control_panel, "_set_audio_profile"):
                    self.control_panel._set_audio_profile(target)
            with self._lock:
                hsv = self.current_hsv
            scale = max(0.01, self.master_brightness / 100.0)
            scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
            self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
            self.tray_icon.showMessage("Async 2.0", f"Audio Sync: {target.upper()}", QSystemTrayIcon.Information, 1200)

    def _set_audio_mode(self, mode: str):
        self.current_sync_mode = mode
        self.mapper.set_mode(mode)
        self.screen_sync.disable()
        self.act_ambilight.setChecked(False)
        if self.control_panel:
            self.control_panel.set_primary_mode("audio")
            if hasattr(self.control_panel, "_set_audio_profile"):
                self.control_panel._set_audio_profile(mode)
        with self._lock:
            hsv = self.current_hsv
        scale = max(0.01, self.master_brightness / 100.0)
        scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
        self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)
        self.tray_icon.showMessage("Async 2.0", f"Mode: {mode.replace('_', ' ').title()}", QSystemTrayIcon.Information, 1200)

    def _open_web_simulator(self):
        """Opens the full-screen browser room simulator on demand."""
        try:
            webbrowser.open("http://localhost:5050")
        except Exception as e:
            logger.error(f"Failed to open web browser: {e}")

    def _set_icon_style(self, style: str):
        """Switches between Official Brand Logo and Live Dynamic RGB Orb in system tray."""
        self.icon_style = style
        if style == "brand":
            if self.brand_icon and not self.brand_icon.isNull():
                self.tray_icon.setIcon(self.brand_icon)
            self._current_tray_style = "brand"
            self.tray_icon.showMessage("Async 2.0", "Tray Icon: Official Async Logo", QSystemTrayIcon.Information, 1000)
        else:
            with self._lock:
                r, g, b = self.current_rgb
            icon = create_orb_icon(r, g, b, self.bulb.is_connected, self.screen_sync.is_strobe_active, self.light_power)
            self.tray_icon.setIcon(icon)
            self._current_tray_style = "orb"
            self.tray_icon.showMessage("Async 2.0", "Tray Icon: Live Dynamic RGB Orb", QSystemTrayIcon.Information, 1000)

    def _on_tray_activated(self, reason):
        """Handles mouse clicks on the system tray icon."""
        if reason == QSystemTrayIcon.Trigger:
            # Single Left-Click: Open or toggle Light Control Panel
            self.show_control_panel()
        elif reason == QSystemTrayIcon.DoubleClick:
            # Double Click: Open Room Simulator Dashboard
            self._open_web_simulator()

    def _engine_loop(self):
        """High-performance 60 FPS audio/screen capture & bulb transmission worker."""
        speaker_devices_timer = 0.0
        stream_health_timer = 0.0
        last_track_key = ""

        while self._is_running:
            t0 = time.time()

            # 1. Capture & Process Audio / Screen
            chunk = self.audio.read_chunk(timeout=0.015)
            if chunk is not None:
                bands, metrics = self.dsp.process(chunk)
            else:
                bands = np.zeros(self.num_bands, dtype=np.float32)
                metrics = {
                    "bass": 0.0, "mid": 0.0, "treble": 0.0, "is_kick": False,
                    "spectral_centroid": 1000.0, "dominant_note": "-", "note_idx": 0
                }

            if self.mapper.mode == "screen_ambilight":
                rgb, hsv = self.screen_sync.get_color()
            else:
                rgb, hsv = self.mapper.update(metrics)

            with self._lock:
                if self.current_sync_mode not in ("static_white", "static_color"):
                    self.current_rgb = rgb
                    self.current_hsv = hsv
                self.current_bands = bands
                self.latest_metrics = metrics
                broadcast_rgb = self.current_rgb
                broadcast_hsv = self.current_hsv

            # 2. Transmit to Bulb if Light Power is ON
            if self.light_power:
                if self.current_sync_mode not in ("static_white", "static_color"):
                    scale = max(0.01, self.master_brightness / 100.0)
                    scaled_v = max(1.0, min(100.0, float(hsv[2]) * scale))
                    self.bulb.set_hsv(hsv[0], hsv[1], scaled_v)

            # 3. Broadcast to Web Room Simulator
            now = time.time()
            if now - stream_health_timer >= 3.0:
                self.audio.check_stream_health()
                stream_health_timer = now

            if now - speaker_devices_timer >= 2.5 or self.devices_refresh_flag[0]:
                self.speaker_devices_cache = self.audio.get_speaker_devices()
                speaker_devices_timer = now
                self.devices_refresh_flag[0] = False

            media_state = self.media.get_state()
            track_key = f"{media_state.get('title')}_{media_state.get('artist')}"
            send_thumb = (track_key != last_track_key)
            if send_thumb:
                last_track_key = track_key

            self.web_server.broadcast({
                "rgb": broadcast_rgb,
                "hsv": [round(broadcast_hsv[0], 1), round(broadcast_hsv[1], 1), round(broadcast_hsv[2], 1)],
                "bands": [round(float(b), 3) for b in bands],
                "mode": self.mapper.mode if self.current_sync_mode not in ("static_white", "static_color") else self.current_sync_mode,
                "ambilight_enabled": (self.mapper.mode == "screen_ambilight" and self.current_sync_mode not in ("static_white", "static_color")),
                "algorithm": self.mapper.algorithm,
                "bulb": {
                    "connected": self.bulb.is_connected,
                    "ping_ms": self.bulb.ping_ms,
                    "rate_pps": self.bulb.packets_per_sec,
                    "reconnects": self.bulb.reconnect_count
                },
                "screen_sync": self.screen_sync.get_status(),
                "source": self.audio.source_mode,
                "source_name": self.audio.get_clean_device_name(),
                "speaker_devices": self.speaker_devices_cache,
                "bass_flash": {
                    "enabled": self.mapper.bass_flash_enabled,
                    "intensity": round(self.mapper.bass_flash_intensity, 2),
                    "style": self.mapper.bass_flash_style,
                    "threshold": round(self.dsp.kick_threshold, 2),
                    "flash_level": round(self.mapper.kick_flash, 2)
                },
                "media": {
                    "has_media": media_state["has_media"],
                    "title": media_state["title"],
                    "artist": media_state["artist"],
                    "album": media_state["album"],
                    "position": media_state["position"],
                    "duration": media_state["duration"],
                    "is_playing": media_state["is_playing"],
                    "app_id": media_state["app_id"],
                    "thumbnail": media_state["thumbnail"] if send_thumb else None
                },
                "metrics": {
                    "bass": round(metrics["bass"], 2),
                    "mid": round(metrics["mid"], 2),
                    "treble": round(metrics["treble"], 2),
                    "is_kick": metrics["is_kick"],
                    "spectral_centroid": metrics.get("spectral_centroid", 1000),
                    "dominant_note": metrics.get("dominant_note", "C"),
                    "note_idx": metrics.get("note_idx", 0)
                }
            })

            elapsed = time.time() - t0
            sleep_time = max(0.002, 0.016 - elapsed)
            time.sleep(sleep_time)

    def _refresh_tray_state(self):
        """Periodically refreshes the tray icon pixmap, connection status label, and tooltip."""
        with self._lock:
            r, g, b = self.current_rgb
            mode_name = self.mapper.mode
            is_strobe = self.screen_sync.is_strobe_active

        is_connected = self.bulb.is_connected
        ping = self.bulb.ping_ms
        pps = self.bulb.packets_per_sec

        # Tray Icon update
        if self.icon_style == "brand":
            if self._current_tray_style != "brand":
                if self.brand_icon and not self.brand_icon.isNull():
                    self.tray_icon.setIcon(self.brand_icon)
                self._current_tray_style = "brand"
        else:
            icon = create_orb_icon(r, g, b, is_connected, is_strobe, self.light_power)
            self.tray_icon.setIcon(icon)
            self._current_tray_style = "orb"

        # Status action in menu
        if self.bulb.dry_run:
            status_text = "Async 2.0 (Preview / Dry-Run)"
        elif is_connected:
            status_text = f"Bulb Connected ({ping:.0f}ms | {pps:.1f} pps)"
        else:
            status_text = f"Bulb Reconnecting (#{self.bulb.reconnect_count})..."
        self.act_status.setText(status_text)

        # Update Tooltip
        mode_label = "Screen Ambilight" if mode_name == "screen_ambilight" else mode_name.replace('_', ' ').title()
        strobe_str = " | Strobe Active" if is_strobe else ""
        self.tray_icon.setToolTip(
            f"Async 2.0\n"
            f"Mode: {mode_label}{strobe_str}\n"
            f"Bulb: {'Connected' if is_connected else 'Offline'} ({ping:.0f}ms)\n"
            f"Left-Click: Light Controls | Right-Click: Menu"
        )

        # Sync menu checkmarks if changed from web UI
        if self.act_ambilight.isChecked() != (mode_name == "screen_ambilight"):
            self.act_ambilight.blockSignals(True)
            self.act_ambilight.setChecked(mode_name == "screen_ambilight")
            self.act_ambilight.blockSignals(False)

        if mode_name in self.mode_actions and not self.mode_actions[mode_name].isChecked():
            self.mode_actions[mode_name].blockSignals(True)
            self.mode_actions[mode_name].setChecked(True)
            self.mode_actions[mode_name].blockSignals(False)

    def quit_app(self):
        """Clean teardown of all threads and sockets on exit."""
        logger.info("Shutting down Async Tray App cleanly...")
        self._is_running = False
        self.ui_timer.stop()
        self.tray_icon.hide()

        self.screen_sync.stop()
        self.media.stop()
        self.audio.stop()
        self.bulb.close()
        self.web_server.stop()

        self.app.quit()

LOCAL_SERVER_NAME = "Async20_Tray_App"

def main():
    # Enforce single QApplication instance
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Do not exit when windows close; stay in tray

    icon_path = Path(__file__).parent / "assets" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 1. Check if another instance is already running
    socket = QLocalSocket()
    socket.connectToServer(LOCAL_SERVER_NAME)
    if socket.waitForConnected(300):
        # Notify the running instance to pop up a reminder
        socket.write(b"PING\n")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        sys.exit(0)

    # 2. First instance: start single-instance local server
    QLocalServer.removeServer(LOCAL_SERVER_NAME)
    server = QLocalServer()
    server.listen(LOCAL_SERVER_NAME)

    tray_app = AsyncTrayApp(app, local_server=server)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
