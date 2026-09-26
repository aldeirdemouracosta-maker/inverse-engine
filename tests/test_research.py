"""Modo Pesquisa: perfilador, gabarito CSV, hipóteses, BIN de teste e findings de gráficos."""
import copy
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core.project import Project
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import tim
from inverse_engine.research import gabarito, profiler, testbin
from inverse_engine.research.findings import FindingsDB, FindingError
from tests.fixture_cd import CdBuilder, make_slus
from tests.test_patch_stack import PROFILE, FINDINGS, TIM, files, ATTACK_182

ROOT = Path(__file__).resolve().parent.parent
W = PROFILE.table("weapons")


def planted():
    """SLUS com colunas plantadas: +0x05 u8 múltiplos de 5 crescentes no grupo; +0x08 u16 = 100+id;
    preço (+0x0C) = 10×id; ataque (+0x0A) = id % 50."""
    values = {}
    for g in W.groups:
        for k, i in enumerate(range(g["start"], g["end"] + 1)):
            values[(i, 0x05)] = bytes([5 * (k + 1)])
    for i in range(1, 215):
        values[(i, 0x08)] = struct.pack("<H", 100 + i)
        values[(i, 0x0C)] = struct.pack("<H", 10 * i)
        values[(i, 0x0A)] = struct.pack("<H", i % 50)
    return make_slus(names={182: "Rebelrod", 7: "Espada Sete"}, values=values)


class ProfilerTest(unittest.TestCase):
    def test_acha_coluna_plantada(self):
        stats = {(s.offset, s.type): s for s in profiler.profile(W, planted())}
        s = stats[(0x05, "u8")]
        self.assertIn("múltiplos de 5", s.notes())
        self.assertIn("cresce dentro dos grupos", s.notes())
        self.assertEqual(s.monotonic, 1.0)
        self.assertEqual(stats[(0x0C, "u16le")].field, "price")
        self.assertIn("múltiplos de 10", stats[(0x0C, "u16le")].notes())
        self.assertIn("constante", stats[(0x00, "u8")].notes())
        self.assertEqual(len([s for s in stats.values() if s.type == "u8"]), 22)
        self.assertEqual(len([s for s in stats.values() if s.type == "u16le"]), 21)


class GabaritoTest(unittest.TestCase):
    def setUp(self):
        self.data = planted()
        self.db = copy.deepcopy(FINDINGS)

    def csv(self, attr, pairs, fonte="guia do usuário"):
        return "id,atributo,valor,fonte\n" + "".join(f"{i},{attr},{v},{fonte}\n" for i, v in pairs)

    def test_proposta_nova_vira_provavel_com_statistical_match(self):
        rows = gabarito.load(self.csv("poder", [(i, 100 + i) for i in range(10, 22)]), W, self.data)
        props = gabarito.match(W, self.data, rows)
        self.assertEqual([(p.offset, p.type) for p in props], [(0x08, "u16le")])
        p = props[0]
        self.assertEqual((p.matched, p.total, p.existing), (12, 12, None))
        f = gabarito.apply(self.db, W, p)
        self.assertEqual((f["id"], f["status"], f["record_offset"]), ("F-0100", "PROVAVEL", "0x8"))
        self.assertEqual(f["evidence"][0]["kind"], "statistical_match")
        again = gabarito.apply(self.db, W, p)
        self.assertEqual(again["id"], "F-0100")  # não duplica: só acrescenta evidência
        self.assertEqual(len(again["evidence"]), 2)

    def test_promove_hipotese_existente_ate_provavel_nunca_confirmado(self):
        rows = gabarito.load(self.csv("preço", [(i, 10 * i) for i in range(30, 42)]), W, self.data)
        p = next(p for p in gabarito.match(W, self.data, rows) if p.offset == 0x0C)
        self.assertEqual(p.existing, "F-0012")
        gabarito.apply(self.db, W, p)
        self.assertEqual(self.db.status("F-0012"), "PROVAVEL")
        self.assertEqual(self.db.get("F-0012")["history"][-1]["to"], "PROVAVEL")

    def test_tolerancia_e_limite(self):
        pairs = [(i, 100 + i) for i in range(10, 22)]
        pairs[0] = (10, 999)  # 11/12 = 91,7%
        rows = gabarito.load(self.csv("poder", pairs), W, self.data)
        self.assertEqual(len(gabarito.match(W, self.data, rows, threshold=0.9)), 1)
        self.assertEqual(gabarito.match(W, self.data, rows, threshold=0.95), [])

    def test_valor_unico_so_vira_hipotese(self):
        rows = gabarito.load(self.csv("duas_maos", [(i, 0) for i in range(10, 16)]), W, self.data)
        props = [p for p in gabarito.match(W, self.data, rows) if p.existing is None]
        self.assertTrue(props)
        self.assertEqual(props[0].distinct, 1)
        f = gabarito.apply(self.db, W, props[0])
        self.assertEqual(f["status"], "HIPOTESE")  # coluna constante bateria com qualquer coisa

    def test_nome_no_lugar_do_id_e_hex(self):
        rows = gabarito.load("id,atributo,valor,fonte\nRebelrod,ataque,32,x\n0x07,ataque,7,x\n", W, self.data)
        self.assertEqual([(r.index, r.value) for r in rows], [(182, 32), (7, 7)])
        with self.assertRaises(ValueError):
            gabarito.load("id,atributo,valor,fonte\nNaoExiste,a,1,x\n", W, self.data)

    def test_poucos_registros_nao_propoem(self):
        rows = gabarito.load(self.csv("poder", [(10, 110), (11, 111)]), W, self.data)
        self.assertEqual(gabarito.match(W, self.data, rows), [])


