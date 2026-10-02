# 🌈 Async: Real-Time Audio-Reactive Smart Lighting & Ambilight

> **Sub-30ms local music-reactive lighting, high-performance screen sync Ambilight, physical Cava equalizer, and a Windows 11 Fluent Room Simulator.**

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%2F%2010%20(WASAPI)-0078d4?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Latency](https://img.shields.io/badge/Latency-%3C25ms%20Local%20LAN-brightgreen.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Tuya%20%7C%20Smart%20Life%20%7C%20WLED%20%7C%20Havells-orange.svg)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ⚡ What is Async?

**Async** transforms your room into an interactive audiovisual experience. It captures system audio from Spotify, YouTube, games, and media players with zero-latency **Windows WASAPI loopback**, processes frequency spectrums using **NumPy Fast Fourier Transforms (FFT)**, and drives your smart lights directly over your local Wi-Fi network with **zero cloud delay**.

Whether you have a standard **Tuya / Smart Life / Havells / Wipro** smart bulb, an **ESP32 WLED** desk strip, or **no hardware at all** (using the edge-to-edge browser room simulator), Async delivers synchronized, cinematic ambient illumination.

```
                    ┌──────────────────────────────────────────────┐
                    │          WINDOWS 11 AUDIO OUTPUT             │
                    │       (Spotify, YouTube, FxSound, Games)     │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼ (WASAPI Loopback Capture)
                    ┌──────────────────────────────────────────────┐
                    │          ASYNC REAL-TIME DSP ENGINE          │
                    │                                              │
                    │  1. NumPy FFT Spectrum Slicing (45+ FPS)     │
                    │  2. Dynamic AGC & Kick Drum Beat Detection   │
                    │  3. 4 Decision Algorithms (Chroma / Physics) │
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
│  - Automatic watchdog probe │ │  - Pure Light mode [Space]  │ │  - Sub-15ms UDP streaming   │
└─────────────────────────────┘ └─────────────────────────────┘ └─────────────────────────────┘
```

---

## 🌟 Key Features

### 🖥️ High-Performance Ambilight (Screen Sync)
* **30 FPS Native Capture:** Uses hardware-accelerated Windows Desktop Window Manager (DWM) frame capture with under **8ms frame extraction time** and **~1% CPU overhead**.
* **Smart Letterbox Cropping:** Automatically detects and crops out 16:9 / 21:9 black cinematic movie bars so dark borders never mute your lighting.
* **Cinematic Vibrancy:** Built-in saturation booster (+35%) and Exponential Moving Average (EMA) temporal smoothing prevent jarring strobe flickers during movies and games.
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

### 🛡️ Self-Healing Background Architecture
* **Non-Blocking Worker:** Smart light transmissions run on an independent background thread so network jitter never stalls audio analysis or the visualizer.
* **3.5-Second Health Watchdog:** Actively sends heartbeat probes over port 6668 to monitor connection health and measure round-trip ping.
* **Auto-Reconnect:** If a Wi-Fi packet drops or the light reboots, Async force-closes the socket and auto-reconnects within 2 seconds.
* **Zero-Delay Audio Queue:** LIFO queue drainage ensures 100% zero-latency audio sync with no stale buffer buildup.

---

## 🚀 Quick Start

### 1. Prerequisites
* **Windows 10 or 11** (64-bit)
* **Python 3.10+** (Python 3.11 or 3.12 recommended)

### 2. Installation
Clone the repository and install dependencies:
```powershell
git clone https://github.com/your-username/async-lighting.git
cd async-lighting
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
*(Or run `python main.py` in your terminal)*

Async will start the terminal Cava equalizer, connect to your smart bulb, and automatically open the **Web Room Simulator** at `http://localhost:5050`.

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

| Key | Web / Console Action | Description |
|:---:|---|---|
| `[Space]` | Pure Light Mode | Hides all GUI panels for 100% borderless room lighting |
| `[5]` | **Toggle Ambilight** | Turns real-time screen color sync ON or OFF |
| `[1]` | Beat Flare | Audio-reactive mode: Ambient glow + white-hot bass kick surge |
| `[2]` | Rainbow Wave | Continuous chromatic rotation accelerated by musical tempo |
| `[3]` | Ambient Chill | Soft breathing pastel transitions for focus & study |
| `[4]` | Rave Strobe | High-contrast club strobes on percussion transients |
| `[B]` | Toggle Bass Flash | Enables or disables explosive transient flashes |
| `[T]` | Test Flash | Triggers an immediate full-power manual flash pulse |
| `[A]` | Cycle Algorithm | Switches between Harmonic Flow, Timbre Warmth, Chroma, Physics |
| `[S]` | Toggle Audio Source | Switches between Desktop Audio (Speaker) and Microphone |
| `[F]` | Fullscreen | Enters or exits browser fullscreen display |
| `[+]` / `[-]` | Sensitivity | Increases or decreases audio reactivity gain |
| `[Q]` | Quit | Cleanly shuts down audio streams, workers, and sockets |

---

## 📁 Project Structure

```
async-lighting/
├── config.example.json            <-- Template configuration
├── config.json                    <-- Your local bulb IP, keys, and DSP settings (git-ignored)
├── start.bat / run.bat            <-- 1-click Windows batch launchers (UTF-8, smart Python detection)
├── run.ps1                        <-- PowerShell launcher
├── requirements.txt               <-- Python dependencies
├── GUIDE.md                       <-- Step-by-step Hardware & Brand Setup Guide
├── main.py                        <-- Main loop, Cava terminal UI & orchestration
│
├── core/
│   ├── audio_capture.py           <-- Windows WASAPI loopback capture & LIFO zero-latency queue
│   ├── dsp_engine.py              <-- NumPy FFT frequency binning, dynamic AGC & beat detection
│   ├── color_mapper.py            <-- 4 decision algorithms, HSV mapping & bass flash engine
│   ├── screen_sync.py             <-- 30 FPS PySide6 DWM desktop capture & Ambilight processor
│   └── media_session.py           <-- Windows Media Transport Controls (SMTC) & thumbnail extractor
│
├── drivers/
│   ├── tuya_driver.py             <-- Non-blocking worker, 3.5s health watchdog & Tuya local driver
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
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
