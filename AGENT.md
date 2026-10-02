# 🤖 AGENT ONBOARDING & EXECUTION MANUAL: Async

> **ATTENTION AGENT / DEVELOPER:**  
> Read this file first! You are continuing development on **Async** (`02_Active_Projects/Async/`). You have 100% full context here. Do **not** ask the user to re-explain the project, lighting hardware, or goals. Everything you need to execute is detailed below.

---

## 🎯 1. Mission & Operational Scope

**Async** (**A**udio-**Sync** / **Async**hronous streaming) is a real-time, low-latency audio visualizer and smart lighting engine for Windows 11. It captures system desktop audio output, calculates Fast Fourier Transform (FFT) frequency spectrums in real time, and broadcasts visual effects to smart lights.

### Target Hardware Support:
1. **Tier 1 (In Hand & Zero Cost):** Havells Smart Light (Tuya / Smart Life Wi-Fi OEM protocol on LAN port 6668).
2. **Tier 2 (Pro Cava Desk Equalizer):** ESP32 microcontroller running **WLED** firmware driving a WS2812B / SK6812 addressable LED strip via UDP DDP/E1.31 streaming.

---

## 🏗️ 2. Core Software Architecture & File Layout

```
02_Active_Projects/Async/
├── AGENT.md                       <-- THIS FILE (Agent Execution Guide)
├── PROJECT_BRIEF.md               <-- Master architecture & DSP formulas
├── README.md                      <-- High-level overview & quick links
│
├── core/
│   ├── audio_capture.py           <-- Windows WASAPI loopback capture (pyaudiowpatch)
│   ├── dsp_engine.py              <-- NumPy FFT spectrum analyzer & beat energy detector
│   └── color_mapper.py            <-- HSV / RGB color transitions & brightness decay
│
├── drivers/
│   ├── tuya_driver.py             <-- Local Tuya / Havells UDP controller (tinytuya)
│   └── wled_driver.py             <-- DDP / E1.31 UDP packet streamer for ESP32 WLED
│
├── web/
│   ├── server.py                  <-- aiohttp WebSocket room simulation server
│   └── index.html                 <-- 60 FPS full-screen room ambient glow & single-color Cava
│
└── main.py                        <-- Main orchestrator daemon & CLI visualizer
```

---

## 🔬 3. Audio DSP Engine Implementation Guide

### 1. Windows WASAPI Loopback Capture (`core/audio_capture.py`)
Use `sounddevice` or `PyAudio` with Windows WASAPI loopback to record whatever sound is currently coming out of speakers/headphones (Brave, Spotify, FxSound, games):

```python
import sounddevice as sd
import numpy as np

def get_wasapi_loopback_device():
    # Discover default WASAPI loopback device
    devices = sd.query_devices()
    for idx, d in enumerate(devices):
        if d['hostapi'] == 3 and d['max_input_channels'] > 0 and "loopback" in d['name'].lower():
            return idx
    return sd.default.device[0]
```

### 2. Frequency Spectrum & Beat Detection (`core/dsp_engine.py`)
* Chunk size: 1024 samples @ 44.1 kHz (~23ms time resolution / ~43 FPS).
* Windowing: Hanning window (`np.hanning(1024)`).
* FFT: `np.abs(np.fft.rfft(chunk * window))`.
* Frequency bins:
  - **Sub-Bass & Bass:** 20 Hz – 250 Hz (bins ~1 to 6).
  - **Mids & Vocals:** 250 Hz – 2,000 Hz (bins ~6 to 47).
  - **Treble & Cymbals:** 2,000 Hz – 16,000 Hz (bins ~47 to 370).

### 3. Local Tuya / Havells Driver (`drivers/tuya_driver.py`)
```python
import tinytuya

class HavellsLocalBulb:
    def __init__(self, dev_id: str, ip_address: str, local_key: str, version: float = 3.3):
        self.device = tinytuya.BulbDevice(dev_id, ip_address, local_key, version=version)
        self.device.set_socketPersistent(True) # Keep socket open for high-speed UDP/TCP

    def set_hsv(self, hue: float, saturation: float, value: float):
        # Maps 0.0-1.0 to Tuya DPS 24 / colour data
        self.device.set_hsv(hue, saturation, value, nowait=True)

    def set_brightness(self, brightness_0_to_100: int):
        self.device.set_brightness_percentage(brightness_0_to_100, nowait=True)
```

---

## 🗺️ 4. Step-by-Step Implementation Roadmap

### Phase 1: Local Havells Bulb Discovery & Pairing
* **Task 1.1:** Scan local network using `tinytuya.deviceScan()` to locate the Havells bulb's local IP and MAC address.
* **Task 1.2:** Guide user to link Havells light with the Tuya Smart / Smart Life app (or use Tuya Developer Cloud) to extract the 16-character `local_key`.
* **Task 1.3:** Test local latency by toggling RGB colors over LAN with zero cloud delay.

### Phase 2: Windows Audio Loopback & FFT Engine
* **Task 2.1:** Implement `audio_capture.py` capturing default output stream (including FxSound audio enhancer).
* **Task 2.2:** Build a Cava-style ASCII visualizer in the terminal showing live bouncing EQ bars to verify DSP accuracy.

### Phase 3: Beat-to-Light Sync Algorithms
* **Task 3.1:** Implement kick-drum threshold detection with exponential decay to create clean, sharp beat pulses without flickers.
* **Task 3.2:** Implement mid-frequency harmonic hue shifts (smooth color wheel rotation).

### Phase 4: Tier 2 WLED / ESP32 Expansion (When Hardware Arrives)
* **Task 4.1:** Stream multi-zone Cava frequency arrays to ESP32 running WLED over UDP DDP.

---

## ⚠️ 5. Key Rules & Technical Gotchas

1. **Local LAN Only (No Cloud Polling):** Never use Tuya Cloud REST APIs during audio playback. Cloud latency is 200ms–800ms (ruins the beat sync). All commands must use direct local socket packets (`tinytuya` local mode).
2. **Socket Persistence & Rate Limiting:** Tuya bulbs can handle ~15–25 state changes per second without overflowing their internal MCU buffers. Use linear interpolation and send updates on meaningful delta changes.
3. **Audio Capture Stability:** Always use non-blocking WASAPI callback streams to prevent audio thread stuttering.
