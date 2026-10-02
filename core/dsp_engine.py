"""
Real-Time Audio DSP Engine for Async.
Performs Fast Fourier Transform (FFT) analysis, logarithmic frequency binning,
dynamic AGC normalization, Cava gravity falloff, and kick drum beat detection.
"""

from typing import Tuple, List, Dict
import numpy as np

class DSPEngine:
    def __init__(
        self,
        num_bands: int = 24,
        sample_rate: int = 44100,
        chunk_size: int = 1024,
        min_freq: float = 25.0,
        max_freq: float = 16000.0,
        gravity: float = 0.85
    ):
        self.num_bands = num_bands
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.min_freq = min_freq
        self.max_freq = max_freq
        self.gravity = gravity

        # Hanning window to prevent spectral leakage
        self.window = np.hanning(chunk_size)

        # FFT frequency bins
        self.fft_freqs = np.fft.rfftfreq(chunk_size, 1.0 / sample_rate)

        # Logarithmic frequency boundaries for Cava equalizer bars
        self.band_cutoffs = np.logspace(
            np.log10(min_freq),
            np.log10(max_freq),
            num_bands + 1
        )

        # State buffers
        self.smooth_bars = np.zeros(num_bands, dtype=np.float32)
        self.peak_bars = np.zeros(num_bands, dtype=np.float32)
        
        # Energy metrics for lighting
        self.bass_energy = 0.0
        self.mid_energy = 0.0
        self.treble_energy = 0.0
        
        # Beat / Kick detector state
        self.bass_history: List[float] = []
        self.max_history_len = 45 # ~1 second of frames
        self.is_kick: bool = False
        self.kick_cooldown = 0
        self.kick_threshold: float = 0.38 # Configurable bass trigger threshold (0.15 - 0.75)
        self.kick_ratio: float = 1.22
        
        # Automatic Gain Control (AGC) state
        self.rolling_max = 0.01

        # Chroma pitch class masks (65 Hz to 3500 Hz)
        self.chroma_mask = (self.fft_freqs >= 65.0) & (self.fft_freqs <= 3500.0)
        self.chroma_freqs = self.fft_freqs[self.chroma_mask]
        midi_nums = np.round(12.0 * np.log2(self.chroma_freqs / 440.0) + 69.0).astype(int)
        self.pitch_classes = midi_nums % 12
        self.note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        self.smooth_chroma = np.zeros(12, dtype=np.float32)
        self.smooth_centroid = 1000.0

    def set_sample_rate(self, sample_rate: int):
        """Updates sample rate and recomputes FFT and Chroma frequency bins."""
        if self.sample_rate == sample_rate:
            return
        self.sample_rate = sample_rate
        self.fft_freqs = np.fft.rfftfreq(self.chunk_size, 1.0 / sample_rate)
        self.chroma_mask = (self.fft_freqs >= 65.0) & (self.fft_freqs <= 3500.0)
        self.chroma_freqs = self.fft_freqs[self.chroma_mask]
        midi_nums = np.round(12.0 * np.log2(self.chroma_freqs / 440.0) + 69.0).astype(int)
        self.pitch_classes = midi_nums % 12

    def reset(self):
        """Resets AGC and smoothing buffers (e.g. on audio source switch)."""
        self.smooth_bars.fill(0)
        self.peak_bars.fill(0)
        self.bass_history.clear()
        self.rolling_max = 0.01
        self.smooth_chroma.fill(0)
        self.smooth_centroid = 1000.0

    def set_kick_threshold(self, threshold: float):
        """Sets the normalized bass threshold required to register a kick hit (0.15 - 0.75)."""
        self.kick_threshold = float(np.clip(threshold, 0.15, 0.75))

    def process(self, chunk: np.ndarray) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        Processes a raw audio chunk.
        Returns:
            bands: Normalized [0.0 - 1.0] array of Cava EQ bars.
            metrics: Dictionary containing bass, mid, treble, and kick detection.
        """
        if len(chunk) < self.chunk_size:
            # Pad if chunk is slightly smaller
            chunk = np.pad(chunk, (0, self.chunk_size - len(chunk)))
        elif len(chunk) > self.chunk_size:
            chunk = chunk[:self.chunk_size]

        # 1. Apply Window & FFT
        windowed = chunk * self.window
        fft_spectrum = np.abs(np.fft.rfft(windowed))

        # 2. Extract Lighting Bands (Bass: 20-250Hz, Mids: 250-2000Hz, Treble: 2000-16000Hz)
        bass_mask = (self.fft_freqs >= 20.0) & (self.fft_freqs <= 250.0)
        mid_mask = (self.fft_freqs > 250.0) & (self.fft_freqs <= 2000.0)
        treble_mask = (self.fft_freqs > 2000.0) & (self.fft_freqs <= 16000.0)

        raw_bass = np.sum(fft_spectrum[bass_mask] ** 2) if np.any(bass_mask) else 0.0
        raw_mid = np.sum(fft_spectrum[mid_mask] ** 2) if np.any(mid_mask) else 0.0
        raw_treble = np.sum(fft_spectrum[treble_mask] ** 2) if np.any(treble_mask) else 0.0

        # Log-scale magnitude
        bass_mag = float(np.log1p(raw_bass))
        mid_mag = float(np.log1p(raw_mid))
        treble_mag = float(np.log1p(raw_treble))

        # 3. Dynamic AGC Tracking
        current_max = max(bass_mag, mid_mag, treble_mag, 0.01)
        if current_max > self.rolling_max:
            self.rolling_max = current_max # Instant rise
        else:
            self.rolling_max = max(self.rolling_max * 0.992, 0.01) # Slow decay (~2 sec)

        norm_bass = min(1.0, bass_mag / self.rolling_max)
        norm_mid = min(1.0, mid_mag / self.rolling_max)
        norm_treble = min(1.0, treble_mag / self.rolling_max)

        self.bass_energy = norm_bass
        self.mid_energy = norm_mid
        self.treble_energy = norm_treble

        # 4. Kick Drum Detection
        self.bass_history.append(bass_mag)
        if len(self.bass_history) > self.max_history_len:
            self.bass_history.pop(0)

        avg_bass = np.mean(self.bass_history) if self.bass_history else 0.01
        
        self.is_kick = False
        if self.kick_cooldown > 0:
            self.kick_cooldown -= 1
        elif norm_bass > self.kick_threshold and (bass_mag > (avg_bass * self.kick_ratio) or norm_bass > (self.kick_threshold * 1.9)):
            self.is_kick = True
            self.kick_cooldown = 4 # ~90ms debounce to avoid double trigger

        # 5. Equalizer Log-Bands Slicing (Cava bars)
        raw_bands = np.zeros(self.num_bands, dtype=np.float32)
        for i in range(self.num_bands):
            f_low = self.band_cutoffs[i]
            f_high = self.band_cutoffs[i + 1]
            mask = (self.fft_freqs >= f_low) & (self.fft_freqs < f_high)
            if np.any(mask):
                # Calculate mean power in this band
                power = np.mean(fft_spectrum[mask])
                raw_bands[i] = np.log1p(power)

        # Normalize bands with perceptual curve (boost high frequencies slightly)
        boost = np.linspace(1.0, 1.8, self.num_bands)
        norm_bands = (raw_bands * boost) / (self.rolling_max * 0.4 + 1e-5)
        norm_bands = np.clip(norm_bands, 0.0, 1.0)

        # 6. Apply Cava Falling Gravity / Peak smoothing
        # If new value is higher, jump immediately; otherwise fall smoothly
        self.smooth_bars = np.maximum(norm_bands, self.smooth_bars * self.gravity)

        # 7. Compute Spectral Centroid (Timbre & Warmth vs Crispness)
        sum_mag = np.sum(fft_spectrum)
        if sum_mag > 1e-4:
            raw_centroid = float(np.sum(self.fft_freqs * fft_spectrum) / sum_mag)
        else:
            raw_centroid = 800.0
        self.smooth_centroid = float(0.85 * self.smooth_centroid + 0.15 * raw_centroid)

        # 8. Compute Chromagram (12-Tone Musical Pitch Detection)
        raw_chroma = np.zeros(12, dtype=np.float32)
        if np.any(self.chroma_mask):
            spec_chroma = fft_spectrum[self.chroma_mask]
            for pc in range(12):
                mask_pc = (self.pitch_classes == pc)
                if np.any(mask_pc):
                    raw_chroma[pc] = float(np.sum(spec_chroma[mask_pc]))

        self.smooth_chroma = 0.80 * self.smooth_chroma + 0.20 * raw_chroma
        dominant_idx = int(np.argmax(self.smooth_chroma))
        dominant_note = self.note_names[dominant_idx]

        metrics = {
            "bass": self.bass_energy,
            "mid": self.mid_energy,
            "treble": self.treble_energy,
            "is_kick": self.is_kick,
            "rolling_max": self.rolling_max,
            "spectral_centroid": round(self.smooth_centroid, 1),
            "dominant_note": dominant_note,
            "note_idx": dominant_idx,
            "chroma": [round(float(c), 3) for c in self.smooth_chroma]
        }

        return self.smooth_bars, metrics