class FindingCreationTest(unittest.TestCase):
    def test_marcar_bytes_como_hipotese(self):
        db = copy.deepcopy(FINDINGS)
        f = db.add_finding("F", "weapons.byte_0x05", "talvez nível mínimo", file="SLUS_009.40",
                           record_offset="0x5", size=1, type="u8")
        self.assertEqual((f["id"], f["status"]), ("F-0100", "HIPOTESE"))
        self.assertEqual(db.next_id("F"), "F-0101")
        with self.assertRaises(FindingError):
            db.add_finding("F", "x", "sem prova", status="PROVAVEL")
        with self.assertRaises(FindingError):
            db.add_finding("F", "x", "y", evidence=[{"kind": "achismo", "detail": "?"}])


class TestBinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bin = root / "jogo.bin"
        self.bin.write_bytes(CdBuilder().build(files()))
        fdir = root / "findings"
        fdir.mkdir()
        shutil.copy(ROOT / "research" / "findings" / "SLUS-00940-USA.json", fdir)
        self.p = Project.create(root / "proj", "P", self.bin, findings_dir=fdir)
        self.p.add_changeset("R")
        self.p.bind("R").set_field("weapons", 1, "attack", 77)  # não deve entrar na BIN de teste

    def tearDown(self):
        self.tmp.cleanup()

    def test_bin_de_teste_altera_um_campo_so(self):
        t = testbin.value_test(self.p, "weapons", 182, 0x0C, "u16le", 999)
        self.assertEqual(t.image.parent.name, "testes")
        self.assertTrue(t.cue.exists())
        self.assertIn("weapons[182].price", t.description)
        self.assertIn("in_game_test", t.instructions)
        new = RomImage.open(t.image).read_file("SLUS_009.40")
        old = files()["SLUS_009.40"]
        diff = [i for i in range(len(old)) if old[i] != new[i]]
        self.assertEqual(diff, [0xB5C + 182 * 22 + 0x0C, 0xB5C + 182 * 22 + 0x0D])
        with self.assertRaises(testbin.TestBinError):
            testbin.value_test(self.p, "weapons", 182, 0x0C, "u16le", 999)
        testbin.value_test(self.p, "weapons", 182, 0x0C, "u16le", 999, overwrite=True)

    def test_recolorir_para_teste_magenta(self):
        t = testbin.recolor_test(self.p, "DATA/CHR/SPR.BIN", 64)
        spr = RomImage.open(t.image).read_file("DATA/CHR/SPR.BIN")
        info = tim.parse(spr, 64)
        pal = tim.palette(spr, info)
        self.assertEqual(pal[0], 0)  # transparente continua transparente
        self.assertTrue(all(v == testbin.MAGENTA for v in pal[1:]))
        self.assertEqual(tim.indices(spr, info), tim.indices(files()["DATA/CHR/SPR.BIN"], info))

    def test_findings_de_graficos(self):
        db = self.p.findings()
        found = tim.scan_image(self.p.open_image())
        new = testbin.register_tims(db, found)
        self.assertEqual([f["id"] for f in new], ["G-0100", "G-0101"])
        self.assertTrue(all(f["status"] == "HIPOTESE" for f in new))
        self.assertEqual(testbin.register_tims(db, found), [])  # sem duplicar
        empty = FindingsDB({"findings": []})
        ch = testbin.register_tims(empty, [])
        self.assertEqual((ch[0]["subject"], ch[0]["status"]), ("graphics.characters", "DESCONHECIDO"))
        self.assertIn("sem TIM solto", ch[0]["evidence"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
