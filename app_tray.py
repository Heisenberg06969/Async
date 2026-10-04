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

from core.audio_capture import AudioCapture
from core.dsp_engine import DSPEngine
from core.color_mapper import ColorMapper
from core.screen_sync import ScreenSyncEngine
from core.media_session import WindowsMediaSession
from drivers.tuya_driver import HavellsLocalBulb
from web.server import AsyncWebServer

# Configure logging to file when running headless
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "async_tray.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Async.Tray")

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

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
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
        self._build_tray_menu()

        # Initial icon
        initial_icon = create_orb_icon(132, 209, 10, self.bulb.is_connected, False, self.light_power)
        self.tray_icon.setIcon(initial_icon)
        self.tray_icon.setToolTip("Async 2.0: Room Lighting Sync\nLeft-click: Toggle Ambilight\nRight-click: Menu")

        # Hook tray interactions
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # UI Refresh Timer (Refreshes icon glow and status tooltip at 10 FPS)
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(100)
        self.ui_timer.timeout.connect(self._refresh_tray_state)
        self.ui_timer.start()

        logger.info("Async 2.0 System Tray successfully initialized.")

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
        """Constructs the native Windows right-click tray menu."""
        self.tray_menu.clear()

        # 1. Status Header
        self.act_status = QAction("⚡ Async 2.0 (Connecting...)", self.tray_menu)
        font = QFont()
        font.setBold(True)
        self.act_status.setFont(font)
        self.act_status.setEnabled(False)
        self.tray_menu.addAction(self.act_status)

        self.tray_menu.addSeparator()

        # 2. Light Power Toggle
        self.act_power = QAction("💡 Smart Light Power", self.tray_menu)
        self.act_power.setCheckable(True)
        self.act_power.setChecked(self.light_power)
        self.act_power.toggled.connect(self._on_toggle_power)
        self.tray_menu.addAction(self.act_power)

        # 3. Ambilight Screen Sync Toggle
        self.act_ambilight = QAction("🖥️ Ambilight Screen Sync", self.tray_menu)
        self.act_ambilight.setCheckable(True)
        self.act_ambilight.setChecked(self.mapper.mode == "screen_ambilight")
        self.act_ambilight.toggled.connect(self._on_toggle_ambilight_action)
        self.tray_menu.addAction(self.act_ambilight)

        # 4. Fast-Edit Strobe Boost Toggle
        self.act_strobe = QAction("⚡ Fast-Edit Strobe Boost", self.tray_menu)
        self.act_strobe.setCheckable(True)
        self.act_strobe.setChecked(self.screen_sync.strobe_boost)
        self.act_strobe.toggled.connect(lambda chk: self.screen_sync.set_strobe_boost(chk))
        self.tray_menu.addAction(self.act_strobe)

        # 5. Bass Flash Toggle
        self.act_flash = QAction("💥 Bass Flash on Kicks", self.tray_menu)
        self.act_flash.setCheckable(True)
        self.act_flash.setChecked(self.mapper.bass_flash_enabled)
        self.act_flash.toggled.connect(lambda chk: self.mapper.set_bass_flash(chk))
        self.tray_menu.addAction(self.act_flash)

        self.tray_menu.addSeparator()

        # 6. Lighting Modes Submenu
        modes_menu = self.tray_menu.addMenu("🎨 Lighting Modes")
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

        # 7. Decision Algorithms Submenu
        algos_menu = self.tray_menu.addMenu("🎵 Music Algorithms")
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

        # 8. Audio Output Device Submenu
        self.devices_menu = self.tray_menu.addMenu("🔊 Audio Device")
        self._populate_audio_devices_menu()

        self.tray_menu.addSeparator()

        # 9. Open Room Simulator
        act_open_sim = QAction("🌐 Open Room Simulator (Web)", self.tray_menu)
        act_open_sim.triggered.connect(self._open_web_simulator)
        self.tray_menu.addAction(act_open_sim)

        # 10. Run on Windows Startup Toggle
        self.act_startup = QAction("🚀 Run on Windows Startup", self.tray_menu)
        self.act_startup.setCheckable(True)
        self.act_startup.setChecked(is_startup_enabled())
        self.act_startup.toggled.connect(lambda chk: set_startup_enabled(chk))
        self.tray_menu.addAction(self.act_startup)

        self.tray_menu.addSeparator()

        # 11. Exit
        act_exit = QAction("❌ Exit Async", self.tray_menu)
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

    def _select_audio_device(self, dev_name: str):
        self.audio.select_speaker_device(dev_name)
        self.dsp.set_sample_rate(self.audio.sample_rate)
        self.dsp.reset()
        self._populate_audio_devices_menu()
        self.tray_icon.showMessage("Async Audio", f"Switched to: {dev_name}", QSystemTrayIcon.Information, 1200)

    def _on_toggle_power(self, checked: bool):
        self.light_power = checked
        if not self.light_power:
            # Turn bulb dark (0% value)
            self.bulb.set_hsv(self.current_hsv[0], self.current_hsv[1], 0.0)
            self.tray_icon.showMessage("Async 2.0", "Light output paused", QSystemTrayIcon.Information, 1000)
        else:
            self.tray_icon.showMessage("Async 2.0", "Light output resumed", QSystemTrayIcon.Information, 1000)

    def _on_toggle_ambilight_action(self, checked: bool):
        if checked:
            if self.mapper.mode != "screen_ambilight":
                self.mapper._last_audio_mode = self.mapper.mode
            self.mapper.set_mode("screen_ambilight")
            self.screen_sync.enable()
            self.tray_icon.showMessage("Async 2.0", "Ambilight ON (Screen Sync)", QSystemTrayIcon.Information, 1200)
        else:
            target = getattr(self.mapper, "_last_audio_mode", "bass_pulse")
            self.mapper.set_mode(target)
            self.screen_sync.disable()
            self.tray_icon.showMessage("Async 2.0", f"Audio Sync: {target.upper()}", QSystemTrayIcon.Information, 1200)

    def _toggle_ambilight(self):
        """Toggles Ambilight and syncs menu checkmark state."""
        is_on = self.mapper.toggle_ambilight()
        if is_on:
            self.screen_sync.enable()
            self.act_ambilight.setChecked(True)
            self.tray_icon.showMessage("Async 2.0", "Ambilight ON (Screen Sync)", QSystemTrayIcon.Information, 1200)
        else:
            self.screen_sync.disable()
            self.act_ambilight.setChecked(False)
            target = getattr(self.mapper, "_last_audio_mode", "bass_pulse")
            self.tray_icon.showMessage("Async 2.0", f"Audio Sync: {target.upper()}", QSystemTrayIcon.Information, 1200)

    def _set_audio_mode(self, mode: str):
        self.mapper.set_mode(mode)
        self.screen_sync.disable()
        self.act_ambilight.setChecked(False)
        self.tray_icon.showMessage("Async 2.0", f"Mode: {mode.replace('_', ' ').title()}", QSystemTrayIcon.Information, 1200)

    def _open_web_simulator(self):
        """Opens the full-screen browser room simulator on demand."""
        try:
            webbrowser.open("http://localhost:5050")
        except Exception as e:
            logger.error(f"Failed to open web browser: {e}")

    def _on_tray_activated(self, reason):
        """Handles mouse clicks on the system tray icon."""
        if reason == QSystemTrayIcon.Trigger:
            # Single Left-Click: Toggle Ambilight Screen Sync vs Audio Mode
            self._toggle_ambilight()
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
                self.current_rgb = rgb
                self.current_hsv = hsv
                self.current_bands = bands
                self.latest_metrics = metrics

            # 2. Transmit to Bulb if Light Power is ON
            if self.light_power:
                self.bulb.set_hsv(hsv[0], hsv[1], hsv[2])

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
                "rgb": rgb,
                "hsv": [round(hsv[0], 1), round(hsv[1], 1), round(hsv[2], 1)],
                "bands": [round(float(b), 3) for b in bands],
                "mode": self.mapper.mode,
                "ambilight_enabled": (self.mapper.mode == "screen_ambilight"),
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

        # Dynamic icon
        icon = create_orb_icon(r, g, b, is_connected, is_strobe, self.light_power)
        self.tray_icon.setIcon(icon)

        # Status action in menu
        if self.bulb.dry_run:
            status_text = "⚡ Async 2.0 (Preview / Dry-Run)"
        elif is_connected:
            status_text = f"● Bulb Connected ({ping:.0f}ms | {pps:.1f} pps)"
        else:
            status_text = f"◌ Bulb Reconnecting (#{self.bulb.reconnect_count})..."
        self.act_status.setText(status_text)

        # Update Tooltip
        mode_label = "Screen Ambilight" if mode_name == "screen_ambilight" else mode_name.replace('_', ' ').title()
        strobe_str = " | ⚡ Strobe Active" if is_strobe else ""
        self.tray_icon.setToolTip(
            f"Async 2.0\n"
            f"Mode: {mode_label}{strobe_str}\n"
            f"Bulb: {'Connected' if is_connected else 'Offline'} ({ping:.0f}ms)\n"
            f"Left-Click: Toggle Ambilight | Right-Click: Menu"
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

def main():
    # Enforce single QApplication instance
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Do not exit when windows close; stay in tray

    tray_app = AsyncTrayApp(app)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
