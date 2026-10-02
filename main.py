"""
Async: Real-Time Audio-Reactive Smart Lighting & Cava Visualizer for Windows 11.
Orchestrates WASAPI desktop audio capture, NumPy FFT DSP analysis,
dynamic color animations, live terminal Cava UI, local Havells Tuya Wi-Fi control,
and a 60 FPS full-screen browser Room Glow simulator.
"""

import os
import sys
import time
import json
import msvcrt
import webbrowser
from pathlib import Path
from typing import Dict, Any

import numpy as np
from core.audio_capture import AudioCapture
from core.dsp_engine import DSPEngine
from core.color_mapper import ColorMapper
from core.screen_sync import ScreenSyncEngine
from core.media_session import WindowsMediaSession
from drivers.tuya_driver import HavellsLocalBulb
from web.server import AsyncWebServer

# Enable ANSI escape sequences & UTF-8 output on Windows console
os.system("")
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
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

BLOCK_CHARS = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

def main():
    config = load_config()
    bulb_cfg = config.get("bulb", {})
    audio_cfg = config.get("audio", {})
    visuals_cfg = config.get("visuals", {})

    num_bands = audio_cfg.get("bands", 24)
    chunk_size = audio_cfg.get("chunk_size", 1024)
    gravity = audio_cfg.get("gravity", 0.82)
    mode = visuals_cfg.get("mode", "bass_pulse")

    # Bar coloring: 'bulb' (matches single active bulb color) or 'rainbow' (multi-frequency bands)
    bar_color_mode = visuals_cfg.get("bar_coloring", "bulb")

    print("\033[2J\033[H\033[?25l", end="") # Clear screen & hide cursor

    # Initialize Modules
    audio = AudioCapture(chunk_size=chunk_size)
    dsp = DSPEngine(num_bands=num_bands, chunk_size=chunk_size, gravity=gravity)
    mapper = ColorMapper(mode=mode)
    screen_sync = ScreenSyncEngine(target_fps=30, smoothing=0.28, letterbox_crop=True)
    screen_sync.start()
    if mapper.mode == "screen_ambilight":
        screen_sync.enable()
    media = WindowsMediaSession()
    media.start()

    bulb = HavellsLocalBulb(
        device_id=bulb_cfg.get("device_id", ""),
        ip_address=bulb_cfg.get("ip", ""),
        local_key=bulb_cfg.get("local_key", ""),
        version=bulb_cfg.get("version", 3.3)
    )

    devices_refresh_flag = [True]
    speaker_devices_cache = []
    speaker_devices_timer = 0.0
    stream_health_timer = 0.0

    # Initialize Web Room Simulator Server
    def handle_web_command(cmd: dict):
        action = cmd.get("action")
        if action == "set_mode":
            new_mode = cmd.get("mode")
            if new_mode in mapper.MODES:
                mapper.set_mode(new_mode)
                if new_mode == "screen_ambilight":
                    screen_sync.enable()
                else:
                    screen_sync.disable()
        elif action == "toggle_ambilight":
            is_on = mapper.toggle_ambilight()
            if is_on:
                screen_sync.enable()
            else:
                screen_sync.disable()
        elif action == "set_ambilight":
            enabled = bool(cmd.get("enabled", True))
            if enabled:
                if mapper.mode != "screen_ambilight":
                    mapper._last_audio_mode = mapper.mode
                mapper.set_mode("screen_ambilight")
                screen_sync.enable()
            else:
                target = getattr(mapper, "_last_audio_mode", "bass_pulse")
                mapper.set_mode(target)
                screen_sync.disable()
        elif action == "set_algorithm":
            new_algo = cmd.get("algorithm")
            if new_algo in mapper.ALGORITHMS:
                mapper.set_algorithm(new_algo)
        elif action == "set_audio_source":
            new_source = cmd.get("source")
            if new_source in audio.SOURCES:
                audio.switch_source(new_source)
                dsp.set_sample_rate(audio.sample_rate)
                dsp.reset()
                devices_refresh_flag[0] = True
        elif action == "set_speaker_device":
            device_target = cmd.get("device")
            audio.select_speaker_device(device_target)
            dsp.set_sample_rate(audio.sample_rate)
            dsp.reset()
            devices_refresh_flag[0] = True
        elif action == "get_speaker_devices":
            devices_refresh_flag[0] = True
        elif action == "set_bass_flash":
            mapper.set_bass_flash(cmd.get("enabled", True))
        elif action == "set_flash_intensity":
            mapper.set_flash_intensity(float(cmd.get("intensity", 1.0)))
        elif action == "set_flash_threshold":
            dsp.set_kick_threshold(float(cmd.get("threshold", 0.38)))
        elif action == "set_flash_style":
            mapper.set_flash_style(cmd.get("style", "white_flare"))
        elif action == "trigger_flash":
            mapper.trigger_flash(float(cmd.get("intensity", 1.0)))
        elif action == "media_play_pause":
            media.toggle_play_pause()
        elif action == "media_next":
            media.next_track()
        elif action == "media_previous":
            media.previous_track()

    web_server = AsyncWebServer(port=5050, on_command=handle_web_command)
    web_server.start()

    # Automatically open browser room simulator
    time.sleep(0.2)
    try:
        webbrowser.open("http://localhost:5050")
    except Exception:
        pass

    try:
        audio.start()
        dsp.set_sample_rate(audio.sample_rate)
    except Exception as e:
        print(f"\033[?25h\033[91mError starting audio capture: {e}\033[0m")
        web_server.stop()
        return

    fps_count = 0
    fps_timer = time.time()
    current_fps = 0.0
    status_msg = "Room Glow Active"

    max_cava_height = 8
    last_track_key = ""

    try:
        while True:
            # 1. Handle Keyboard Inputs
            if msvcrt.kbhit():
                key = msvcrt.getch().decode("utf-8", errors="ignore").lower()
                if key == "q":
                    break
                elif key == "5":
                    is_on = mapper.toggle_ambilight()
                    if is_on:
                        screen_sync.enable()
                        status_msg = "Ambilight: ON (Screen Sync)"
                    else:
                        screen_sync.disable()
                        status_msg = f"Ambilight: OFF ({mapper.mode})"
                elif key in ["1", "2", "3", "4"]:
                    mode_map = {"1": "bass_pulse", "2": "rainbow_wave", "3": "ambient_chill", "4": "rave_strobe"}
                    selected = mode_map[key]
                    mapper.set_mode(selected)
                    screen_sync.disable()
                    status_msg = f"Mode: {mapper.mode}"
                elif key == "m":
                    new_mode = mapper.cycle_mode()
                    if new_mode == "screen_ambilight":
                        screen_sync.enable()
                    else:
                        screen_sync.disable()
                    status_msg = f"Mode: {new_mode}"
                elif key == "a":
                    new_algo = mapper.cycle_algorithm()
                    status_msg = f"Algo: {new_algo}"
                elif key == "b":
                    mapper.set_bass_flash(not mapper.bass_flash_enabled)
                    status_msg = f"Flash: {'ON' if mapper.bass_flash_enabled else 'OFF'}"
                elif key == "t":
                    mapper.trigger_flash(1.2)
                    status_msg = "Flash Triggered!"
                elif key == "s":
                    new_src, dev_name, sr = audio.toggle_source()
                    dsp.set_sample_rate(sr)
                    dsp.reset()
                    status_msg = f"Source: {new_src.upper()}"
                elif key == "c":
                    bar_color_mode = "rainbow" if bar_color_mode == "bulb" else "bulb"
                    status_msg = f"Bars: {bar_color_mode.upper()}"
                elif key == "w":
                    webbrowser.open("http://localhost:5050")
                    status_msg = "Opened Browser"
                elif key == "+":
                    dsp.rolling_max = max(0.01, dsp.rolling_max * 0.85)
                    status_msg = "Sensitivity +"
                elif key == "-":
                    dsp.rolling_max = dsp.rolling_max * 1.15
                    status_msg = "Sensitivity -"

            # 2. Capture & Process Audio / Screen
            chunk = audio.read_chunk(timeout=0.015)
            if chunk is not None:
                bands, metrics = dsp.process(chunk)
            else:
                bands = np.zeros(num_bands, dtype=np.float32)
                metrics = {
                    "bass": 0.0, "mid": 0.0, "treble": 0.0, "is_kick": False,
                    "spectral_centroid": 1000.0, "dominant_note": "-", "note_idx": 0
                }

            if mapper.mode == "screen_ambilight":
                rgb, hsv = screen_sync.get_color()
            else:
                rgb, hsv = mapper.update(metrics)

            # 3. Transmit to Bulb
            bulb.set_hsv(hsv[0], hsv[1], hsv[2])

            # 4. Broadcast to Browser Room Simulator (WebSocket)
            media_state = media.get_state()
            track_key = f"{media_state.get('title')}_{media_state.get('artist')}"
            send_thumb = (track_key != last_track_key)
            if send_thumb:
                last_track_key = track_key

            now = time.time()
            if now - stream_health_timer >= 3.0:
                audio.check_stream_health()
                stream_health_timer = now

            if now - speaker_devices_timer >= 2.0 or devices_refresh_flag[0]:
                speaker_devices_cache = audio.get_speaker_devices()
                speaker_devices_timer = now
                devices_refresh_flag[0] = False

            web_server.broadcast({
                "rgb": rgb,
                "hsv": [round(hsv[0], 1), round(hsv[1], 1), round(hsv[2], 1)],
                "bands": [round(float(b), 3) for b in bands],
                "mode": mapper.mode,
                "ambilight_enabled": (mapper.mode == "screen_ambilight"),
                "algorithm": mapper.algorithm,
                "bulb": {
                    "connected": bulb.is_connected,
                    "ping_ms": bulb.ping_ms
                },
                "source": audio.source_mode,
                "source_name": audio.get_clean_device_name(),
                "speaker_devices": speaker_devices_cache,
                "bass_flash": {
                    "enabled": mapper.bass_flash_enabled,
                    "intensity": round(mapper.bass_flash_intensity, 2),
                    "style": mapper.bass_flash_style,
                    "threshold": round(dsp.kick_threshold, 2),
                    "flash_level": round(mapper.kick_flash, 2)
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

            # 5. FPS Calculation
            fps_count += 1
            now = time.time()
            if now - fps_timer >= 1.0:
                current_fps = fps_count / (now - fps_timer)
                fps_count = 0
                fps_timer = now

            # 6. Render Cava & Lighting Terminal UI
            r, g, b = rgb
            hue, sat, val = hsv

            # Build Cava rows from top to bottom
            cava_lines = []
            for row in range(max_cava_height - 1, -1, -1):
                line_chars = []
                for b_idx in range(num_bands):
                    band_val = bands[b_idx] * max_cava_height
                    if band_val >= (row + 1):
                        char = "█"
                    elif band_val > row:
                        char_sub = int((band_val - row) * 8)
                        char = BLOCK_CHARS[min(8, max(0, char_sub))]
                    else:
                        char = " "

                    if bar_color_mode == "bulb":
                        intensity = max(0.4, (row + 1) / max_cava_height)
                        r_col = int(r * intensity)
                        g_col = int(g * intensity)
                        b_col = int(b * intensity)
                    else:
                        t = b_idx / float(num_bands - 1)
                        if t < 0.35:
                            r_col, g_col, b_col = 255, int(t / 0.35 * 200), 40
                        elif t < 0.70:
                            r_col = int((1.0 - (t - 0.35) / 0.35) * 200)
                            g_col = 240
                            b_col = int((t - 0.35) / 0.35 * 255)
                        else:
                            r_col = int((t - 0.70) / 0.30 * 230)
                            g_col = int((1.0 - (t - 0.70) / 0.30) * 120)
                            b_col = 255

                    line_chars.append(f"\033[38;2;{r_col};{g_col};{b_col}m{char*2}\033[0m")
                cava_lines.append("  " + "".join(line_chars))

            # Color preview block
            swatch = f"\033[48;2;{r};{g};{b}m                \033[0m"

            # Brightness gauge
            gauge_len = 16
            filled = int((val / 100.0) * gauge_len)
            gauge = "█" * filled + "░" * (gauge_len - filled)

            # Kick indicator
            kick_badge = "\033[97;41;1m 💥 KICK! \033[0m" if metrics["is_kick"] else "\033[90m [      ] \033[0m"

            if bulb.dry_run:
                bulb_conn = "\033[93m◌ PREVIEW / DRY-RUN\033[0m"
            elif bulb.is_connected:
                bulb_conn = f"\033[92m● CONNECTED ({bulb.ping_ms:.0f}ms)\033[0m"
            else:
                bulb_conn = "\033[91;1m◌ AUTO-RECONNECTING...\033[0m"
            color_mode_label = f"\033[1;36mSINGLE BULB\033[0m" if bar_color_mode == "bulb" else "\033[1;35mRAINBOW\033[0m"

            # Algorithm details
            algo_name = mapper.algorithm.upper()
            if mapper.algorithm == "chroma_pitch":
                algo_extra = f"\033[1;33m[Note: {metrics.get('dominant_note')}]\033[0m"
            elif mapper.algorithm == "spectral_centroid":
                algo_extra = f"\033[1;36m[{int(metrics.get('spectral_centroid', 0))} Hz]\033[0m"
            elif mapper.algorithm == "rgb_projection":
                algo_extra = "\033[1;35m[Physics]\033[0m"
            else:
                algo_extra = "\033[1;32m[Melody]\033[0m"

            flash_status = "\033[92m● ON\033[0m" if mapper.bass_flash_enabled else "\033[90m○ OFF\033[0m"
            flash_style_name = mapper.bass_flash_style.replace('_', ' ').title()

            src_label = "\033[1;35m🎤 MIC\033[0m" if audio.source_mode == "mic" else "\033[1;34m🔊 SPEAKER\033[0m"
            dev_display = audio.device_info['name'][:22] if audio.device_info else "Audio"
            media_info_str = f"| Track: \033[1;97m{media_state['title'][:22]}\033[0m" if media_state['has_media'] else ""

            # Compose screen buffer
            output = (
                "\033[H" # Move cursor to top-left
                " \033[1;36m🌈 ASYNC: Real-Time Audio-Reactive Smart Lighting & Room Simulator\033[0m\n"
                f" \033[90mSource: {src_label} \033[90m({dev_display}) | FPS: {current_fps:4.1f} | Bulb: {bulb_conn}\033[0m\n"
                f" \033[90mWeb Simulator: \033[4;34mhttp://localhost:5050\033[0m \033[90m| Algo: \033[1m{algo_name}\033[0m {algo_extra} {media_info_str}\033[0m\n"
                " ─────────────────────────────────────────────────────────────────────────────\n"
                + "\n".join(cava_lines) + "\n"
                "  " + "▀▀" * num_bands + "\n"
                f"  \033[90m[20 Hz] ─────────────── SUB-BASS ─── MIDS ─── TREBLE ─────────────── [16 kHz]\033[0m\n\n"
                " ┌─────────────────────────── LIVE SMART LIGHT STATE ──────────────────────────┐\n"
                f" │  Color Swatch : {swatch}  Mode: \033[1;33m{mapper.mode.upper():<14}\033[0m   {kick_badge}  │\n"
                f" │  RGB Output   : \033[1mR:{r:<3} G:{g:<3} B:{b:<3}\033[0m        Hue : \033[36m{hue:5.1f}°\033[0m Sat: \033[36m{sat:4.1f}%\033[0m              │\n"
                f" │  Brightness   : [{gauge}] {val:5.1f}%   Bass Energy: {metrics['bass']*100:4.1f}%       │\n"
                f" │  Bass Flash   : {flash_status} ({flash_style_name:<12})  Sens: {dsp.kick_threshold:4.2f} | Mul: {mapper.bass_flash_intensity*100:3.0f}%     │\n"
                f" │  Target Bulb  : IP {bulb.ip_address}:6668 | ID: {bulb.device_id[:16]}...          │\n"
                " └─────────────────────────────────────────────────────────────────────────────┘\n"
                f"  \033[90mControls: [1-4] Audio Modes | [5] Toggle Ambilight | [A] Algo | [B] Bass Flash | [T] Flash Test | [S] Source | [Q] Quit\033[0m\n"
            )

            sys.stdout.write(output)
            sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        screen_sync.stop()
        media.stop()
        audio.stop()
        bulb.close()
        web_server.stop()
        print("\033[?25h\033[0m\n\nExited Async cleanly.")

if __name__ == "__main__":
    main()
