from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Iterable
import hashlib
import json
import re
import struct
import shutil

PSEXE_MAGIC = b"PS-X EXE"
PSEXE_HEADER_SIZE = 0x800


def parse_int(value, default=None):
    if value is None:
        return default
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return default
    try:
        return int(s, 0)
    except ValueError:
        try:
            return int(s)
        except ValueError as exc:
            raise ValueError(f"Valor inválido: {value!r}") from exc


@dataclass
class BinarySource:
    path: Path
    data: bytes = field(repr=False)
    sha256: str = ""
    is_psx_exe: bool = False
    ram_destination: int = 0x80010000
    ram_base_offset: int = 0

    @classmethod
    def load(cls, path: str | Path) -> "BinarySource":
        p = Path(path)
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        is_psx = data[:8] == PSEXE_MAGIC and len(data) >= 0x1C
        ram_dest = struct.unpack("<I", data[0x18:0x1C])[0] if is_psx else 0x80010000
        return cls(
            path=p,
            data=data,
            sha256=sha,
            is_psx_exe=is_psx,
            ram_destination=ram_dest,
            ram_base_offset=PSEXE_HEADER_SIZE if is_psx else 0,
        )

    @property
    def size(self) -> int:
        return len(self.data)

    def file_to_ram(self, offset: int) -> int:
        return offset - self.ram_base_offset + self.ram_destination

    def ram_to_file(self, address: int) -> int:
        return address - self.ram_destination + self.ram_base_offset

    def bounded_slice(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError("Faixa fora dos limites do arquivo.")
        return self.data[offset:offset + size]

    def scan_value(self, value: int, dtype: str) -> list[int]:
        fmts = {"u8": "<B", "s8": "<b", "u16le": "<H", "s16le": "<h", "u32le": "<I", "s32le": "<i"}
        if dtype not in fmts:
            raise ValueError(f"Tipo não suportado: {dtype}")
        try:
            pattern = struct.pack(fmts[dtype], value)
        except struct.error as exc:
            raise ValueError(str(exc)) from exc
        return self.scan_bytes(pattern)

    def scan_bytes(self, pattern: bytes) -> list[int]:
        if not pattern:
            return []
        out = []
        pos = 0
        while True:
            pos = self.data.find(pattern, pos)
            if pos < 0:
                break
            out.append(pos)
            pos += 1
        return out

    def scan_hex_pattern(self, pattern: str) -> list[int]:
        tokens = pattern.strip().split()
        if not tokens:
            return []
        regex_parts = []
        for tok in tokens:
            if tok in ("?", "??"):
                regex_parts.append(b".")
            elif re.fullmatch(r"[0-9A-Fa-f]{2}", tok):
                regex_parts.append(re.escape(bytes([int(tok, 16)])))
            else:
                raise ValueError(f"Token inválido no padrão: {tok}")
        rx = re.compile(b"".join(regex_parts), re.DOTALL)
        return [m.start() for m in rx.finditer(self.data)]

    def scan_text(self, text: str, encoding: str = "shift_jis") -> list[int]:
        if not text:
            return []
        return self.scan_bytes(text.encode(encoding, errors="strict"))


@dataclass
class Change:
    offset: int
    old_hex: str
    new_hex: str
    label: str
    category: str = "generic"
    evidence: str = "USER-MAPPED"
    enabled: bool = True

    @property
    def old_bytes(self) -> bytes:
        return bytes.fromhex(self.old_hex)

    @property
    def new_bytes(self) -> bytes:
        return bytes.fromhex(self.new_hex)


class ChangeSet:
    def __init__(self, source: BinarySource):
        self.source = source
        self.changes: list[Change] = []
        self.undo_stack: list[list[Change]] = []
        self.redo_stack: list[list[Change]] = []

    def _snapshot(self):
        self.undo_stack.append([Change(**asdict(c)) for c in self.changes])
        self.redo_stack.clear()

    def stage(self, offset: int, new_bytes: bytes, label: str, category="generic", evidence="USER-MAPPED") -> Change:
        if offset < 0 or offset + len(new_bytes) > self.source.size:
            raise ValueError("Alteração fora dos limites do arquivo.")
        if not new_bytes:
            raise ValueError("Alteração vazia não é permitida.")
        self._snapshot()
        old = self.source.data[offset:offset + len(new_bytes)]
        # replace exact same offset+size entry to avoid duplicate conflicting writes
        self.changes = [c for c in self.changes if not (c.offset == offset and len(c.new_bytes) == len(new_bytes))]
        ch = Change(offset, old.hex().upper(), new_bytes.hex().upper(), label, category, evidence, True)
        self.changes.append(ch)
        self.changes.sort(key=lambda c: c.offset)
        return ch

    def remove(self, index: int):
        self._snapshot()
        del self.changes[index]

    def toggle(self, index: int):
        self._snapshot()
        self.changes[index].enabled = not self.changes[index].enabled

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append([Change(**asdict(c)) for c in self.changes])
        self.changes = self.undo_stack.pop()
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append([Change(**asdict(c)) for c in self.changes])
        self.changes = self.redo_stack.pop()
        return True

    def validate(self) -> list[str]:
        errors = []
        ranges = []
        for i, c in enumerate(self.changes):
            if not c.enabled:
                continue
            end = c.offset + len(c.new_bytes)
            if c.offset < 0 or end > self.source.size:
                errors.append(f"Alteração #{i+1} fora dos limites.")
            current = self.source.data[c.offset:end]
            if current.hex().upper() != c.old_hex.upper():
                errors.append(f"Alteração #{i+1} não corresponde aos bytes originais esperados.")
            for s, e, j in ranges:
                if c.offset < e and end > s:
                    errors.append(f"Alterações #{j+1} e #{i+1} se sobrepõem.")
            ranges.append((c.offset, end, i))
        return errors

    def patched_bytes(self) -> bytes:
        errors = self.validate()
        if errors:
            raise ValueError("\n".join(errors))
        out = bytearray(self.source.data)
        for c in self.changes:
            if c.enabled:
                out[c.offset:c.offset + len(c.new_bytes)] = c.new_bytes
        return bytes(out)

    def build_copy(self, output_path: str | Path) -> Path:
        out = Path(output_path)
        out.write_bytes(self.patched_bytes())
        return out

    def export_ips(self, output_path: str | Path) -> Path:
        errors = self.validate()
        if errors:
            raise ValueError("\n".join(errors))
        enabled = [c for c in self.changes if c.enabled]
        if not enabled:
            raise ValueError("Não há alterações habilitadas.")
        blob = bytearray(b"PATCH")
        for c in enabled:
            if c.offset > 0xFFFFFF:
                raise ValueError("IPS tradicional não suporta offset acima de 0xFFFFFF. Use cópia de teste/rebuild para este caso.")
            if len(c.new_bytes) > 0xFFFF:
                raise ValueError("Registro IPS excede 65535 bytes.")
            blob += c.offset.to_bytes(3, "big")
            blob += len(c.new_bytes).to_bytes(2, "big")
            blob += c.new_bytes
        blob += b"EOF"
        out = Path(output_path)
        out.write_bytes(bytes(blob))
        return out


@dataclass
class MappedRecord:
    record_type: str
    base_offset: int
    label: str
    fields: dict[str, dict]
    evidence: str = "USER-MAPPED"

    def to_dict(self):
        return asdict(self)


@dataclass
class ProjectState:
    name: str = "Projeto VH2"
    source_path: str = ""
    source_sha256: str = ""
    mapped_records: list[dict] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    appearance: dict = field(default_factory=lambda: {"directions": {}, "animation": []})
    scene: dict = field(default_factory=lambda: {"width": 12, "height": 10, "tiles": {}, "units": [], "events": []})

    def save(self, path: str | Path):
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ProjectState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def decode_scalar(data: bytes, dtype: str):
    fmts = {"u8": "<B", "s8": "<b", "u16le": "<H", "s16le": "<h", "u32le": "<I", "s32le": "<i"}
    if dtype in fmts:
        return struct.unpack(fmts[dtype], data)[0]
    if dtype.startswith("str:"):
        enc = dtype.split(":", 1)[1]
        return data.split(b"\x00", 1)[0].decode(enc, errors="replace")
    if dtype == "hex":
        return data.hex().upper()
    raise ValueError(f"Tipo não suportado: {dtype}")


def encode_scalar(value, dtype: str, size: Optional[int] = None) -> bytes:
    fmts = {"u8": "<B", "s8": "<b", "u16le": "<H", "s16le": "<h", "u32le": "<I", "s32le": "<i"}
    if dtype in fmts:
        return struct.pack(fmts[dtype], parse_int(value))
    if dtype.startswith("str:"):
        enc = dtype.split(":", 1)[1]
        raw = str(value).encode(enc)
        if size is not None:
            if len(raw) > size:
                raise ValueError(f"Texto ocupa {len(raw)} bytes, máximo {size}.")
            raw = raw + b"\x00" * (size - len(raw))
        return raw
    if dtype == "hex":
        raw = bytes.fromhex(str(value).replace(" ", ""))
        if size is not None and len(raw) != size:
            raise ValueError(f"Esperados {size} bytes, recebidos {len(raw)}.")
        return raw
    raise ValueError(f"Tipo não suportado: {dtype}")


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    val = float(n)
    for u in units:
        if val < 1024 or u == units[-1]:
            return f"{val:.1f} {u}"
        val /= 1024
