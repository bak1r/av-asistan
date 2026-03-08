"""PCM audio encode/decode yardimcilari."""
from __future__ import annotations

import struct

import numpy as np


def float32_to_pcm16(data: np.ndarray) -> bytes:
    """Float32 [-1, 1] -> PCM 16-bit LE bytes."""
    clipped = np.clip(data, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    return pcm.tobytes()


def pcm16_to_float32(data: bytes) -> np.ndarray:
    """PCM 16-bit LE bytes -> Float32 [-1, 1]."""
    pcm = np.frombuffer(data, dtype=np.int16)
    return pcm.astype(np.float32) / 32767.0
