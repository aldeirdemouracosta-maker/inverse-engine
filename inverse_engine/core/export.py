"""Validation e Export (portão P2): BIN nova + BPS contra a original + CUE + relatório .md/.json.

Conferências: reler a BIN nova e comparar; aplicar o BPS na original e comparar; EDC/ECC dos setores
tocados; original intocado. O relatório JSON guarda o projeto inteiro e reproduz a saída (mesmo hash).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass
from pathlib import Path
import json

from inverse_engine import __version__
from inverse_engine.core import hexview
from inverse_engine.core.paths import with_ext
from inverse_engine.core.project import Project, sha256_file
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import bps, edc_ecc
from inverse_engine.formats.disc import RAW_SECTOR


class ExportError(ValueError):
    pass


@dataclass
class ExportResult:
    files: dict[str, Path]
    report: dict


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def output_paths(project: Project) -> dict[str, Path]:
    folder = project.abs(project.output.get("folder") or "saida")
    name = project.output.get("name") or project.name
    image = project.open_image()
    if image.kind == "bin":
        main = with_ext(folder / name, ".bin")
    else:
        main = folder / f"{name} - {image.path.name}"
    out = {"imagem": main, "bps": with_ext(main, ".bps"),
           "relatorio_md": with_ext(folder / name, ".relatorio.md"),
           "relatorio_json": with_ext(folder / name, ".relatorio.json")}
    if image.kind == "bin":
        out["cue"] = with_ext(folder / name, ".cue")
    return out


def export(project: Project, overwrite: bool = False) -> ExportResult:
    """Gera a saída. Só chamar depois da revisão do usuário (P2)."""
    paths = output_paths(project)
    existing = [p for p in paths.values() if p.exists()]
    if existing and not overwrite:
        raise ExportError("já existem arquivos de saída (confirme a sobrescrita):\n" + "\n".join(map(str, existing)))
    stack = project.stack()
    original = stack.image.data
    original_hash_before = stack.image.sha256
    result = stack.build(acknowledged=set(project.acknowledged))
    new = result.data
    patch = bps.create(original, new, f"Inverse Engine {__version__} — {project.name}")

    # --- conferências antes de gravar -----------------------------------
    if bps.apply(original, patch) != new:
        raise ExportError("o BPS aplicado na original não reproduz a BIN nova")
    if stack.image.disc is not None:
        reread = RomImage.from_bytes(new)
        for lba in result.touched_sectors:
            if not edc_ecc.is_valid(new[lba * RAW_SECTOR:(lba + 1) * RAW_SECTOR]):
                raise ExportError(f"setor {lba} saiu com EDC/ECC inválido")
        if sorted(f.path for f in reread.list_files()) != sorted(f.path for f in stack.image.list_files()):
            raise ExportError("a BIN nova não tem os mesmos arquivos da original")

    folder = paths["imagem"].parent
    folder.mkdir(parents=True, exist_ok=True)
    paths["imagem"].write_bytes(new)
    paths["bps"].write_bytes(patch)
    if "cue" in paths:
        paths["cue"].write_text(f'FILE "{paths["imagem"].name}" BINARY\n  TRACK 01 MODE2/2352\n'
                                f"    INDEX 01 00:00:00\n", encoding="utf-8")

    # --- conferências depois de gravar -----------------------------------
    if paths["imagem"].read_bytes() != new:
        raise ExportError("a BIN gravada não confere com a montada (disco cheio?)")
    if sha256_file(stack.image.path) != original_hash_before:
        raise ExportError("a imagem original mudou durante a exportação")

    report = build_report(project, stack, result, paths, patch)
    paths["relatorio_json"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["relatorio_md"].write_text(report_markdown(report), encoding="utf-8")
    return ExportResult(paths, report)


def build_report(project: Project, stack, result, paths: dict[str, Path], patch: bytes) -> dict:
    profile = stack.profile
    findings = stack.findings
    anchors = None
    if profile is not None:
        m = profile.evaluate(stack.image)
        anchors = {"applies": m.applies, "integrity_ok": m.integrity_ok,
                   "anchors": [{"type": a.type, "ok": a.ok, "detail": a.detail} for a in m.anchors]}
    layers = []
    for entry in project.order:
        if entry["type"] == "patch":
            r = project.patches[entry["name"]]
            layers.append({"name": r.name, "kind": r.kind, "active": r.active, "file": r.path, "sha256": r.sha256})
        else:
            cs = project.changesets[entry["name"]]
            layers.append({"name": cs.name, "kind": "changeset", "active": cs.active, "operations": len(cs.ops)})
    ops = []
    for cs in project.changesets.values():
        for o in cs.ops:
            ops.append({"changeset": cs.name, "id": o.id, "grupo": o.group, "alvo": o.target,
                        "antes": o.before if o.kind in ("field", "text") else f"{len(o.before) // 2} bytes",
                        "depois": o.after if o.kind in ("field", "text") else f"{len(o.after) // 2} bytes",
                        "origem": o.origin, "finding": o.finding,
                        "estado": findings.status(o.finding) if (findings and o.finding) else None,
                        "experimental": o.experimental, "ativa": cs.active})
    ranges = [{"camada": r.layer, "arquivo": r.file, "offset": r.file_offset, "lba": r.lba, "ram": r.ram,
               "original": r.original.hex().upper(), "novo": r.new.hex().upper(), "campo": r.field}
              for r in hexview.write_rows(stack)]
    conflicts = [{"tipo": c.kind, "camadas": list(c.layers), "detalhe": c.detail, "alvo": c.target,
                  "reconhecido": c.id in project.acknowledged, "id": c.id} for c in result.conflicts]
    outputs = {k: {"arquivo": v.name, "sha256": sha256_file(v)} for k, v in paths.items()
               if k in ("imagem", "bps", "cue")}
    return {
        "ferramenta": {"nome": "Inverse Engine", "versao": __version__},
        "data": _dt.datetime.now().isoformat(timespec="seconds"),
        "perfil": project.profile_id, "ancoras": anchors,
        "original": {"arquivo": project.base_image, "sha256": stack.image.sha256},
        "camadas": layers, "operacoes": ops, "faixas": ranges, "conflitos": conflicts,
        "setores_tocados": result.touched_sectors, "bytes_de_sistema_ignorados": result.system_bytes_ignored,
        "experimental": result.experimental, "saida": outputs,
        "projeto": project.to_dict(), "pasta_do_projeto": str(project.folder.resolve()),
    }


def report_markdown(r: dict) -> str:
    lines = [f"# Relatório de exportação — {r['projeto']['name']}", "",
             f"- Data: {r['data']}", f"- Ferramenta: {r['ferramenta']['nome']} {r['ferramenta']['versao']}",
             f"- Perfil: {r['perfil'] or 'nenhum'}",
             f"- Original: `{r['original']['arquivo']}` — SHA-256 `{r['original']['sha256']}`", ""]
    if r["ancoras"]:
        lines += ["## Âncoras", ""] + [f"- {'OK' if a['ok'] else 'FALHOU'} — {a['type']}: {a['detail']}"
                                       for a in r["ancoras"]["anchors"]] + [""]
    lines += ["## Camadas", "", "| Ordem | Nome | Tipo | Ativa | Arquivo / operações |", "|---|---|---|---|---|"]
    for i, l in enumerate(r["camadas"], 1):
        extra = f"`{l['file']}` ({l['sha256'][:12]}…)" if "file" in l else f"{l['operations']} operação(ões)"
        lines.append(f"| {i} | {l['name']} | {l['kind']} | {'sim' if l['active'] else 'não'} | {extra} |")
    lines += ["", "## Operações", "", "| Alvo | Antes | Depois | Origem | Estado do finding |", "|---|---|---|---|---|"]
    for o in r["operacoes"]:
        est = (o["estado"] or "-") + (" (experimental)" if o["experimental"] else "")
        lines.append(f"| {o['alvo']} | {o['antes']} | {o['depois']} | {o['origem']} | {est} |")
    lines += ["", "## Faixas afetadas", "", "| Arquivo | Offset | LBA | RAM | Original | Novo | Campo |",
              "|---|---|---|---|---|---|---|"]
    for f in r["faixas"]:
        off = f"0x{f['offset']:X}" if f["offset"] is not None else "-"
        ram = f"0x{f['ram']:08X}" if f["ram"] is not None else "-"
        lines.append(f"| {f['arquivo'] or '-'} | {off} | {f['lba'] if f['lba'] is not None else '-'} | {ram} | "
                     f"{f['original']} | {f['novo']} | {f['campo'] or ''} |")
    lines += ["", "## Conflitos e avisos", ""]
    lines += [f"- {c['tipo']}{' (reconhecido)' if c['reconhecido'] else ''}: {c['detalhe']}" for c in r["conflitos"]] \
        or ["- nenhum"]
    lines += ["", "## Saída", ""] + [f"- `{v['arquivo']}` — SHA-256 `{v['sha256']}`" for v in r["saida"].values()]
    lines += ["", f"Setores tocados: {len(r['setores_tocados'])}. Bytes de sistema ignorados (EDC/ECC recalculado): "
              f"{r['bytes_de_sistema_ignorados']}.", ""]
    return "\n".join(lines)


def reproduce(report_path: str | Path) -> tuple[bool, str]:
    """Remonta a saída a partir do original + camadas do relatório e compara o SHA-256 da imagem."""
    r = json.loads(Path(report_path).read_text(encoding="utf-8"))
    project = Project.from_dict(r["projeto"], r["pasta_do_projeto"])
    data = project.stack().build(acknowledged=set(project.acknowledged)).data
    got = _sha(data)
    want = r["saida"]["imagem"]["sha256"]
    return got == want, got
