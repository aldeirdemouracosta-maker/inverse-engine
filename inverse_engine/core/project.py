"""Arquivo de projeto `<nome>.vh2proj.json`: imagem base, perfil, camadas em ordem, changesets e saída.

Caminhos são guardados relativos à pasta do projeto quando possível (pode ser partição compartilhada
Windows/Linux). Hashes da imagem base e dos patches são conferidos ao reabrir (portão P4 se mudarem).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from inverse_engine.core.changeset import ChangeSet
from inverse_engine.core.patch_stack import Layer, PatchStack, PatchError
from inverse_engine.core.profile import RomProfile
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import bps, ppf
from inverse_engine.research.findings import FindingsDB

EXT = ".vh2proj.json"
FORMAT = 1
ROOT = Path(__file__).resolve().parent.parent.parent


class ProjectError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class PatchLayerRef:
    """Camada de patch externo (PPF ou BPS) guardada por caminho + hash."""
    name: str
    kind: str                 # ppf | bps_import
    path: str                 # relativo à pasta do projeto, com '/'
    sha256: str
    active: bool = True
    block_acknowledged: bool = False


@dataclass
class Project:
    name: str
    folder: Path
    base_image: str                               # relativo à pasta do projeto
    base_sha256: str
    profile_id: str | None = None
    research_mode: bool = False
    order: list[dict] = field(default_factory=list)          # [{"type": "patch"|"changeset", "name": ...}]
    patches: dict[str, PatchLayerRef] = field(default_factory=dict)
    changesets: dict[str, ChangeSet] = field(default_factory=dict)
    acknowledged: list[str] = field(default_factory=list)    # conflitos reconhecidos (P4)
    output: dict = field(default_factory=lambda: {"folder": "saida", "name": ""})
    ui: dict = field(default_factory=dict)                   # layout dos painéis etc. (interface)
    profiles_dir: Path = field(default=ROOT / "profiles", compare=False)
    findings_dir: Path = field(default=ROOT / "research" / "findings", compare=False)

    # --- criação -------------------------------------------------------------
    @classmethod
    def create(cls, folder: str | Path, name: str, image_path: str | Path,
               profile_id: str | None = None, **dirs) -> "Project":
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        image_path = Path(image_path)
        p = cls(name, folder, "", "", profile_id, **dirs)
        p.base_image = p.rel(image_path)
        image = p.open_image()
        p.base_sha256 = image.sha256  # hash da BIN (mesmo quando a base é um .cue)
        if profile_id is None:
            from inverse_engine.core.profile import match_profiles
            matches = [m for m in match_profiles(image, RomProfile.load_all(p.profiles_dir)) if m.applies]
            p.profile_id = matches[0].profile_id if len(matches) == 1 else None
        return p

    # --- caminhos -------------------------------------------------------------
    def rel(self, path: str | Path) -> str:
        path = Path(path).resolve()
        try:
            return PurePosixPath(Path(os.path.relpath(path, self.folder.resolve()))).as_posix()
        except ValueError:  # outra unidade no Windows
            return path.as_posix()

    def abs(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.folder / p).resolve()

    @property
    def path(self) -> Path:
        return self.folder / (self.name + EXT)

    # --- camadas ----------------------------------------------------------------
    def add_patch(self, path: str | Path, name: str | None = None) -> PatchLayerRef:
        path = Path(path)
        data = path.read_bytes()
        kind = "ppf" if data[:3] == b"PPF" else "bps_import" if data[:4] == b"BPS1" else None
        if kind is None:
            raise ProjectError(f"{path.name}: não é PPF nem BPS")
        name = name or path.name
        if name in self.patches or name in self.changesets:
            raise ProjectError(f"já existe uma camada chamada {name!r}")
        ref = PatchLayerRef(name, kind, self.rel(path), hashlib.sha256(data).hexdigest())
        self.patches[name] = ref
        # Patch base entra antes dos changesets: Original → [PPF] → [edições]; a ordem pode ser mudada com move().
        first_cs = next((k for k, o in enumerate(self.order) if o["type"] == "changeset"), len(self.order))
        self.order.insert(first_cs, {"type": "patch", "name": name})
        return ref

    def add_changeset(self, name: str = "Alterações") -> ChangeSet:
        if name in self.patches or name in self.changesets:
            raise ProjectError(f"já existe uma camada chamada {name!r}")
        cs = ChangeSet(name)
        self.changesets[name] = cs
        self.order.append({"type": "changeset", "name": name})
        return cs

    def move(self, name: str, new_index: int) -> None:
        i = next(k for k, o in enumerate(self.order) if o["name"] == name)
        self.order.insert(new_index, self.order.pop(i))

    def set_active(self, name: str, active: bool) -> None:
        if name in self.patches:
            self.patches[name].active = active
        else:
            self.changesets[name].active = active

    # --- abrir e montar ------------------------------------------------------------
    def open_image(self) -> RomImage:
        path = self.abs(self.base_image)
        if not path.exists():
            raise ProjectError(f"imagem base não encontrada: {path}")
        return RomImage.open(path)

    def profile(self) -> RomProfile | None:
        if not self.profile_id:
            return None
        for p in RomProfile.load_all(self.profiles_dir):
            if p.profile_id == self.profile_id:
                return p
        raise ProjectError(f"perfil {self.profile_id} não encontrado em {self.profiles_dir}")

    def findings(self) -> FindingsDB | None:
        if not self.profile_id:
            return None
        f = self.findings_dir / f"{self.profile_id}.json"
        return FindingsDB.load(f) if f.exists() else None

    def check_hashes(self, image: RomImage | None = None) -> list[str]:
        """Diferenças de hash (imagem base e patches). Lista vazia = tudo confere."""
        problems = []
        image = image or self.open_image()
        if image.sha256 != self.base_sha256:
            problems.append(f"imagem base mudou: {self.base_image}")
        for ref in self.patches.values():
            p = self.abs(ref.path)
            if not p.exists():
                problems.append(f"patch não encontrado: {ref.path}")
            elif sha256_file(p) != ref.sha256:
                problems.append(f"patch mudou desde que entrou no projeto: {ref.path}")
        return problems

    def stack(self, accept_changed_files: bool = False) -> PatchStack:
        image = self.open_image()
        problems = self.check_hashes(image)
        if problems and not accept_changed_files:
            raise ProjectError("arquivos do projeto mudaram (portão P4):\n" + "\n".join(problems))
        profile, findings = self.profile(), self.findings()
        st = PatchStack(image, profile, findings, self.research_mode)
        for entry in self.order:
            if entry["type"] == "patch":
                ref = self.patches[entry["name"]]
                data = self.abs(ref.path).read_bytes()
                if ref.kind == "ppf":
                    st.add(Layer(ref.name, "ppf", ref.active, ppf=ppf.parse(data),
                                 ppf_block_acknowledged=ref.block_acknowledged))
                else:
                    st.add(Layer(ref.name, "bps_import", ref.active, bps_target=bps.apply(image.data, data)))
            else:
                for layer in self.changesets[entry["name"]].to_layers():
                    st.add(layer)
        return st

    def bind(self, changeset: str, image: RomImage | None = None) -> ChangeSet:
        """ChangeSet pronto para receber operações (validadas contra imagem, perfil e findings)."""
        image = image or self.open_image()
        return self.changesets[changeset].bind(image, self.profile(), self.findings(), self.research_mode)

    # --- persistência ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT, "tool": "inverse_engine", "name": self.name,
            "base_image": {"path": self.base_image, "sha256": self.base_sha256},
            "profile_id": self.profile_id, "research_mode": self.research_mode,
            "order": self.order,
            "patches": [vars(r).copy() for r in self.patches.values()],
            "changesets": [c.to_dict() for c in self.changesets.values()],
            "acknowledged": self.acknowledged, "output": self.output, "ui": self.ui,
        }

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else self.path
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)  # troca atômica: nunca deixa o projeto pela metade
        return path

    @classmethod
    def load(cls, path: str | Path, **dirs) -> "Project":
        path = Path(path)
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), path.parent, **dirs)

    @classmethod
    def from_dict(cls, d: dict, folder: str | Path, **dirs) -> "Project":
        if d.get("format") != FORMAT:
            raise ProjectError(f"formato de projeto não suportado: {d.get('format')}")
        p = cls(d["name"], Path(folder), d["base_image"]["path"], d["base_image"]["sha256"], d.get("profile_id"),
                d.get("research_mode", False), [dict(o) for o in d.get("order", [])], **dirs)
        p.patches = {r["name"]: PatchLayerRef(**r) for r in d.get("patches", [])}
        p.changesets = {c["name"]: ChangeSet.from_dict(c) for c in d.get("changesets", [])}
        p.acknowledged = d.get("acknowledged", [])
        p.output = d.get("output", p.output)
        p.ui = d.get("ui", {})
        names = {o["name"] for o in p.order}
        if names != set(p.patches) | set(p.changesets):
            raise ProjectError("ordem das camadas não confere com as camadas do projeto")
        return p
