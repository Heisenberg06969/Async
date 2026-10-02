# 🌈 Async: Real-Time Audio-Reactive Smart Lighting System

> **Vision:** Bring the iconic multi-band audio visualizer experience (like **Cava** on Linux/terminal) into the physical room, syncing ambient lighting and addressable LED strips with live PC audio, beats, and frequency spectrums in sub-30ms real time.

---

## 🎯 1. Mission & Core Concept

**Async** (**A**udio-**Sync** / **Asynchronous** streaming) captures live desktop audio output (from Brave, Spotify, YouTube, games, or media players via Windows WASAPI Loopback), computes real-time Fast Fourier Transform (FFT) frequency spectrums, and drives smart lights dynamically:

* **Bass / Kick Drums (20 Hz – 250 Hz):** Drives brightness pulses, strobe hits, and high-energy dynamics.
* **Mid-Range / Vocals & Melodies (250 Hz – 2,000 Hz):** Drives smooth color hue transitions (HSV color space shifting).
* **Treble / Hi-Hats & Cymbals (2,000 Hz – 20,000 Hz):** Drives micro-shimmers, high-frequency energy spikes, and edge strobes.

---

## 🏗️ 2. Two-Tier Hardware & Deployment Architecture

```
                      ┌──────────────────────────────────────────────┐
                      │          WINDOWS 11 AUDIO OUTPUT             │
                      │       (Brave, Spotify, FxSound, Games)       │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼ (WASAPI Loopback Capture)
                      ┌──────────────────────────────────────────────┐
                      │          ASYNC REAL-TIME DSP ENGINE          │
                      │                                              │
                      │  1. NumPy FFT Spectrum Slicing (60 FPS)      │
                      │  2. Beat Energy & Spectral Flux Detection    │
                      │  3. HSV Color & Dynamic Brightness Mapper    │
                      └──────────────────────┬───────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       │                                           │
         (Local Wi-Fi Tuya UDP / Port 6668)         (DDP / E1.31 / UDP Streaming)
                       ▼                                           ▼
       ┌───────────────────────────────┐           ┌───────────────────────────────┐
       │   TIER 1: EXISTING SMART BULB │           │   TIER 2: "CAVA" LED BAR      │
       │   (Havells Smart Light / Tuya)│           │   (ESP32 + WS2812B Strip)     │
       │                               │           │                               │
       │  - Whole-room ambient glow    │           │  - 60+ individual LED bars    │
       │  - Zero new hardware needed   │           │  - Multi-band spectrum visual │
       │  - Direct local LAN control   │           │  - Physical Cava on your desk │
       └───────────────────────────────┘           └───────────────────────────────┘
```

---

## 🔬 3. Tier 1: Existing Havells Smart Light (Zero-Cost Software Bridge)

### How Havells Smart Lights Work Under the Hood:
* In India, **Havells Smart Lights** (controlled via *Havells Sync* or *Havells Digitap*) are OEM devices built on the **Tuya / Smart Life IoT platform**.
* They listen for encrypted UDP/TCP packets on local Wi-Fi (**Ports 6667 / 6668**).
* **Cloud Bypass:** By extracting the light's `device_id`, `ip_address`, and 16-character `local_key` (via the free Tuya Developer Portal or `tinytuya scan`), your PC can control the light directly on your home LAN with **sub-40ms latency**, completely bypassing cloud servers.

### Supported Modes for Tier 1:
1. **Pulse on Bass (Kick Beat):** Brightness drops to 30% baseline and surges to 100% on bass drops.
2. **Harmonic Hue Cycle:** Color temperature or RGB hue continuously shifts based on the musical key / dominant mid frequencies.
3. **Chill Ambient Reactive:** Subtle, smoothed brightness changes for background focus listening.

---

## ⚡ 4. Tier 2: The Physical "Cava" Desk Equalizer (ESP32 + Addressable LEDs)

### The Vision:
An addressable LED strip (WS2812B or SK6812) mounted behind your monitor or along your desk, functioning as a real-time physical **Cava frequency bar**:
* **Left Segment (LEDs 1–20):** Bass / Sub-Bass amplitude (Red / Orange glow rising with kick drums).
* **Center Segment (LEDs 21–40):** Mid-range vocals (Cyan / Purple waves).
* **Right Segment (LEDs 41–60):** Treble cymbals (White / Electric Blue flashes).

### Hardware Components:
* **Controller:** ESP32 Dev Board (NodeMCU-32S / ESP-WROOM-32) (~₹250 / $3).
* **Firmware:** **WLED** (Open-source, ultra-fast ESP32 LED driver with native UDP DDP protocol).
* **LED Strip:** WS2812B 5V 60 LEDs/meter (~₹400 / $5).
* **Data Protocol:** PC streams raw RGB byte arrays over UDP (`DDP: Distributed Display Protocol` at 60 FPS).

---

## 📊 5. Audio Analysis Pipeline & Math

$$\text{Audio Signal } x(t) \xrightarrow{\text{WASAPI Loopback (44.1kHz)}} \text{Chunk (1024 samples)} \xrightarrow{\text{NumPy FFT}} |X(f)|$$

1. **Band Energy Summation:**
   $$E_{\text{bass}} = \sum_{f=20}^{250} |X(f)|^2, \quad E_{\text{mid}} = \sum_{f=250}^{2000} |X(f)|^2, \quad E_{\text{treble}} = \sum_{f=2000}^{20000} |X(f)|^2$$
2. **Dynamic Decay & Smoothing:**
   $$\text{Brightness}(t) = \max\left(E_{\text{bass}}(t), \text{Brightness}(t-1) \times \text{DecayFactor}\right)$$
3. **HSV to RGB Mapping:**
   $$\text{Hue} = \left(\text{Hue}_{\text{prev}} + \Delta \text{Mid}\right) \bmod 360$$
