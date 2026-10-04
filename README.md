# Async 2.0: Real-Time Audio-Reactive Smart Lighting & Fast-Edit Ambilight

> **Sub-30ms local music-reactive lighting, high-performance screen sync Ambilight, physical Cava equalizer, and a Windows 11 Fluent Room Simulator.**

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%2F%2010%20(WASAPI)-0078d4?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Version](https://img.shields.io/badge/Version-2.0%20Release-purple.svg)]()
[![Latency](https://img.shields.io/badge/Latency-%3C25ms%20Local%20LAN-brightgreen.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Tuya%20%7C%20Smart%20Life%20%7C%20WLED%20%7C%20Havells-orange.svg)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ⚡ What is Async?

**Async** transforms your room into an interactive audiovisual experience. It captures system audio from Spotify, YouTube, games, and media players with zero-latency **Windows WASAPI loopback**, processes frequency spectrums using **NumPy Fast Fourier Transforms (FFT)**, captures desktop screen pixels for **Ambilight**, and drives your smart lights directly over your local Wi-Fi network with **zero cloud delay**.

Whether you have a standard **Tuya / Smart Life / Havells / Wipro** smart bulb, an **ESP32 WLED** desk strip, or **no hardware at all** (using the edge-to-edge browser room simulator), Async delivers synchronized, cinematic ambient illumination.

```
                    ┌──────────────────────────────────────────────┐
                    │          WINDOWS 11 AUDIO & SCREEN           │
                    │       (Spotify, YouTube, FxSound, Games)     │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼ (WASAPI Loopback & DWM Capture)
                    ┌──────────────────────────────────────────────┐
                    │          ASYNC 2.0 REAL-TIME DSP ENGINE      │
                    │                                              │
                    │  1. NumPy FFT Spectrum Slicing (60 FPS)      │
                    │  2. Asymmetric Transient Strobe Engine       │
                    │  3. Peak-Preserving Cadence Dispatcher       │
                    │  4. Sub-Second Self-Healing Watchdog (<350ms)│
                    └──────────────────────┬───────────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │                                 │                                 │
         ▼ (Local Wi-Fi Port 6668)         ▼ (WebSocket @ 60 FPS)            ▼ (DDP UDP Port 4048)
┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌─────────────────────────────┐
│  TIER 1: SMART BULBS        │ │  WEB ROOM SIMULATOR         │ │  TIER 2: ADDRESSABLE LEDS   │
│  (Tuya / Smart Life / Havells)│ │  (Edge-to-Edge Screen Glow) │ │  (ESP32 + WLED Desk Strips) │
│  - Whole-room ambient glow  │ │  - Windows 11 Fluent UI     │ │  - 60+ individual LED bars  │
│  - Sub-25ms response time   │ │  - Album art & Media Player │ │  - Physical Cava equalizer  │
│  - Sub-350ms self-healing   │ │  - Strobe Boost indicator   │ │  - Sub-15ms UDP streaming   │
│  - Peak-preserving cadence  │ │  - Pure Light mode [Space]  │ │  - 60 FPS real-time sync    │
└─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────┘
```

---

## 🚀 What's New in Version 2.0?

Async 2.0 solves two of the most technically challenging bottlenecks in consumer IoT smart lighting:

### 1. ⚡ Asymmetric Transient Strobe Engine (Fast Edits & Flash Shakes)
* **The Problem:** In high-tempo edits (car edits, Reels, phonk videos, and EDM strobe sequences), videos alternate rapidly between blinding white flashes and dark silhouettes (white $\leftrightarrow$ black shakes at 5–12 Hz). Traditional Exponential Moving Average (EMA) filters smooth this out into a continuous, plateaued 100% white light, ruining the effect.
* **The 2.0 Solution:**
  * **Asymmetric Attack & Decay:** Instant rise ($\alpha = 0.95$) on flash spikes, paired with an aggressive contrast plunge ($\alpha = 0.88$) down to a 26% trough floor on dark frames.
  * **Hardware-Compensated Trough Hold:** Holds the dark trough for 75ms to overcome Tuya bulb internal hardware slew ramps, allowing the physical LED phosphor to visually extinguish before the next flash hits.
  * **Result:** Razor-sharp $100\% \leftrightarrow 26\%$ strobe oscillations in both the physical room and the browser simulator.

### 2. 🛡️ Sub-Second Self-Healing Watchdog (<350ms Recovery)
* **The Problem:** Flooding the bulb's tiny Wi-Fi microcontroller (ESP8266 or Beken BK7231N) during intense burst scenes could fill its small TCP buffer, causing socket hangs. The previous 3.5-second heartbeat allowed dead sockets to linger for up to 5 seconds during critical song drops.
* **The 2.0 Solution:**
  * **Event-Driven Socket Polling:** Uses non-blocking OS `select` calls (0% CPU) to drain unread TCP ACK buffers and detect closed sockets within **8ms**.
  * **Instant Send Exception Interception:** Catches write errors immediately and executes an asynchronous reconnect in **<350ms** without freezing the main audio analysis or visualizer loop.

### 3. 🎯 Peak-Preserving Cadence Rate Limiter (16 FPS)
* Microcontroller-synchronized transmission pacing at **16 FPS (62ms)** prevents Wi-Fi buffer congestion.
* Automatically prioritizes peak flashes ($V \ge 90\%$) and trough drops ($V \le 30\%$) while coalescing noisy intermediate frames.
* Enabled **RFC 896 `TCP_NODELAY`** to eliminate Nagle buffering delays on Windows.

---

## 🌟 Core Features

### 🖥️ High-Performance Ambilight (Screen Sync)
* **30 FPS Native Capture:** Uses hardware-accelerated Windows Desktop Window Manager (DWM) frame capture with under **8ms extraction time** and **~1% CPU overhead**.
* **Smart Letterbox Cropping:** Automatically detects and crops out 16:9 / 21:9 black cinematic movie bars so dark borders never mute your lighting.
* **Cinematic Vibrancy:** Built-in saturation booster (+35%) and smooth cinema mode for movies.
* **One-Click Toggle:** Switch between Audio-Reactive music modes and Screen Ambilight with a dedicated UI toggle button or key `[5]`.

### 🎵 4 Color Decision Algorithms
* **Harmonic Flow:** Continuous melodic rotation guided by vocal momentum and lead instruments.
* **Timbre Warmth (Spectral Centroid):** Senses acoustic texture — warm amber for deep bass/lofi vs electric cyan/neon violet for bright pop and synths.
* **Chroma Pitch (Circle of Fifths):** Analyzes 12 musical pitch classes ($C, C\sharp, D, \dots, B$) in real time to match the harmonic key of the track.
* **RGB Physics:** Direct 3-band physical frequency mapping (Sub-bass = Red, Mid-range = Green, Treble = Blue).

### 💥 Bass Flash Controller
* Real-time kick drum transient detector with configurable **Intensity** (20% – 150%) and **Sensitivity** sliders.
* **3 Flash Styles:**
  * **White Flare:** Explosive white-hot flare on kick drops.
  * **Color Burst:** Saturated chromatic surge.
  * **Invert Strobe:** High-energy complementary color inversion.

### 🎧 Windows 11 Fluent Sound Output Flyout
* Integrated audio switcher powered by NirSoft tools.
* Switch between **Headphones**, **Internal Speakers**, and **FxSound** directly from the UI without touching Windows Settings.
* Automatically redirects active media processes (`brave.exe`, `chrome.exe`, `spotify.exe`, `msedge.exe`, `vlc.exe`) so playing sound transfers immediately.

### 💿 Windows Media Session & Player Controller
* Syncs with Windows System Media Transport Controls (SMTC).
* Displays live **Album Artwork**, track title, artist name, and a real-time playback progress bar.
* Built-in playback controls: Play/Pause, Next Track, and Previous Track.

---

## 🚀 Quick Start

### 1. Prerequisites
* **Windows 10 or 11** (64-bit)
* **Python 3.10+** (Python 3.11 or 3.12 recommended)

### 2. Installation
Clone the repository and install dependencies:
```powershell
git clone https://github.com/Heisenberg06969/Async.git
cd Async
pip install -r requirements.txt
```

### 3. Configuration
Copy the template configuration file:
```powershell
copy config.example.json config.json
```
Edit `config.json` with your smart bulb's IP address, Device ID, and Local Key.
*(Don't have your bulb keys yet? See the [Smart Light Setup Guide](GUIDE.md) to extract them in 5 minutes, or leave them as-is to use the **Web Simulator** preview!)*

### 4. Run
Start Async with a single click:
```cmd
start.bat
```
*(Or double-click `Async.vbs` for 100% silent, windowless background launch!)*

Async docks right into your **Windows System Tray** (notification area next to the clock):
* **Glowing Tray Icon:** Real-time color orb mimics your smart bulb's live color and strobe state.
* **Left-Click:** Instantly toggle between **Ambilight Screen Sync** and **Audio Reactive Mode**.
* **Right-Click Context Menu:** Switch lighting modes, audio decision algorithms, sound output devices, strobe boosts, and toggle "Run on Windows Startup".
* **Double-Click:** Opens the edge-to-edge **Web Room Simulator** on demand at `http://localhost:5050`.

> **Prefer the terminal Cava visualizer?** Run `start.bat --cli` or `python main.py`.

---

## 💡 Supported Smart Light Brands

Async works with over **80% of consumer smart lighting** on the market through direct local Wi-Fi control (port 6668):

| Brand / Ecosystem | Protocol | Setup Guide |
|---|---|---|
| **Havells** (Havells Sync / Digitap) | Tuya Local 3.3 / 3.5 | [Read Guide](GUIDE.md) |
| **Wipro** (Wipro Next Smart Home) | Tuya Local 3.3 | [Read Guide](GUIDE.md) |
| **Gosund** / **Treatlife** / **Lumary** | Tuya Local 3.3 | [Read Guide](GUIDE.md) |
| **Smart Life / Tuya Smart Bulbs & Strips** | Tuya Local 3.1 – 3.5 | [Read Guide](GUIDE.md) |
| **WLED** (ESP32 / ESP8266 + WS2812B) | UDP DDP (Port 4048) | [Read Guide](GUIDE.md) |
| **Zero Hardware (Browser Screen Glow)** | Web Simulator | Out of the box |

👉 **[Click here for the complete step-by-step Hardware & Brand Setup Guide](GUIDE.md)** to extract your `local_key` and configure static IPs.

---

## ⌨️ Interactive Controls & Shortcuts

| Key (Console / Web) | Action | Description |
|:---:|---|---|
| `[Space]` | Pure Light Mode | Hides all GUI panels for 100% borderless room lighting |
| `[5]` | **Toggle Ambilight** | Turns real-time screen color sync ON or OFF |
| `[F]` (CLI) / `[E]` (Web) | **Strobe Boost (2.0)** | Toggles high-tempo fast-edit shake and strobe tracking |
| `[1]` | Beat Flare | Audio-reactive mode: Ambient glow + white-hot bass kick surge |
| `[2]` | Rainbow Wave | Continuous chromatic rotation accelerated by musical tempo |
| `[3]` | Ambient Chill | Soft breathing pastel transitions for focus & study |
| `[4]` | Rave Strobe | High-contrast club strobes on percussion transients |
| `[B]` | Toggle Bass Flash | Enables or disables explosive transient flashes |
| `[T]` | Test Flash | Triggers an immediate full-power manual flash pulse |
| `[A]` | Cycle Algorithm | Switches between Harmonic Flow, Timbre Warmth, Chroma, Physics |
| `[S]` | Toggle Audio Source | Switches between Desktop Audio (Speaker) and Microphone |
| `[F]` (Web) | Fullscreen | Enters or exits browser fullscreen display |
| `[+]` / `[-]` | Sensitivity | Increases or decreases audio reactivity gain |
| `[Q]` | Quit | Cleanly shuts down audio streams, workers, and sockets |

---

## 📁 Project Structure

```
Async/
├── config.example.json            <-- Template configuration
├── config.json                    <-- Your local bulb IP, keys, and DSP settings (git-ignored)
├── start.bat / run.bat            <-- 1-click Windows batch launchers (launches silent Tray by default)
├── Async.vbs                      <-- Zero-terminal windowless VBScript launcher
├── app_tray.py                    <-- Windows System Tray application (PySide6 native menu & live glowing icon)
├── run.ps1                        <-- PowerShell launcher
├── requirements.txt               <-- Python dependencies
├── GUIDE.md                       <-- Step-by-step Hardware & Brand Setup Guide
├── main.py                        <-- Terminal Cava UI & standalone orchestration
│
├── core/
│   ├── audio_capture.py           <-- Windows WASAPI loopback capture & LIFO zero-latency queue
│   ├── dsp_engine.py              <-- NumPy FFT frequency binning, dynamic AGC & beat detection
│   ├── color_mapper.py            <-- 4 decision algorithms, HSV mapping & bass flash engine
│   ├── screen_sync.py             <-- Asymmetric Transient Strobe Engine & PySide6 DWM capture
│   └── media_session.py           <-- Windows Media Transport Controls (SMTC) & thumbnail extractor
│
├── drivers/
│   ├── tuya_driver.py             <-- Async 2.0 driver: Peak-preserving cadence & sub-350ms recovery
│   └── wled_driver.py             <-- UDP DDP streaming driver for ESP32 addressable strips
│
├── tools/
│   └── SoundVolumeView.exe        <-- NirSoft Windows audio endpoint switcher
│
└── web/
    ├── index.html                 <-- Windows 11 Fluent room simulator & interactive controller
    └── server.py                  <-- Low-latency asynchronous WebSocket & HTTP server
```

---

## 🤝 Contributing

Contributions, feature requests, and bug reports are welcome!
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat: Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
