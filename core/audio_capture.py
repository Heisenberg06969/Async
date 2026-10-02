"""
Windows WASAPI Audio Capture Engine for Async.
Supports seamless switching between:
  1. 'speaker' Mode: Zero-latency loopback capture of desktop audio (Spotify, YouTube, Games, FxSound)
  2. 'mic' Mode: Live microphone capture for room voice, clapping, singing, instruments, or ambient sound
"""

import sys
import time
import queue
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pyaudiowpatch as pyaudio

logger = logging.getLogger("Async.AudioCapture")

def set_windows_default_playback_device(device_name: str) -> bool:
    """
    Uses NirSoft SoundVolumeView (tools/SoundVolumeView.exe) to switch Windows 11
    system-wide default audio playback endpoint across Console, Multimedia, and Communications.
    """
    try:
        tools_dir = Path(__file__).resolve().parent.parent / "tools"
        exe_path = tools_dir / "SoundVolumeView.exe"
        if not exe_path.exists():
            logger.warning(f"SoundVolumeView.exe not found at {exe_path}")
            return False

        # Extract base name for matching SoundVolumeView device names:
        # e.g. "Speaker (Realtek(R) Audio)" -> "Speaker"
        # "Headphone (Realtek(R) Audio)" -> "Headphone"
        # "FxSound Speakers (FxSound Audio Enhancer)" -> "FxSound Speakers"
        # "LG FHD (NVIDIA High Definition Audio)" -> "LG FHD"
        clean_target = device_name.split("(")[0].strip() if "(" in device_name else device_name.strip()

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        success = True
        
        # Windows 11 requires setting each role explicitly: 0=Console, 1=Multimedia, 2=Communications
        for role in ["0", "1", "2"]:
            res = subprocess.run(
                [str(exe_path), "/SetDefault", clean_target, role],
                capture_output=True,
                timeout=3.0,
                creationflags=creationflags
            )
            if res.returncode != 0:
                success = False

        # Also redirect any active media players / browsers directly so currently playing audio immediately transitions
        for app_proc in ["brave.exe", "chrome.exe", "spotify.exe", "msedge.exe", "vlc.exe"]:
            subprocess.run(
                [str(exe_path), "/SetAppDefault", clean_target, "all", app_proc],
                capture_output=True,
                timeout=1.0,
                creationflags=creationflags
            )

        logger.info(f"Switched Windows default audio to '{clean_target}' across roles 0,1,2 (success: {success})")
        return success
    except Exception as e:
        logger.error(f"Failed to switch Windows default audio to '{device_name}': {e}")
        return False

