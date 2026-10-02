"""
WLED / ESP32 DDP (Distributed Display Protocol) UDP Streamer for Async.
Streams 60 FPS multi-band RGB LED arrays directly to WLED firmware over UDP port 4048.
"""

import socket
import logging
import numpy as np

logger = logging.getLogger("Async.WLEDDriver")

class WLEDDriver:
    DDP_PORT = 4048

    def __init__(self, ip_address: str, num_leds: int = 60):
        self.ip_address = ip_address
        self.num_leds = num_leds
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _build_ddp_packet(self, rgb_array: np.ndarray) -> bytes:
        """
        Constructs standard DDP packet header + raw RGB payload.
        Header: 10 bytes:
          0: Flags (0x40 = DDP_FLAGS_VER1, 0x01 = Push)
          1: Sequence number (0)
          2: Data type (1 = RGB)
          3: Destination ID (1)
          4..7: Offset (0)
          8..9: Data length (3 * num_leds)
        """
        payload = rgb_array.astype(np.uint8).tobytes()
        length = len(payload)
        
        header = bytearray(10)
        header[0] = 0x41 # DDP Version 1 + Push flag
        header[1] = 0x00 # Sequence
        header[2] = 0x01 # Data type: RGB 8-bit
        header[3] = 0x01 # ID
        # Offset 0
        header[8] = (length >> 8) & 0xFF
        header[9] = length & 0xFF

        return bytes(header) + payload

    def send_frame(self, rgb_array: np.ndarray):
        """Sends an RGB frame of shape (num_leds, 3) to the WLED ESP32."""
        try:
            packet = self._build_ddp_packet(rgb_array)
            self.sock.sendto(packet, (self.ip_address, self.DDP_PORT))
        except Exception as e:
            logger.debug(f"Failed to stream DDP packet: {e}")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
