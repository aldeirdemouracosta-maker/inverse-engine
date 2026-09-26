"""VAB (banco de sons da Sony, PsyQ): cabeçalho VH ("pBAV") + corpo VB com amostras SPU-ADPCM. Só leitura.

VH: 32 bytes de cabeçalho, 128 programas × 16 bytes, 16 tons × 32 bytes por programa usado,
256 tamanhos de amostra (u16, em unidades de 8 bytes; a entrada 0 é reservada). O VB vem logo depois
do VH no mesmo arquivo (VAB completo) ou em outro arquivo (VH/VB separados).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from inverse_engine.formats import adpcm

MAGIC = b"pBAV"
HEADER = 32
PROGRAMS = 128
PROGRAM_SIZE = 16
TONE_SIZE = 32
TONES_PER_PROGRAM = 16
SAMPLE_TABLE = 256 * 2
DEFAULT_RATE = 44100  # a altura real depende da nota central de cada tom


class VabError(ValueError):
    pass


@dataclass(frozen=True)
class Tone:
    program: int
    index: int
    center: int
    shift: int
    min_note: int
    max_note: int
    volume: int
    pan: int
    sample: int          # índice da amostra (1…)
    adsr1: int
    adsr2: int


@dataclass
class Vab:
    offset: int                  # início do VH no arquivo
    version: int
    bank_id: int
    total_size: int              # VH + VB segundo o cabeçalho
    program_count: int
    tone_count: int
    sample_count: int
    volume: int
    pan: int
    programs: list[dict]
    tones: list[Tone]
    sample_sizes: list[int]      # bytes de cada amostra (1…sample_count)
    vh_size: int
    vb: bytes | None = field(default=None, repr=False)   # None: VB em outro arquivo (HIPOTESE)

    @property
    def inline_vb(self) -> bool:
        return self.vb is not None

    def sample_bytes(self, index: int) -> bytes:
        """ADPCM da amostra `index` (0 = primeira amostra)."""
        if self.vb is None:
            raise VabError("o VB deste VAB não está no mesmo arquivo: indique o arquivo do corpo (VB)")
        if not 0 <= index < self.sample_count:
            raise VabError(f"amostra {index} não existe (0..{self.sample_count - 1})")
        start = sum(self.sample_sizes[:index])
        return self.vb[start:start + self.sample_sizes[index]]

    def decode(self, index: int) -> list[int]:
        return adpcm.decode(self.sample_bytes(index))

    def attach_vb(self, vb: bytes) -> None:
        need = sum(self.sample_sizes)
        if len(vb) < need:
            raise VabError(f"VB tem {len(vb)} bytes; as amostras somam {need}")
        self.vb = vb


def parse(data: bytes, offset: int = 0) -> Vab:
    if data[offset:offset + 4] != MAGIC:
        raise VabError("assinatura pBAV ausente")
    if offset + HEADER > len(data):
        raise VabError("cabeçalho VH truncado")
    version, bank_id, size = struct.unpack_from("<III", data, offset + 4)
    ps, ts, vs = struct.unpack_from("<HHH", data, offset + 0x12)
    mvol, mpan = data[offset + 0x18], data[offset + 0x19]
    if not (1 <= version <= 7) or ps > PROGRAMS or ts > ps * TONES_PER_PROGRAM or not 0 < vs < 255:
        raise VabError("cabeçalho VH incoerente")
    vh_size = HEADER + PROGRAMS * PROGRAM_SIZE + ps * TONES_PER_PROGRAM * TONE_SIZE + SAMPLE_TABLE
    if offset + vh_size > len(data):
        raise VabError("VH truncado")
    p0 = offset + HEADER
    programs = []
    for i in range(PROGRAMS):
        tones, pvol, prior, mode, ppan = data[p0 + i * 16:p0 + i * 16 + 5]
        if tones:
            programs.append({"program": i, "tones": tones, "volume": pvol, "pan": ppan, "mode": mode})
    t0 = p0 + PROGRAMS * PROGRAM_SIZE
    tones = []
    for k in range(ps * TONES_PER_PROGRAM):
        b = t0 + k * TONE_SIZE
        _prior, _mode, vol, pan, center, shift, mn, mx = data[b:b + 8]
        adsr1, adsr2, prog, vag = struct.unpack_from("<HHhh", data, b + 16)
        if vag > 0:
            tones.append(Tone(prog, k % TONES_PER_PROGRAM, center, shift, mn, mx, vol, pan, vag, adsr1, adsr2))
    s0 = t0 + ps * TONES_PER_PROGRAM * TONE_SIZE
    sizes = [v * 8 for v in struct.unpack_from("<256H", data, s0)[1:vs + 1]]
    if any(sz % 16 for sz in sizes):
        raise VabError("tamanho de amostra não é múltiplo de 16 (bloco ADPCM)")
    vab = Vab(offset, version, bank_id, size, ps, ts, vs, mvol, mpan, programs, tones, sizes, vh_size)
    body = offset + vh_size
    if size == vh_size + sum(sizes) and body + sum(sizes) <= len(data):
        vab.vb = data[body:body + sum(sizes)]
    return vab


def scan(data: bytes, limit: int = 1000) -> list[Vab]:
    out = []
    pos = data.find(MAGIC)
    while pos >= 0 and len(out) < limit:
        try:
            out.append(parse(data, pos))
        except VabError:
            pass
        pos = data.find(MAGIC, pos + 4)
    return out


def scan_image(image) -> list[tuple[str, Vab]]:
    """VABs em todos os arquivos de dados (Form 2 e pastas ignorados)."""
    out = []
    for f in image.list_files():
        if f.is_dir or f.form2:
            continue
        for v in scan(image.read_file(f.path)):
            out.append((f.path, v))
    return out