class AudioCapture:
    SOURCES = ["speaker", "mic"]

    def __init__(self, chunk_size: int = 1024, source_mode: str = "speaker", target_device_name: Optional[str] = None):
        self.chunk_size = chunk_size
        self.source_mode = source_mode if source_mode in self.SOURCES else "speaker"
        self.target_device_name = target_device_name
        self.p: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.audio_queue: queue.Queue = queue.Queue(maxsize=8)
        self.is_running: bool = False
        
        self.device_info: Optional[dict] = None
        self.sample_rate: int = 44100
        self.channels: int = 2

    def _match_loopback_device(self, target_query, loopback_devices: list) -> Optional[dict]:
        """Matches a loopback device by index, exact clean name, base name, prefix, or substring."""
        if not target_query:
            return None
        target_str = str(target_query).strip().lower()

        # 1. Match by index
        for dev in loopback_devices:
            if str(dev["index"]) == target_str:
                return dev

        # 2. Match exact clean name
        for dev in loopback_devices:
            clean = dev["name"].replace(" [Loopback]", "").strip().lower()
            if clean == target_str:
                return dev

        # 3. Match base device name (before parenthesis, e.g. "Speaker" vs "FxSound Speakers")
        for dev in loopback_devices:
            clean = dev["name"].replace(" [Loopback]", "").strip().lower()
            clean_base = clean.split("(")[0].strip()
            if clean_base == target_str:
                return dev

        # 4. Match prefix / starts with
        for dev in loopback_devices:
            clean = dev["name"].replace(" [Loopback]", "").strip().lower()
            if clean.startswith(target_str):
                return dev

        # 5. Match substring
        for dev in loopback_devices:
            clean = dev["name"].replace(" [Loopback]", "").strip().lower()
            if target_str in clean:
                return dev

        return None

    def _find_loopback_device(self) -> dict:
        """Finds the default WASAPI output loopback device or matching target."""
        wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        
        loopback_devices = list(self.p.get_loopback_device_info_generator())
        if not loopback_devices:
            raise RuntimeError("No WASAPI loopback audio devices found on system!")

        # If user specified a specific device name or index
        if self.target_device_name:
            matched = self._match_loopback_device(self.target_device_name, loopback_devices)
            if matched:
                return matched

        # Otherwise match the default active speaker (e.g. FxSound Speakers)
        for dev in loopback_devices:
            if default_speakers["name"] in dev["name"]:
                return dev

        # Fallback to the first available loopback device
        return loopback_devices[0]

    def _find_mic_device(self) -> dict:
        """Finds the system default input microphone device."""
        try:
            # Try WASAPI default input first for lowest latency
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_in_idx = wasapi_info.get("defaultInputDevice")
            if default_in_idx is not None and default_in_idx >= 0:
                dev = self.p.get_device_info_by_index(default_in_idx)
                if dev.get("maxInputChannels", 0) > 0:
                    return dev
        except Exception:
            pass

        # Fallback to general default input device
        return self.p.get_default_input_device_info()

    def _stream_callback(self, in_data, frame_count, time_info, status):
        """Audio stream callback pushing chunks to queue."""
        if status:
            logger.debug(f"Audio stream status: {status}")
            
        try:
            # Convert raw byte buffer to int16 numpy array
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            
            # Reshape into (samples, channels)
            if self.channels > 1:
                audio_data = audio_data.reshape(-1, self.channels)
                # Average channels to mono float32 [-1.0, 1.0]
                mono = audio_data.mean(axis=1).astype(np.float32) / 32768.0
            else:
                mono = audio_data.astype(np.float32) / 32768.0
                
            if self.audio_queue.full():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
            self.audio_queue.put_nowait(mono)
        except Exception as e:
            logger.error(f"Error in audio callback: {e}")
            
        return (in_data, pyaudio.paContinue)

    def start(self):
        """Starts audio capture stream for the active source_mode."""
        if self.is_running:
            return

        self.p = pyaudio.PyAudio()

        if self.source_mode == "mic":
            self.device_info = self._find_mic_device()
            self.channels = min(2, max(1, int(self.device_info.get("maxInputChannels", 1))))
        else:
            self.device_info = self._find_loopback_device()
            self.channels = int(self.device_info["maxInputChannels"])

        self.sample_rate = int(self.device_info["defaultSampleRate"])

        logger.info(f"Capture ({self.source_mode.upper()}): {self.device_info['name']} @ {self.sample_rate}Hz ({self.channels}ch)")

        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self.device_info["index"],
            frames_per_buffer=self.chunk_size,
            stream_callback=self._stream_callback
        )
        self.stream.start_stream()
        self.is_running = True

    def switch_source(self, mode: str) -> Tuple[str, str, int]:
        """
        Dynamically switches audio source between 'speaker' and 'mic'.
        Returns:
            (new_mode, device_name, sample_rate)
        """
        if mode not in self.SOURCES:
            return self.source_mode, (self.device_info["name"] if self.device_info else "Unknown"), self.sample_rate

        if mode == self.source_mode and self.is_running:
            return self.source_mode, self.device_info["name"], self.sample_rate

        self.stop()
        self.source_mode = mode
        
        # Clear out any residual chunks from previous audio device
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Exception:
                break

        self.start()
        dev_name = self.device_info["name"] if self.device_info else "Unknown"
        return self.source_mode, dev_name, self.sample_rate

    def toggle_source(self) -> Tuple[str, str, int]:
        """Toggles between speaker and mic."""
        next_mode = "mic" if self.source_mode == "speaker" else "speaker"
        return self.switch_source(next_mode)

    def get_clean_device_name(self) -> str:
        """Returns clean display name for active audio capture device."""
        if not self.device_info or "name" not in self.device_info:
            return "Desktop Audio" if self.source_mode == "speaker" else "Microphone (Live)"
        return self.device_info["name"].replace(" [Loopback]", "").strip()

    def get_speaker_devices(self) -> list:
        """Returns all available WASAPI loopback output audio devices with UI device metadata."""
        close_p = False
        p_inst = self.p
        if p_inst is None:
            p_inst = pyaudio.PyAudio()
            close_p = True

        devices = []
        try:
            current_idx = self.device_info["index"] if self.device_info else -1
            current_clean = self.get_clean_device_name()

            for dev in p_inst.get_loopback_device_info_generator():
                raw_name = dev["name"]
                clean_name = raw_name.replace(" [Loopback]", "").strip()
                dev_type = "speaker"
                lower_name = clean_name.lower()
                if "headphone" in lower_name or "headset" in lower_name or "earphone" in lower_name:
                    dev_type = "headphone"
                elif any(k in lower_name for k in ["fhd", "display", "monitor", "nvidia", "tv", "hdmi"]):
                    dev_type = "display"

                is_active = (self.source_mode == "speaker") and (
                    (dev["index"] == current_idx) or (clean_name == current_clean)
                )

                devices.append({
                    "index": dev["index"],
                    "name": clean_name,
                    "type": dev_type,
                    "is_active": is_active
                })
        except Exception as e:
            logger.warning(f"Error enumerating speaker devices: {e}")
        finally:
            if close_p:
                p_inst.terminate()

        return devices

    def resolve_speaker_device(self, device_name_or_index) -> Optional[dict]:
        """Resolves a loopback device dict from name or index."""
        target_str = str(device_name_or_index).strip().lower()
        close_p = False
        p_inst = self.p
        if p_inst is None:
            p_inst = pyaudio.PyAudio()
            close_p = True

        try:
            loopback_devices = list(p_inst.get_loopback_device_info_generator())
            return self._match_loopback_device(device_name_or_index, loopback_devices)
        except Exception as e:
            logger.warning(f"Error resolving speaker device: {e}")
        finally:
            if close_p:
                p_inst.terminate()
        return None

    def select_speaker_device(self, device_name_or_index) -> Tuple[str, str, int]:
        """
        Switches Windows 11 default playback endpoint AND loopback audio capture
        to a specific speaker/headphone device by name or index.
        Returns:
            (source_mode, clean_device_name, sample_rate)
        """
        matched_dev = self.resolve_speaker_device(device_name_or_index)
        resolved_name = matched_dev["name"].replace(" [Loopback]", "").strip() if matched_dev else str(device_name_or_index)

        # 1. Switch Windows 11 system-wide default playback device
        set_windows_default_playback_device(resolved_name)

        # 2. Brief sleep for Windows CoreAudio endpoint migration
        time.sleep(0.08)

        # 3. Re-initialize WASAPI loopback capture on newly selected device
        self.stop()
        self.source_mode = "speaker"
        self.target_device_name = resolved_name

        # Clear residual audio chunks
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Exception:
                break

        self.start()
        clean_name = self.get_clean_device_name()
        return self.source_mode, clean_name, self.sample_rate

    def read_chunk(self, timeout: float = 0.015) -> Optional[np.ndarray]:
        """
        Fetches the latest real-time audio chunk from queue.
        Drains any stale backlog chunks so analysis is always 100% zero-latency.
        """
        try:
            latest = self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

        # Drain any backlog chunks so we never lag behind live playback
        while not self.audio_queue.empty():
            try:
                latest = self.audio_queue.get_nowait()
            except queue.Empty:
                break

        return latest

    def check_stream_health(self) -> bool:
        """Verifies PyAudio stream is active, restarts if Windows dropped the endpoint."""
        if not self.is_running or self.stream is None:
            return False
        try:
            if not self.stream.is_active():
                logger.warning("WASAPI loopback stream inactive. Restarting audio capture...")
                self.restart()
                return False
            return True
        except Exception:
            return False

    def restart(self):
        """Restarts audio stream on the current device."""
        self.stop()
        time.sleep(0.05)
        self.start()

    def stop(self):
        """Stops and cleans up audio resources."""
        self.is_running = False
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if self.p is not None:
            try:
                self.p.terminate()
            except Exception:
                pass
            self.p = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
