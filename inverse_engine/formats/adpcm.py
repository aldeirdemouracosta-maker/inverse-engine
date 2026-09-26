"""SPU-ADPCM do PS1: blocos de 16 bytes (1 byte de shift/filtro, 1 de flags, 14 de dados = 28 amostras)."""
from __future__ import annotations

POS = (0, 60, 115, 98, 122)
NEG = (0, 0, -52, -55, -60)
FLAG_END, FLAG_REPEAT, FLAG_LOOP_START = 1, 2, 4


class AdpcmError(ValueError):
    pass


def decode(data: bytes, stop_at_end: bool = False) -> list[int]:
    """Amostras PCM 16 bits com sinal. `stop_at_end`: para no bloco com a flag de fim."""
    if len(data) % 16:
        raise AdpcmError(f"ADPCM precisa de blocos de 16 bytes (tem {len(data)} bytes)")
    out: list[int] = []
    old = older = 0
    for b in range(0, len(data), 16):
        shift = data[b] & 0x0F
        filt = (data[b] >> 4) & 0x0F
        if filt > 4:
            raise AdpcmError(f"filtro ADPCM inválido ({filt}) no bloco {b // 16}")
        if shift > 12:
            shift = 9  # valor reservado: o hardware se comporta como shift 9
        f0, f1 = POS[filt], NEG[filt]
        for k in range(28):
            byte = data[b + 2 + k // 2]
            nib = (byte >> (4 * (k & 1))) & 0x0F
            s = (nib << 12) & 0xFFFF
            if s & 0x8000:
                s -= 0x10000
            s = (s >> shift) + ((old * f0 + older * f1 + 32) >> 6)
            s = max(-32768, min(32767, s))
            out.append(s)
            older, old = old, s
        if stop_at_end and data[b + 1] & FLAG_END:
            break
    return out


def loop_info(data: bytes) -> dict:
    """Blocos com flags de laço: início, fim e se repete."""
    start = end = None
    repeat = False
    for b in range(0, len(data) - 15, 16):
        f = data[b + 1]
        if f & FLAG_LOOP_START and start is None:
            start = b // 16
        if f & FLAG_END:
            end = b // 16
            repeat = bool(f & FLAG_REPEAT)
            break
    return {"loop_start": start, "end": end, "repeat": repeat}
