"""WAV PCM 16 bits mono com o módulo `wave` da biblioteca padrão."""
from __future__ import annotations

import io
import struct
import wave


def to_bytes(samples: list[int], rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def read(data: bytes) -> tuple[list[int], int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        raw = w.readframes(w.getnframes())
        return list(struct.unpack(f"<{len(raw) // 2}h", raw)), w.getframerate()
