"""Export (BIN + BPS + CUE + relatório), reprodução pelo relatório e visualização em hexa."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core import hexview
from inverse_engine.core.export import export, reproduce, ExportError, output_paths
from inverse_engine.core.patch_stack import PatchError, PatchStack, Layer, FieldEdit
from inverse_engine.core.project import Project
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import bps, ppf, tim
from tests.fixture_cd import make_slus
from tests.test_patch_stack import (PROFILE, FINDINGS, ATTACK_182, SAME_SECTOR_OUTSIDE_TABLE, cd, slus_with,
                                    recolor, files, TIM)


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bin = root / "Vandal Hearts II (USA).bin"
        self.bin.write_bytes(cd())
        self.orig_hash = hashlib.sha256(self.bin.read_bytes()).hexdigest()
        self.ppf = root / "tt.ppf"
        self.ppf.write_bytes(ppf.build_ppf3(cd(), cd(slus_with([(SAME_SECTOR_OUTSIDE_TABLE, b"\xEE")]))))
        p = Project.create(root / "proj", "Rebalance v1.2", self.bin)
        p.add_patch(self.ppf, "Take Turns")
        p.add_changeset("Rebalance")
        cs = p.bind("Rebalance")
        with cs.group("especiais"):
            cs.set_field("weapons", 182, "attack", 45)
            cs.set_field("weapons", 183, "descriptor_code", 7)
        cs.set_graphic(recolor(64))
        p.save()
        self.p = p

    def tearDown(self):
        self.tmp.cleanup()

    def test_gera_bin_bps_cue_e_relatorio(self):
        res = export(self.p)
        f = res.files
        self.assertEqual(f["imagem"].name, "Rebalance v1.2.bin")
        self.assertEqual(f["bps"].name, "Rebalance v1.2.bin.bps")
        self.assertEqual(f["cue"].name, "Rebalance v1.2.cue")
        for k in ("imagem", "bps", "cue", "relatorio_md", "relatorio_json"):
            self.assertTrue(f[k].exists(), k)
        self.assertIn('FILE "Rebalance v1.2.bin" BINARY', f["cue"].read_text())
        new = f["imagem"].read_bytes()
        self.assertEqual(bps.apply(self.bin.read_bytes(), f["bps"].read_bytes()), new)
        self.assertEqual(hashlib.sha256(self.bin.read_bytes()).hexdigest(), self.orig_hash)  # original intocado
        img = RomImage.open(f["cue"])
        slus = img.read_file("SLUS_009.40")
        self.assertEqual(struct.unpack_from("<H", slus, ATTACK_182)[0], 45)
        self.assertEqual(slus[SAME_SECTOR_OUTSIDE_TABLE], 0xEE)

    def test_relatorio_tem_tudo(self):
        r = export(self.p).report
        self.assertEqual(r["perfil"], "SLUS-00940-USA")
        self.assertEqual(r["original"]["sha256"], self.orig_hash)
        self.assertEqual(len(r["ancoras"]["anchors"]), 3)
        self.assertEqual([l["kind"] for l in r["camadas"]], ["ppf", "changeset"])
        self.assertEqual(r["camadas"][0]["sha256"], hashlib.sha256(self.ppf.read_bytes()).hexdigest())
        op = next(o for o in r["operacoes"] if o["alvo"] == "weapons[182].attack")
        self.assertEqual((op["antes"], op["depois"], op["origem"], op["estado"]), (30, 45, "manual", "PROVAVEL"))
        faixa = next(x for x in r["faixas"] if x["campo"] == "weapons[182].attack")
        self.assertEqual(faixa["offset"], ATTACK_182)
        self.assertIsNotNone(faixa["lba"])
        self.assertEqual(faixa["ram"], 0x80010000 + ATTACK_182 - 0x800)
        self.assertTrue(r["setores_tocados"])
        self.assertGreater(r["bytes_de_sistema_ignorados"], 0)
        self.assertEqual(set(r["saida"]), {"imagem", "bps", "cue"})
        md = export(self.p, overwrite=True).files["relatorio_md"].read_text(encoding="utf-8")
        for sec in ("## Âncoras", "## Camadas", "## Operações", "## Faixas afetadas", "## Conflitos", "## Saída"):
            self.assertIn(sec, md)
        self.assertIn("weapons[182].attack", md)

    def test_relatorio_reproduz_a_saida(self):
        res = export(self.p)
        ok, got = reproduce(res.files["relatorio_json"])
        self.assertTrue(ok)
        self.assertEqual(got, hashlib.sha256(res.files["imagem"].read_bytes()).hexdigest())

    def test_sobrescrita_exige_confirmacao(self):
        export(self.p)
        with self.assertRaisesRegex(ExportError, "sobrescrita"):
            export(self.p)
        export(self.p, overwrite=True)

    def test_conflito_precisa_ser_reconhecido(self):
        cs = self.p.bind("Rebalance")
        cs.set_field("weapons", 182, "attack", 45)
        bad = Path(self.tmp.name) / "conflito.ppf"
        bad.write_bytes(ppf.build_ppf3(cd(), cd(slus_with([(ATTACK_182, struct.pack("<H", 99))]))))
        self.p.add_patch(bad, "Outro")
        with self.assertRaisesRegex(PatchError, "P4"):
            export(self.p)
        self.assertFalse(output_paths(self.p)["imagem"].exists())
        self.p.acknowledged = [c.id for c in self.p.stack().conflicts() if c.needs_ack]
        r = export(self.p).report
        self.assertTrue(all(c["reconhecido"] for c in r["conflitos"] if c["tipo"] == "CONFLITO"))

    def test_pasta_e_nome_de_saida_configuraveis(self):
        self.p.output = {"folder": "../builds", "name": "VH2 Rebalance 2026.v3"}
        f = export(self.p).files
        self.assertEqual(f["imagem"].parent.name, "builds")
        self.assertEqual(f["imagem"].name, "VH2 Rebalance 2026.v3.bin")

    def test_executavel_avulso_sem_cue(self):
        exe = Path(self.tmp.name) / "SLUS_009.40"
        exe.write_bytes(files()["SLUS_009.40"])
        p = Project.create(Path(self.tmp.name) / "p2", "Exe", exe)
        p.add_changeset("R")
        p.bind("R").set_field("weapons", 182, "attack", 50)
        f = export(p).files
        self.assertNotIn("cue", f)
        self.assertEqual(f["imagem"].name, "Exe - SLUS_009.40")
        self.assertEqual(struct.unpack_from("<H", f["imagem"].read_bytes(), ATTACK_182)[0], 50)


class HexViewTest(unittest.TestCase):
    def test_linhas_com_offset_lba_ram_e_campo(self):
        st = PatchStack(RomImage.from_bytes(cd()), PROFILE, FINDINGS)
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 182, "attack", 0x1234)]))
        rows = hexview.write_rows(st)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r.file, r.file_offset, r.field), ("SLUS_009.40", ATTACK_182, "weapons[182].attack"))
        self.assertEqual((r.original, r.new), (b"\x1e\x00", b"\x34\x12"))
        self.assertEqual(r.ram, 0x80010000 + ATTACK_182 - 0x800)
        text = hexview.format_table([r.cells()], hexview.HEADERS)
        self.assertIn("1E 00", text)
        self.assertIn("34 12", text)
        self.assertIn("OFFSET", text.splitlines()[0])

    def test_registro_com_fronteiras(self):
        data = make_slus(values={(182, 0xA): struct.pack("<H", 30)})
        rows = hexview.record_view(PROFILE.table("weapons"), data, 182, FINDINGS)
        self.assertEqual(sum(r["tamanho"] for r in rows), 22)
        names = [r["campo"] for r in rows]
        self.assertEqual(names[:8], ["byte_0x00", "byte_0x01", "byte_0x02", "byte_0x03", "byte_0x04",
                                     "byte_0x05", "byte_0x06", "range"])
        atk = next(r for r in rows if r["campo"] == "attack")
        self.assertEqual((atk["offset"], atk["hex"], atk["valor"], atk["estado"]), (0xA, "1E 00", 30, "PROVAVEL"))

    def test_tim_blocos_e_so_faixas_alteradas(self):
        g = recolor(64)
        info = tim.parse(g.original, 0)
        names = [n for n, _, _ in hexview.tim_sections(info)]
        self.assertEqual(names, ["cabeçalho", "paleta: cabeçalho", "paleta: cores", "pixels: cabeçalho", "pixels"])
        changes = hexview.tim_changes(info, g.original, g.new)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], "paleta: cores")


if __name__ == "__main__":
    unittest.main()
