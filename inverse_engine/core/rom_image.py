"""RomImage: abstração sobre a imagem aberta (BIN de CD ou executável avulso).

Só leitura. O arquivo original nunca é alterado; toda saída é cópia (ver export).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from inverse_engine.formats import disc as cd
from inverse_engine.formats.psexe import MAGIC as PSEXE_MAGIC


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    lba: int | None
    is_dir: bool = False
    form2: bool = False


class RomImage:
    """Imagem base. `kind` é 'bin' (CD 2352) ou 'file' (executável/arquivo avulso)."""

    def __init__(self, path: Path, data: bytes, kind: str, disc: cd.Disc | None, single_name: str | None):
        self.path = path
        self.data = data
        self.kind = kind
        self.disc = disc
        self._single_name = single_name
        self.sha256 = hashlib.sha256(data).hexdigest()

    @classmethod
    def open(cls, path: str | Path) -> "RomImage":
        p = Path(path)
        if p.suffix.lower() == ".cue":
            p = resolve_cue(p)
        data = p.read_bytes()
        if cd.looks_like_bin(data):
            return cls(p, data, "bin", cd.open_disc(data), None)
        return cls(p, data, "file", None, p.name)

    @classmethod
    def from_bytes(cls, data: bytes, name: str = "image.bin") -> "RomImage":
        if cd.looks_like_bin(data):
            return cls(Path(name), data, "bin", cd.open_disc(data), None)
        return cls(Path(name), data, "file", None, name)

    # --- arquivos -------------------------------------------------------
    def list_files(self) -> list[FileEntry]:
        if self.disc is None:
            return [FileEntry(self._single_name, len(self.data), None)]
        return [FileEntry(f.path, f.size, f.lba, f.is_dir, f.form2)
                for f in sorted(self.disc.files.values(), key=lambda f: f.path)]

    def has_file(self, name: str) -> bool:
        if self.disc is None:
            return cd.normalize_path(name) == cd.normalize_path(self._single_name)
        return cd.normalize_path(name) in self.disc.files

    def read_file(self, name: str) -> bytes:
        if self.disc is None:
            if not self.has_file(name):
                raise cd.DiscError(f"a imagem aberta é o arquivo {self._single_name}, não {name}")
            return self.data
        return self.disc.read_file(name)

    def find_executable(self) -> str | None:
        """Primeiro arquivo com cabeçalho PS-X EXE (pelo conteúdo, não pela extensão)."""
        for f in self.list_files():
            if f.is_dir or f.form2 or f.size < 0x800:
                continue
            if self.read_file(f.path)[:8] == PSEXE_MAGIC:
                return f.path
        return None

    # --- endereçamento --------------------------------------------------
    def file_offset_to_lba(self, name: str, offset: int) -> tuple[int, int] | None:
        """(LBA, offset no setor) de um byte de arquivo. None para imagem avulsa."""
        if self.disc is None:
            return None
        return self.disc.file_offset_to_lba(name, offset)

    def file_offset_to_bin(self, name: str, offset: int) -> int:
        if self.disc is None:
            return offset
        lba, pos = self.disc.file_offset_to_lba(name, offset)
        return self.disc.bin_offset(lba, pos)

    def bin_offset_to_user(self, bin_offset: int) -> tuple[int, int] | None:
        """BIN → (LBA, offset nos dados de usuário); None se for byte de sistema."""
        if self.disc is None:
            return (0, bin_offset)
        lba, pos = self.disc.locate_bin_offset(bin_offset)
        return None if pos is None else (lba, pos)

    def non_data_sectors(self) -> list[tuple[int, str]]:
        """Setores fora de Mode 1 / Mode 2 Form 1 (Form 2, áudio etc.) para aviso."""
        if self.disc is None:
            return []
        out = []
        for lba in range(self.disc.sector_count):
            k = self.disc.kind(lba)
            if k not in ("mode1", "mode2_form1"):
                out.append((lba, k))
        return out


def resolve_cue(cue: Path) -> Path:
    """Primeira linha FILE "x.bin" BINARY do .cue, relativa à pasta do .cue."""
    for line in cue.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.upper().startswith("FILE"):
            first, last = s.find('"'), s.rfind('"')
            name = s[first + 1:last] if last > first else s.split()[1]
            return cue.parent / name
    raise ValueError(f"{cue.name}: nenhuma linha FILE encontrada")
