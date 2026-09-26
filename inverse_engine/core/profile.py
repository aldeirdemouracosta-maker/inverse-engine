"""RomProfile: perfil de jogo em JSON (dados, não código) e identificação por âncoras.

A versão não é decidida pelo SHA-256 da imagem inteira (muda conforme a cópia do disco ou
patches como o Take Turns). O hash inteiro só registra qual arquivo foi usado; a decisão
"estes offsets valem aqui" vem das âncoras.
"""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats.psexe import PsExe

TYPES = {"u8": ("<B", 1), "s8": ("<b", 1), "u16le": ("<H", 2), "s16le": ("<h", 2),
         "u32le": ("<I", 4), "s32le": ("<i", 4)}
NAME_MAX = 64


def hexint(v) -> int:
    return v if isinstance(v, int) else int(str(v), 0)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    offset: int
    type: str
    finding: str | None = None

    @property
    def size(self) -> int:
        return TYPES[self.type][1]


@dataclass
class TableSpec:
    name: str
    file: str
    offset: int
    stride: int
    count: int
    fields: dict[str, FieldSpec]
    finding: str | None = None
    names_pointer_table: int | None = None
    names_finding: str | None = None
    groups: list[dict] = field(default_factory=list)
    integrity_sha256: str | None = None
    names_shift: int = 0              # registro i usa o ponteiro i + shift (só depois de confirmado)
    names_status: str | None = None   # estado da hipótese dos nomes (informativo)

    @classmethod
    def from_json(cls, name: str, d: dict) -> "TableSpec":
        fields = {k: FieldSpec(k, hexint(v["offset"]), v["type"], v.get("finding"))
                  for k, v in d.get("fields", {}).items()}
        for f in fields.values():
            if f.type not in TYPES:
                raise ValueError(f"{name}.{f.name}: tipo {f.type} não suportado")
            if f.offset + f.size > d["stride"]:
                raise ValueError(f"{name}.{f.name}: campo passa do fim do registro")
        names = d.get("names") or {}
        pt = names.get("pointer_table")
        return cls(name, d["file"], hexint(d["offset"]), d["stride"], d["count"], fields,
                   d.get("finding"), hexint(pt) if pt is not None else None,
                   names.get("finding"), d.get("groups", []), d.get("integrity_sha256"),
                   int(names.get("shift", 0)), names.get("status"))

    @property
    def end(self) -> int:
        return self.offset + self.stride * self.count

    def record_offset(self, index: int) -> int:
        if not 0 <= index < self.count:
            raise IndexError(f"{self.name}[{index}] fora da tabela (0..{self.count - 1})")
        return self.offset + index * self.stride

    def field_offset(self, index: int, field_name: str) -> int:
        return self.record_offset(index) + self.fields[field_name].offset

    def read_record(self, data: bytes, index: int) -> bytes:
        start = self.record_offset(index)
        return data[start:start + self.stride]

    def read_field(self, data: bytes, index: int, field_name: str) -> int:
        f = self.fields[field_name]
        return struct.unpack_from(TYPES[f.type][0], data, self.field_offset(index, field_name))[0]

    def read_name(self, data: bytes, index: int) -> str | None:
        """Nome pela matriz de ponteiros (u32le, endereço de RAM). None se não resolver."""
        if self.names_pointer_table is None or not 0 <= index < self.count:
            return None
        ptr_at = self.names_pointer_table + (index + self.names_shift) * 4
        if ptr_at + 4 > len(data):
            return None
        ptr = struct.unpack_from("<I", data, ptr_at)[0]
        try:
            off = PsExe.parse(data).ram_to_file(ptr)
        except ValueError:
            return None
        if not 0 <= off < len(data):
            return None
        raw = data[off:off + NAME_MAX].split(b"\x00", 1)[0]
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError:
            return None

    def name_slot(self, data: bytes, index: int) -> tuple[int, int] | None:
        """(offset no arquivo, bytes do texto atual sem o NUL) do nome; espaço máximo para editar sem realocar."""
        if self.names_pointer_table is None or not 0 <= index < self.count:
            return None
        ptr = struct.unpack_from("<I", data, self.names_pointer_table + (index + self.names_shift) * 4)[0]
        try:
            off = PsExe.parse(data).ram_to_file(ptr)
        except ValueError:
            return None
        if not 0 <= off < len(data):
            return None
        return off, len(data[off:off + NAME_MAX].split(b"\x00", 1)[0])

    def integrity(self, data: bytes) -> bool | None:
        """Confere o hash da tabela (None quando o perfil não tem hash para ela)."""
        if not self.integrity_sha256:
            return None
        return hashlib.sha256(data[self.offset:self.end]).hexdigest() == self.integrity_sha256.lower()

    def category(self, index: int) -> str | None:
        for g in self.groups:
            if g["start"] <= index <= g["end"]:
                return g["category"]
        return None


