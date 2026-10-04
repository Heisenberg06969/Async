# 📖 Smart Light Hardware & Setup Guide

This guide walks you through connecting **any smart bulb or LED strip** to **Async** for ultra-low latency (<25ms) local network control without cloud delays.

---

## 💡 Supported Hardware & Brand Compatibility

Over 80% of smart home lighting sold worldwide runs on either the **Tuya / Smart Life IoT platform** or open-source **WLED (ESP32)**. If your light connects to Wi-Fi, chances are it works with Async.

### 1. Tuya / Smart Life Ecosystem (Zero New Hardware Required)
These lights are OEM products running Tuya microcontrollers. Even if the box says a different brand name, they listen on local LAN port `6668`:
* **Havells** (Havells Sync / Digitap)
* **Wipro** (Wipro Next Smart Home)
* **Gosund**
* **Treatlife**
* **Lumary**
* **Avatar Controls**
* **Novostella**
* **LSC Smart Connect** (Action)
* **Nedis SmartLife**
* **Syska Smart Lights** (Tuya-based models)
* **Generic / White-label Smart Bulbs & Strips** (any device paired using the **Smart Life** or **Tuya Smart** app)

### 2. DIY Addressable LED Strips (WLED)
* **Hardware:** ESP32 or ESP8266 microcontroller connected to **WS2812B**, **WS2811**, **SK6812**, or **APA102** addressable LED strips.
* **Firmware:** [WLED](https://kno.wled.ge/)
* **Protocol:** DDP (Distributed Display Protocol) over UDP port `4048` at 60 FPS.

### 3. No Hardware? Use the Web Room Simulator!
You don't need any smart light at all to experience Async. Async automatically launches an edge-to-edge room light simulator at `http://localhost:5050` that turns your monitor, secondary display, tablet, or phone into an edge-to-edge room lighting source.

---

## 🔑 How to Get Your Bulb's `local_key` and `device_id`

Tuya smart bulbs communicate over encrypted local Wi-Fi. To control them without relying on Tuya's cloud servers, you need:
1. **Bulb IP Address** (e.g. `192.168.1.50`)
2. **Device ID** (22 characters)
3. **Local Key** (16 characters secret encryption key)

Here is the fastest, official 5-minute method using `tinytuya`:

### Step 1: Create a Free Tuya Developer Account
1. Go to the [Tuya IoT Development Platform](https://iot.tuya.com/) and create a free account.
2. Log into the console.

### Step 2: Create a Cloud Project
1. In the left navigation bar, go to **Cloud** ➔ **Development**.
2. Click **Create Cloud Project**.
3. Enter any project name (e.g. `Async-Lighting`).
4. Select **Smart Home** for Industry and **Development** for Development Method.
5. In **Data Center**, select the region closest to you:
   * **Western America Data Center** (US)
   * **Central Europe Data Center** (EU / UK)
   * **India Data Center** (India)
   * **China Data Center**
6. Click **Create**, then click **Authorize** on the default API permissions screen.

### Step 3: Link Your Mobile App (Smart Life or Tuya Smart)
> [!TIP]
> If your bulb is currently paired with a branded app (like *Havells Sync* or *Wipro Next*), you can either keep it there if the Tuya portal links it, or re-pair it directly inside the official **Smart Life** or **Tuya Smart** app (iOS / Android) for the simplest linking.

1. In your Tuya Cloud Project, click the **Devices** tab at the top.
2. Select the **Link Tuya App Account** sub-tab.
3. Click **Add App Account**.
4. Open the **Smart Life** or **Tuya Smart** app on your phone:
   * Go to **Me** (bottom right) ➔ tap the **QR code scanner** (top right).
5. Scan the QR code displayed on your PC screen and confirm authorization.
6. All your smart bulbs will instantly appear under the **All Devices** tab in your browser!

### Step 4: Run the Automatic Key Extractor Wizard
Open PowerShell in the `Async` project directory and run:
```powershell
python -m tinytuya wizard
```
1. It will ask for your **API Key** (`Access ID`) and **API Secret** (`Access Secret`):
   * Found in your Tuya Cloud Project under **Project Overview** ➔ **Authorization Key**.
2. Select your **Data Center Region** (`us`, `eu`, `in`, `cn`).
3. The wizard will contact the Tuya API and automatically print a table of all your devices with their **Device Name**, **Device ID**, and **Local Key**!
4. It will also save these credentials to `devices.json` in your project folder.

---

## ⚙️ Router Configuration & Static IP

To prevent your router from assigning a new IP address to your bulb after a reboot:
1. Open your Wi-Fi router's admin dashboard (usually `192.168.1.1` or `192.168.0.1`).
2. Navigate to **DHCP Server** ➔ **Address Reservation** (or **Static IP Leases**).
3. Find your smart bulb's MAC address and bind it to a fixed IP (e.g. `192.168.0.51`).

> [!IMPORTANT]
> Smart bulbs only connect to **2.4 GHz Wi-Fi** networks. Make sure your PC and bulb are on the same local subnet / Wi-Fi network.

---

## 📝 Configuring `config.json`

Open `config.json` in the `Async` folder and enter your details:

```json
{
  "bulb": {
    "ip": "192.168.0.51",
    "device_id": "d73b4741da0829e032rjf7",
    "local_key": "LAR(qnKApPONka{E",
    "version": 3.3,
    "port": 6668
  },
  "audio": {
    "chunk_size": 1024,
    "bands": 28,
    "gravity": 0.82,
    "min_freq": 25.0,
    "max_freq": 16000.0
  },
  "visuals": {
    "mode": "bass_pulse",
    "bass_decay": 0.82,
    "min_brightness": 20.0
  }
}
```

### Protocol Version Guide:
* **Version 3.3:** Used by 90% of Tuya bulbs manufactured between 2019 and 2024.
* **Version 3.4 / 3.5:** Newer Tuya security chips. If version 3.3 does not respond, change `"version": 3.4` or `"version": 3.5`.
* **Version 3.1:** Older Tuya hardware (pre-2019).

---

## 🧪 Testing Your Bulb Connection

Before starting the full music visualizer, you can test your bulb connection with this quick one-liner in PowerShell:

```powershell
python -c "import json, tinytuya; cfg = json.load(open('config.json')); d = tinytuya.BulbDevice(cfg['bulb']['device_id'], cfg['bulb']['ip'], cfg['bulb']['local_key'], version=cfg['bulb']['version']); print('Status:', d.status()); d.set_colour(255, 0, 0); print('Light turned RED!')"
```

If your light turns **Red** and prints its status dictionary, your setup is complete and ready for real-time music sync!

---

## 🚦 Troubleshooting

### 1. "Failed to connect to bulb" or "Connection refused"
* **Check Wi-Fi Subnet:** Verify your PC and the bulb are on the same router subnet (e.g. both start with `192.168.1.x` or `192.168.0.x`).
* **Guest Wi-Fi Isolation:** If your bulb is on a "Guest Network", it cannot communicate with your PC. Move both to your main Wi-Fi.
* **Windows Firewall:** Ensure Windows Firewall allows outbound TCP/UDP traffic on port `6668`.

### 2. The bulb responds slowly or lags
* Async 2.0 includes an automatic **sub-second self-healing watchdog (<350ms)** and **Peak-Preserving Cadence rate limiter (16 FPS)** that prevents Wi-Fi buffer overflow and auto-reconnects instantly if packets stall.
* Check your Wi-Fi signal strength at the bulb's socket. Thick walls or metal lamp fixtures can attenuate 2.4 GHz signals.

### 3. Light stays white and doesn't change color
* The bulb is in white mode instead of RGB mode. Async automatically sends `{ "20": True, "21": "colour" }` on connect. You can also switch to color mode once in your mobile app.
