"""
Windows WASAPI Audio Capture Engine for Async.
Non-intrusive, zero-latency audio capture:
  1. 'speaker' Mode: Passive loopback capture of Windows default audio playback
  2. 'mic' Mode: Live microphone capture for voice / ambient acoustic sound
Never modifies, overrides, or locks system audio drivers or default playback endpoints.
"""

import time
import queue
import logging
from typing import Optional, Tuple
import numpy as np
import pyaudiowpatch as pyaudio

logger = logging.getLogger("Async.AudioCapture")


class AudioCapture:
    SOURCES = ["speaker", "mic"]

    def __init__(self, chunk_size: int = 1024, source_mode: str = "speaker"):
        self.chunk_size = chunk_size
        self.source_mode = source_mode if source_mode in self.SOURCES else "speaker"
        self.p: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.audio_queue: queue.Queue = queue.Queue(maxsize=8)
        self.is_running: bool = False

        self.device_info: Optional[dict] = None
        self.sample_rate: int = 44100
        self.channels: int = 2

    def _find_loopback_device(self) -> dict:
        """Finds the system default WASAPI loopback device passively without modifying Windows audio settings."""
        try:
            return self.p.get_default_wasapi_loopback()
        except Exception as e:
            logger.warning(f"get_default_wasapi_loopback fallback ({e})")
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            loopback_devices = list(self.p.get_loopback_device_info_generator())
            if not loopback_devices:
                raise RuntimeError("No WASAPI loopback audio devices found on system!")

            for dev in loopback_devices:
                if default_speakers["name"] in dev["name"]:
                    return dev

            return loopback_devices[0]

    def _find_mic_device(self) -> dict:
        """Finds the system default input microphone device."""
        try:
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_in_idx = wasapi_info.get("defaultInputDevice")
            if default_in_idx is not None and default_in_idx >= 0:
                dev = self.p.get_device_info_by_index(default_in_idx)
                if dev.get("maxInputChannels", 0) > 0:
                    return dev
        except Exception:
            pass

        return self.p.get_default_input_device_info()

    def _stream_callback(self, in_data, frame_count, time_info, status):
        """Audio stream callback pushing chunks to queue."""
        if status:
            logger.debug(f"Audio stream status: {status}")

        try:
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            if self.channels > 1:
                audio_data = audio_data.reshape(-1, self.channels)
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

    def read_chunk(self, timeout: float = 0.015) -> Optional[np.ndarray]:
        """
        Fetches the latest real-time audio chunk from queue.
        Drains any stale backlog chunks so analysis is always 100% zero-latency.
        """
        try:
            latest = self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

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
        """Restarts audio stream on the current default device."""
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