@dataclass(frozen=True)
class AnchorResult:
    type: str
    ok: bool
    detail: str
    meaning: str = ""


@dataclass
class ProfileMatch:
    profile_id: str
    anchors: list[AnchorResult]
    applies: bool          # todas as âncoras `required` passaram
    integrity_ok: bool     # todas as âncoras `table_integrity` passaram
    image_sha256: str
    known_image: str | None  # nota da imagem conhecida, se o hash inteiro bater

    def summary(self) -> str:
        if not self.applies:
            return "perfil NÃO se aplica: nenhuma edição por perfil"
        if not self.integrity_ok:
            return "perfil se aplica, mas a tabela foi alterada por algum patch base (confirmar para continuar)"
        return "perfil se aplica"


class RomProfile:
    def __init__(self, data: dict, source: Path | None = None):
        self.raw = data
        self.source = source
        self.profile_id: str = data["profile_id"]
        self.game: str = data.get("game", "")
        self.executable: str = data["executable"]["name"]
        ident = data["identify"]
        self.anchors: list[dict] = ident["anchors"]
        self.required: list[str] = ident.get("required", [])
        self.table_integrity: list[str] = ident.get("table_integrity", [])
        self.known_images: list[dict] = data.get("known_images", [])
        self.tables = {k: TableSpec.from_json(k, v) for k, v in data.get("tables", {}).items()}

    @classmethod
    def load(cls, path: str | Path) -> "RomProfile":
        p = Path(path)
        return cls(json.loads(p.read_text(encoding="utf-8")), p)

    @classmethod
    def load_all(cls, folder: str | Path) -> list["RomProfile"]:
        return [cls.load(p) for p in sorted(Path(folder).glob("*.json"))]

    def table(self, name: str) -> TableSpec:
        return self.tables[name]

    # --- âncoras --------------------------------------------------------
    def evaluate(self, image: RomImage) -> ProfileMatch:
        cache: dict[str, bytes | None] = {}

        def file_bytes(name: str) -> bytes | None:
            if name not in cache:
                if image.has_file(name):
                    cache[name] = image.read_file(name)
                elif image.kind == "file" and name == self.executable:
                    cache[name] = image.data  # executável avulso com outro nome de arquivo
                else:
                    cache[name] = None
            return cache[name]

        results = [self._check(a, file_bytes) for a in self.anchors]
        by_type: dict[str, list[bool]] = {}
        for r in results:
            by_type.setdefault(r.type, []).append(r.ok)

        def all_pass(types: list[str]) -> bool:
            return all(t in by_type and all(by_type[t]) for t in types)

        known = next((k.get("note", k.get("kind", "")) for k in self.known_images
                      if k.get("sha256") == image.sha256), None)
        return ProfileMatch(self.profile_id, results, all_pass(self.required),
                            all_pass(self.table_integrity), image.sha256, known)

    def _check(self, a: dict, file_bytes) -> AnchorResult:
        t = a["type"]
        meaning = a.get("meaning", "")
        if t in ("bytes", "sha256_range"):
            data = file_bytes(a["file"])
            if data is None:
                return AnchorResult(t, False, f"arquivo {a['file']} não existe na imagem", meaning)
            off = hexint(a["offset"])
            if t == "bytes":
                want = bytes.fromhex(a["hex"])
                got = data[off:off + len(want)]
                return AnchorResult(t, got == want,
                                    f"{a['file']}+0x{off:X}: esperado {want.hex().upper()}, lido {got.hex().upper() or '(nada)'}",
                                    meaning)
            length = a["length"]
            got = hashlib.sha256(data[off:off + length]).hexdigest()
            ok = got == a["sha256"].lower() and off + length <= len(data)
            return AnchorResult(t, ok, f"{a['file']}+0x{off:X} ({length} bytes): sha256 {got[:16]}…"
                                + (" confere" if ok else f" ≠ {a['sha256'][:16]}…"), meaning)
        if t == "catalog_name":
            table = self.tables.get(a["table"])
            if table is None:
                return AnchorResult(t, False, f"tabela {a['table']} não existe no perfil", meaning)
            data = file_bytes(table.file)
            if data is None:
                return AnchorResult(t, False, f"arquivo {table.file} não existe na imagem", meaning)
            got = table.read_name(data, a["id"])
            ok = got == a["name"]
            return AnchorResult(t, ok, f"{a['table']}[{a['id']}]: esperado {a['name']!r}, lido {got!r}", meaning)
        return AnchorResult(t, False, f"tipo de âncora desconhecido: {t}", meaning)


def match_profiles(image: RomImage, profiles: list[RomProfile]) -> list[ProfileMatch]:
    """Avalia todos os perfis; os que se aplicam vêm primeiro."""
    matches = [p.evaluate(image) for p in profiles]
    return sorted(matches, key=lambda m: (not m.applies, not m.integrity_ok, m.profile_id))
