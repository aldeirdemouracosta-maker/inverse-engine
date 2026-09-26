"""Modo terminal do Inverse Engine (diagnóstico).

    python -m inverse_engine.cli abrir  IMAGEM          # arquivos do CD + âncoras de todos os perfis
    python -m inverse_engine.cli tabela IMAGEM weapons   # registros da tabela (perfil que se aplica)
    python -m inverse_engine.cli findings                # resumo do banco de descobertas
    python -m inverse_engine.cli tims   IMAGEM           # TIMs encontrados em todos os arquivos
    python -m inverse_engine.cli ppf    PATCH.ppf [--imagem IMAGEM]   # registros e bloco de conferência
    python -m inverse_engine.cli projeto novo    PASTA NOME IMAGEM         # cria <NOME>.vh2proj.json
    python -m inverse_engine.cli projeto patch   PROJ ARQUIVO.ppf          # acrescenta camada PPF/BPS
    python -m inverse_engine.cli projeto campo   PROJ weapons 182 attack 45 [--grupo ROTULO]
    python -m inverse_engine.cli projeto desfazer|refazer PROJ
    python -m inverse_engine.cli projeto mostrar PROJ                      # camadas, histórico, conflitos
    python -m inverse_engine.cli projeto hexa    PROJ                      # escritas: offset | LBA | RAM | …
    python -m inverse_engine.cli projeto reconhecer PROJ                   # reconhece os conflitos atuais (P4)
    python -m inverse_engine.cli projeto exportar PROJ [--sobrescrever]    # BIN + BPS + CUE + relatório (P2)
    python -m inverse_engine.cli registro IMAGEM weapons 182               # registro com fronteiras dos campos
    python -m inverse_engine.cli reproduzir RELATORIO.relatorio.json       # remonta e compara o SHA-256
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from inverse_engine.core.profile import RomProfile, match_profiles
from inverse_engine.core.rom_image import RomImage
from inverse_engine.research.findings import FindingsDB

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles"
FINDINGS = ROOT / "research" / "findings"


def cmd_abrir(args) -> int:
    image = RomImage.open(args.imagem)
    print(f"Imagem: {image.path}  ({image.kind}, {len(image.data)} bytes)")
    print(f"SHA-256: {image.sha256}")
    if image.disc is not None:
        print(f"Volume: {image.disc.volume_id}  setores: {image.disc.sector_count}")
        for f in image.list_files():
            tag = "pasta" if f.is_dir else ("Form 2 (XA, só listado)" if f.form2 else f"{f.size} bytes")
            print(f"  LBA {f.lba:>6}  {f.path:<40} {tag}")
        odd = [x for x in image.non_data_sectors() if x[1] != "mode2_form2"]
        if odd:
            print(f"Aviso: {len(odd)} setores fora de Mode 1/Mode 2 tratados como bytes crus")
    exe = image.find_executable()
    print(f"Executável PS-X EXE: {exe or 'não encontrado'}")
    profiles = RomProfile.load_all(args.perfis)
    for m in match_profiles(image, profiles):
        print(f"\nPerfil {m.profile_id}: {m.summary()}")
        if m.known_image:
            print(f"  imagem conhecida: {m.known_image}")
        for a in m.anchors:
            print(f"  [{'OK ' if a.ok else 'FALHOU'}] {a.type:<13} {a.detail}" + (f"  — {a.meaning}" if a.meaning else ""))
    return 0


def cmd_tabela(args) -> int:
    image = RomImage.open(args.imagem)
    profiles = RomProfile.load_all(args.perfis)
    match = next((m for m in match_profiles(image, profiles) if m.applies), None)
    if match is None:
        print("Nenhum perfil se aplica a esta imagem: tabelas indisponíveis.", file=sys.stderr)
        return 2
    profile = next(p for p in profiles if p.profile_id == match.profile_id)
    if not match.integrity_ok:
        print("AVISO: a âncora de integridade falhou; a tabela foi alterada por algum patch base.")
    table = profile.table(args.tabela)
    findings = _findings_for(profile.profile_id)
    data = image.read_file(table.file)
    ids = [args.id] if args.id is not None else range(table.count)
    cols = list(table.fields)
    print("id   " + "nome".ljust(18) + "".join(c[:12].rjust(13) for c in cols))
    print("     " + "".ljust(18) + "".join(findings.status(table.fields[c].finding)[:12].rjust(13) for c in cols))
    for i in ids:
        name = table.read_name(data, i) or ""
        vals = "".join(str(table.read_field(data, i, c)).rjust(13) for c in cols)
        print(f"{i:<5}{name[:17]:<18}{vals}")
    return 0


def cmd_findings(args) -> int:
    for p in sorted(Path(args.pasta).glob("*.json")):
        db = FindingsDB.load(p)
        print(f"{p.name}: " + ", ".join(f"{k} {v}" for k, v in db.by_status().items()))
        for f in db.findings.values():
            print(f"  {f['id']:<7} {f['status']:<13} {f['subject']}")
    return 0


def cmd_tims(args) -> int:
    from inverse_engine.formats import tim
    image = RomImage.open(args.imagem)
    found = tim.scan_image(image)
    for path, info in found:
        print(f"{path:<32} 0x{info.offset:08X} {info.size:>7} bytes  {info.describe()}")
    print(f"{len(found)} TIM(s)")
    return 0


def cmd_ppf(args) -> int:
    from inverse_engine.formats import ppf
    p = ppf.parse(Path(args.patch).read_bytes())
    print(f"PPF{p.version}.0  {p.description!r}  registros: {len(p.records)}  "
          f"bytes: {sum(len(d) for _, d in p.records)}")
    if p.file_id:
        print(f"FILE_ID.DIZ: {p.file_id}")
    if args.imagem:
        image = RomImage.open(args.imagem)
        why = p.check_block(image.data)
        print("Bloco de conferência: " + ("confere" if why is None else why))
        if image.disc is not None:
            system = sum(1 for off, d in p.records for k in range(len(d))
                         if image.bin_offset_to_user(off + k) is None)
            print(f"Bytes em sync/cabeçalho/EDC/ECC (ignorados, recalculados no fim): {system}")
    return 0


def cmd_projeto(args) -> int:
    from inverse_engine.core.project import Project
    if args.acao == "novo":
        pasta, nome, imagem = args.args
        p = Project.create(pasta, nome, imagem)
        p.add_changeset("Alterações")
        print(f"Projeto criado: {p.save()}  (perfil: {p.profile_id or 'nenhum'})")
        return 0
    p = Project.load(args.args[0])
    rest = args.args[1:]
    if args.acao == "patch":
        ref = p.add_patch(rest[0])
        print(f"Camada {ref.kind} '{ref.name}' acrescentada ({ref.path})")
    elif args.acao == "campo":
        table, index, field_name, value = rest
        cs = p.bind(args.changeset or next(iter(p.changesets)))
        with cs.group(args.grupo or f"{table}[{index}].{field_name}"):
            op = cs.set_field(table, int(index, 0), field_name, int(value, 0))
        print(f"{op.target}: {op.before} → {op.after}")
    elif args.acao in ("desfazer", "refazer"):
        cs = p.changesets[args.changeset or next(iter(p.changesets))]
        ops = cs.undo() if args.acao == "desfazer" else cs.redo()
        print(f"{args.acao}: {len(ops)} operação(ões)" + (f" do grupo '{ops[0].group_label}'" if ops else ""))
    elif args.acao == "hexa":
        from inverse_engine.core import hexview
        rows = hexview.write_rows(p.stack())
        print(hexview.format_table([r.cells() for r in rows], hexview.HEADERS))
        return 0
    elif args.acao == "reconhecer":
        pend = [c for c in p.stack().conflicts() if c.needs_ack and c.id not in p.acknowledged]
        for c in pend:
            print(f"reconhecido: {c.detail}")
            p.acknowledged.append(c.id)
        if not pend:
            print("nenhum conflito pendente")
    elif args.acao == "exportar":
        from inverse_engine.core.export import export
        res = export(p, overwrite=args.sobrescrever)
        for k, v in res.files.items():
            print(f"{k:<15} {v}")
        return 0
    elif args.acao == "mostrar":
        print(f"Projeto {p.name}  perfil {p.profile_id}  imagem {p.base_image}")
        for o in p.order:
            ref = p.patches.get(o["name"]) or p.changesets[o["name"]]
            print(f"  [{'x' if ref.active else ' '}] {o['type']:<9} {o['name']}")
        for cs in p.changesets.values():
            for h in cs.history():
                print(f"    #{h['id']:<4} grupo {h['grupo']:<3} {h['alvo']:<28} {h['antes']} → {h['depois']}  ({h['origem']})")
        for c in p.stack().conflicts():
            print(f"  {c.kind}: {c.detail}")
        return 0
    p.save()
    return 0


def cmd_registro(args) -> int:
    from inverse_engine.core import hexview
    image = RomImage.open(args.imagem)
    profiles = RomProfile.load_all(args.perfis)
    match = next((m for m in match_profiles(image, profiles) if m.applies), None)
    if match is None:
        print("Nenhum perfil se aplica a esta imagem.", file=sys.stderr)
        return 2
    profile = next(p for p in profiles if p.profile_id == match.profile_id)
    table = profile.table(args.tabela)
    data = image.read_file(table.file)
    base = table.record_offset(args.id)
    print(f"{args.tabela}[{args.id}] {table.read_name(data, args.id) or ''}  arquivo {table.file} 0x{base:X}")
    rows = hexview.record_view(table, data, args.id, _findings_for(profile.profile_id))
    print(hexview.format_table([[f"+0x{r['offset']:02X}", r["campo"], r["hex"], str(r["valor"]), r["estado"]]
                                for r in rows], ["OFF", "CAMPO", "HEX", "VALOR", "ESTADO"]))
    return 0


def cmd_reproduzir(args) -> int:
    from inverse_engine.core.export import reproduce
    ok, got = reproduce(args.relatorio)
    print(("REPRODUZ: mesmo SHA-256 " if ok else "NÃO REPRODUZ: SHA-256 diferente ") + got)
    return 0 if ok else 1


def _findings_for(profile_id: str) -> FindingsDB:
    p = FINDINGS / f"{profile_id}.json"
    return FindingsDB.load(p) if p.exists() else FindingsDB({"findings": []})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inverse_engine", description="Inverse Engine — modo terminal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("abrir", help="lista arquivos e avalia as âncoras dos perfis")
    a.add_argument("imagem")
    a.add_argument("--perfis", default=str(PROFILES))
    a.set_defaults(func=cmd_abrir)
    t = sub.add_parser("tabela", help="mostra registros de uma tabela do perfil")
    t.add_argument("imagem")
    t.add_argument("tabela")
    t.add_argument("--id", type=lambda s: int(s, 0))
    t.add_argument("--perfis", default=str(PROFILES))
    t.set_defaults(func=cmd_tabela)
    f = sub.add_parser("findings", help="resumo do banco de descobertas")
    f.add_argument("--pasta", default=str(FINDINGS))
    f.set_defaults(func=cmd_findings)
    m = sub.add_parser("tims", help="procura TIMs em todos os arquivos da imagem")
    m.add_argument("imagem")
    m.set_defaults(func=cmd_tims)
    pp = sub.add_parser("ppf", help="mostra um PPF e confere o bloco contra a imagem")
    pp.add_argument("patch")
    pp.add_argument("--imagem")
    pp.set_defaults(func=cmd_ppf)
    pj = sub.add_parser("projeto", help="projeto .vh2proj.json: novo, patch, campo, desfazer, refazer, mostrar")
    pj.add_argument("acao", choices=["novo", "patch", "campo", "desfazer", "refazer", "mostrar", "hexa",
                                     "reconhecer", "exportar"])
    pj.add_argument("--sobrescrever", action="store_true")
    pj.add_argument("args", nargs="+")
    pj.add_argument("--changeset")
    pj.add_argument("--grupo")
    pj.set_defaults(func=cmd_projeto)
    rg = sub.add_parser("registro", help="registro de tabela com as fronteiras dos campos")
    rg.add_argument("imagem")
    rg.add_argument("tabela")
    rg.add_argument("id", type=lambda s: int(s, 0))
    rg.add_argument("--perfis", default=str(PROFILES))
    rg.set_defaults(func=cmd_registro)
    rp = sub.add_parser("reproduzir", help="remonta a saída a partir do relatório e compara o hash")
    rp.add_argument("relatorio")
    rp.set_defaults(func=cmd_reproduzir)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
