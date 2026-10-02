"""
Color & Animation Mapper Engine for Async.
Transforms real-time DSP frequency energies into dynamic HSV/RGB lighting colors.
Supports 4 Industry-Standard Color Decision Algorithms:
  1. harmonic_flow     - Melody & vocal momentum rotation
  2. spectral_centroid - Acoustic timbre warmth (warm amber vs bright icy violet)
  3. chroma_pitch      - 12-Tone musical note & chord detection (Circle of Fifths)
  4. rgb_projection    - Direct physics frequency mapping (Bass=Red, Mid=Green, Treble=Blue)
Combined with 4 Dynamic Lighting FX Presets (Beat Flare, Rainbow, Ambient, Rave Strobe).
"""

import math
import colorsys
import numpy as np
from typing import Dict, Tuple

class ColorMapper:
    MODES = ["bass_pulse", "rainbow_wave", "ambient_chill", "rave_strobe", "screen_ambilight"]
    ALGORITHMS = ["harmonic_flow", "spectral_centroid", "chroma_pitch", "rgb_projection"]

    # Circle of Fifths Synesthetic Color Wheel for 12 Semitones:
    # 0:C(Emerald), 1:C#(Violet), 2:D(Gold), 3:D#(Sky Blue), 4:E(Ruby Red), 5:F(Turquoise),
    # 6:F#(Deep Purple), 7:G(Lime), 8:G#(Indigo), 9:A(Amber), 10:A#(Cyan), 11:B(Magenta)
    NOTE_HUES = [120.0, 270.0, 60.0, 210.0, 0.0, 150.0, 290.0, 90.0, 250.0, 30.0, 180.0, 330.0]

    def __init__(self, mode: str = "bass_pulse", algorithm: str = "harmonic_flow"):
        self.mode = mode if mode in self.MODES else "bass_pulse"
        self._last_audio_mode = "bass_pulse" if self.mode == "screen_ambilight" else self.mode
        self.algorithm = algorithm if algorithm in self.ALGORITHMS else "harmonic_flow"
        
        # Color state
        self.current_hue = 180.0 # 0.0 - 360.0
        self.current_saturation = 100.0 # 0.0 - 100.0
        self.current_brightness = 35.0 # 0.0 - 100.0

        # Transient / Flash state
        self.kick_flash = 0.0
        self.min_brightness = 25.0

        # Bass Flash Controller settings
        self.bass_flash_enabled: bool = True
        self.bass_flash_intensity: float = 1.0 # 0.0 to 1.5 multiplier
        self.bass_flash_style: str = "white_flare" # "white_flare", "color_burst", "invert_strobe"

    def trigger_flash(self, intensity: float = 1.0):
        """Manually triggers an instant flash surge."""
        self.kick_flash = max(self.kick_flash, min(1.5, intensity * self.bass_flash_intensity))

    def set_bass_flash(self, enabled: bool):
        """Toggles bass flash transient bursts on kicks."""
        self.bass_flash_enabled = bool(enabled)
        if not self.bass_flash_enabled:
            self.kick_flash = 0.0

    def set_flash_intensity(self, intensity: float):
        """Sets flash intensity multiplier (0.1 - 1.5)."""
        self.bass_flash_intensity = max(0.1, min(1.5, float(intensity)))

    def set_flash_style(self, style: str):
        """Sets flash visual styling (white_flare, color_burst, invert_strobe)."""
        if style in ["white_flare", "color_burst", "invert_strobe"]:
            self.bass_flash_style = style

    def set_mode(self, mode: str):
        if mode in self.MODES:
            if mode != "screen_ambilight":
                self._last_audio_mode = mode
            self.mode = mode

    def toggle_ambilight(self) -> bool:
        """Toggles between screen_ambilight and the last active audio-reactive mode."""
        if self.mode == "screen_ambilight":
            target = getattr(self, "_last_audio_mode", "bass_pulse")
            self.mode = target
            return False
        else:
            self._last_audio_mode = self.mode
            self.mode = "screen_ambilight"
            return True

    def cycle_mode(self) -> str:
        idx = (self.MODES.index(self.mode) + 1) % len(self.MODES)
        self.mode = self.MODES[idx]
        if self.mode != "screen_ambilight":
            self._last_audio_mode = self.mode
        return self.mode

    def set_algorithm(self, algo: str):
        if algo in self.ALGORITHMS:
            self.algorithm = algo

    def cycle_algorithm(self) -> str:
        idx = (self.ALGORITHMS.index(self.algorithm) + 1) % len(self.ALGORITHMS)
        self.algorithm = self.ALGORITHMS[idx]
        return self.algorithm

    def _shortest_hue_interp(self, current: float, target: float, speed: float = 0.12) -> float:
        """Interpolates between two angles on the 360° color circle via shortest path."""
        diff = (target - current + 180.0) % 360.0 - 180.0
        return (current + diff * speed) % 360.0

    def _determine_base_hue(self, metrics: Dict[str, float]) -> Tuple[float, float]:
        """
        Calculates target Hue & base Saturation based on the selected decision algorithm.
        """
        mid = metrics["mid"]
        bass = metrics["bass"]
        treble = metrics["treble"]

        if self.algorithm == "harmonic_flow":
            # Continuous melodic flow guided by vocal & mid harmonies
            next_hue = (self.current_hue + (0.5 + mid * 1.6)) % 360.0
            return next_hue, 95.0

        elif self.algorithm == "spectral_centroid":
            # Timbre & Sound Warmth:
            # Low centroid (200Hz - 600Hz)  -> Deep Amber / Warm Red (10° - 45°)
            # Mid centroid (600Hz - 1800Hz) -> Gold to Emerald Green (55° - 140°)
            # High centroid (1800Hz - 5000Hz+) -> Electric Cyan to Neon Violet (180° - 290°)
            centroid = metrics.get("spectral_centroid", 1000.0)
            norm_c = float(np.clip((centroid - 250.0) / 3200.0, 0.0, 1.0))
            target_hue = norm_c * 290.0
            smooth_hue = self._shortest_hue_interp(self.current_hue, target_hue, speed=0.10)
            return smooth_hue, 92.0

        elif self.algorithm == "chroma_pitch":
            # 12-Tone Musical Pitch Class & Key Detection
            note_idx = metrics.get("note_idx", 0)
            target_hue = self.NOTE_HUES[note_idx % 12]
            smooth_hue = self._shortest_hue_interp(self.current_hue, target_hue, speed=0.15)
            return smooth_hue, 96.0

        elif self.algorithm == "rgb_projection":
            # Direct 3-Band Physical Wave Projection
            r_phys = float(np.clip(bass ** 1.3, 0.01, 1.0))
            g_phys = float(np.clip(mid ** 1.2, 0.01, 1.0))
            b_phys = float(np.clip(treble ** 1.2, 0.01, 1.0))
            h, s, _ = colorsys.rgb_to_hsv(r_phys, g_phys, b_phys)
            target_hue = h * 360.0
            smooth_hue = self._shortest_hue_interp(self.current_hue, target_hue, speed=0.20)
            return smooth_hue, max(75.0, s * 100.0)

        return self.current_hue, 95.0

    def update(self, metrics: Dict[str, float]) -> Tuple[Tuple[int, int, int], Tuple[float, float, float]]:
        """
        Updates color state by synthesizing the active algorithm with the lighting FX preset and bass flash controller.
        Returns:
            rgb: (r, g, b) 0-255
            hsv: (h_deg 0-360, s_pct 0-100, v_pct 0-100)
        """
        bass = metrics["bass"]
        mid = metrics["mid"]
        treble = metrics["treble"]
        is_kick = metrics["is_kick"]

        # Step 1: Compute Base Hue & Saturation from Active Algorithm
        base_hue, base_sat = self._determine_base_hue(metrics)
        self.current_hue = base_hue

        # Step 2: Update Kick Flash State & Decay
        self.kick_flash = max(0.0, self.kick_flash * 0.72) # Fast ~100ms decay
        if self.bass_flash_enabled:
            if is_kick:
                self.kick_flash = max(self.kick_flash, 1.0 * self.bass_flash_intensity)
            elif bass > 0.72:
                surge = ((bass - 0.72) / 0.28) * self.bass_flash_intensity
                self.kick_flash = max(self.kick_flash, surge * 0.85)
        else:
            self.kick_flash = 0.0

        # Step 3: Apply Lighting FX Profile (Beat Flare, Rainbow, Ambient Chill, Rave Strobe)
        if self.mode == "bass_pulse":
            baseline_brightness = 28.0 + (mid * 18.0)

            if self.bass_flash_enabled and self.kick_flash > 0.02:
                flash_amount = min(1.0, self.kick_flash)
                if self.bass_flash_style == "white_flare":
                    # Luminous white-hot flare tint (drop saturation on hit)
                    self.current_saturation = max(0.0, base_sat - (flash_amount * 75.0))
                elif self.bass_flash_style == "color_burst":
                    # Punchy pure saturated color
                    self.current_saturation = 100.0
                elif self.bass_flash_style == "invert_strobe":
                    # Complementary inverted hue flash
                    self.current_hue = (base_hue + 180.0 * flash_amount) % 360.0
                    self.current_saturation = 100.0

                # Brightness surge to 100% on flash
                target_brightness = baseline_brightness + (flash_amount * (100.0 - baseline_brightness))
            else:
                # Smooth ambient bass pulse without jarring flash
                self.current_saturation = base_sat
                target_brightness = baseline_brightness + (bass * 28.0)

            if target_brightness > self.current_brightness:
                self.current_brightness = target_brightness
            else:
                self.current_brightness = max(baseline_brightness, self.current_brightness * 0.80)

        elif self.mode == "rainbow_wave":
            # Override hue to continuous rainbow progression
            energy = (bass * 0.4 + mid * 0.4 + treble * 0.2)
            self.current_hue = (self.current_hue + (1.5 + energy * 4.0)) % 360.0
            
            if self.bass_flash_enabled and self.kick_flash > 0.02:
                flash_amount = min(1.0, self.kick_flash)
                if self.bass_flash_style == "white_flare":
                    self.current_saturation = max(0.0, base_sat - (flash_amount * 75.0))
                elif self.bass_flash_style == "invert_strobe":
                    self.current_hue = (self.current_hue + 180.0 * flash_amount) % 360.0
                    self.current_saturation = 100.0
                else:
                    self.current_saturation = 100.0
                target_brightness = min(100.0, self.min_brightness + energy * 50.0 + flash_amount * 50.0)
            else:
                self.current_saturation = base_sat
                target_brightness = self.min_brightness + energy * (100.0 - self.min_brightness)
            self.current_brightness = max(target_brightness, self.current_brightness * 0.90)

        elif self.mode == "ambient_chill":
            # Relaxed breathing pastel
            self.current_saturation = min(base_sat, 68.0)
            target_brightness = 35.0 + (mid * 35.0)
            if self.bass_flash_enabled and self.kick_flash > 0.02:
                flash_amount = min(1.0, self.kick_flash)
                target_brightness = min(100.0, target_brightness + flash_amount * 45.0)
                if self.bass_flash_style == "white_flare":
                    self.current_saturation = max(10.0, self.current_saturation - flash_amount * 40.0)
            self.current_brightness = (self.current_brightness * 0.94) + (target_brightness * 0.06)

        elif self.mode == "rave_strobe":
            # Club Strobe
            if self.bass_flash_enabled and (is_kick or self.kick_flash > 0.1):
                if self.bass_flash_style == "invert_strobe":
                    self.current_hue = (self.current_hue + 180.0) % 360.0
                else:
                    self.current_hue = (self.current_hue + 60.0) % 360.0
                self.current_saturation = 15.0 if self.bass_flash_style == "white_flare" else 100.0
                self.current_brightness = 100.0
            elif treble > 0.85:
                self.current_saturation = 15.0 # White transient flash
                self.current_brightness = 100.0
            else:
                self.current_saturation = base_sat
                self.current_brightness = max(18.0, self.current_brightness * 0.75)

        # Convert HSV (0-1) to RGB (0-255)
        h_norm = self.current_hue / 360.0
        s_norm = max(0.0, min(1.0, self.current_saturation / 100.0))
        v_norm = max(0.0, min(1.0, self.current_brightness / 100.0))

        r, g, b = colorsys.hsv_to_rgb(h_norm, s_norm, v_norm)
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        hsv = (self.current_hue, self.current_saturation, self.current_brightness)

        return rgb, hsv

    def to_tuya_hex(self, hue: float, sat: float, val: float) -> str:
        """Converts HSV to Tuya 12-char DPS 24 hex string (HHHHSSSSVVVV)."""
        h_int = int(hue) % 360
        s_int = int(sat * 10.0)
        v_int = int(val * 10.0)
        return f"{h_int:04x}{s_int:04x}{v_int:04x}"
