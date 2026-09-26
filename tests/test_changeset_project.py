"""ChangeSet (grupos, desfazer/refazer) e arquivo de projeto (salvar/reabrir idêntico)."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core.changeset import ChangeSet
from inverse_engine.core.patch_stack import PatchError, PatchStack
from inverse_engine.core.project import Project, ProjectError, EXT
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import ppf
from tests.test_patch_stack import (PROFILE, FINDINGS, ATTACK_182, SAME_SECTOR_OUTSIDE_TABLE, cd, slus_with,
                                    recolor)


def attack(data, index=182):
    return struct.unpack_from("<H", RomImage.from_bytes(data).read_file("SLUS_009.40"),
                              0xB5C + index * 22 + 0xA)[0]


class ChangeSetTest(unittest.TestCase):
    def setUp(self):
        self.image = RomImage.from_bytes(cd())
        self.cs = ChangeSet("Rebalance").bind(self.image, PROFILE, FINDINGS)

    def test_operacao_registra_antes_depois_origem_e_finding(self):
        op = self.cs.set_field("weapons", 182, "attack", 45, origin="regras")
        self.assertEqual((op.target, op.before, op.after, op.origin, op.finding),
                         ("weapons[182].attack", 30, 45, "regras", "F-0011"))
        op2 = self.cs.set_field("weapons", 182, "attack", 50)
        self.assertEqual(op2.before, 45)
        self.assertNotEqual(op.group, op2.group)
        self.assertTrue(op.date)

    def test_grupo_desfeito_e_refeito_de_uma_vez(self):
        self.cs.set_field("weapons", 1, "attack", 5)
        with self.cs.group("assistente: machados −10%") as g:
            for i in (22, 23, 24):
                self.cs.set_field("weapons", i, "attack", 9)
        self.assertEqual({o.group for o in self.cs.ops[1:]}, {g})
        undone = self.cs.undo()
        self.assertEqual([o.target for o in undone], [f"weapons[{i}].attack" for i in (22, 23, 24)])
        self.assertEqual(len(self.cs.ops), 1)
        self.assertTrue(self.cs.can_redo())
        self.cs.redo()
        self.assertEqual(len(self.cs.ops), 4)
        self.cs.undo()
        self.cs.undo()
        self.assertFalse(self.cs.can_undo())
        self.assertEqual(self.cs.undo(), [])
        self.cs.redo()
        self.cs.set_field("weapons", 2, "attack", 1)  # operação nova apaga o refazer
        self.assertFalse(self.cs.can_redo())

    def test_erro_no_meio_do_grupo_nao_deixa_metade(self):
        with self.assertRaises(PatchError):
            with self.cs.group("plano"):
                self.cs.set_field("weapons", 1, "attack", 5)
                self.cs.set_field("weapons", 2, "attack", 999999)
        self.assertEqual(self.cs.ops, [])

    def test_politica_e_origem(self):
        with self.assertRaisesRegex(PatchError, "Modo Pesquisa"):
            self.cs.set_field("weapons", 1, "price", 10)
        with self.assertRaisesRegex(PatchError, "Modo Pesquisa"):
            self.cs.set_raw("SLUS_009.40", 0x3000, b"\x01")
        with self.assertRaisesRegex(PatchError, "origem"):
            self.cs.set_field("weapons", 1, "attack", 1, origin="palpite")
        with self.assertRaises(IndexError):
            self.cs.set_field("weapons", 300, "attack", 1)
        research = ChangeSet("P").bind(self.image, PROFILE, FINDINGS, research_mode=True)
        self.assertTrue(research.set_field("weapons", 1, "price", 10).experimental)
        op = research.set_raw("SLUS_009.40", 0x3000, b"\x01\x02")
        self.assertEqual((op.after, op.target), ("0102", "SLUS_009.40+0x3000"))

    def test_camadas_so_com_o_ultimo_valor_de_cada_alvo(self):
        self.cs.set_field("weapons", 182, "attack", 45)
        self.cs.set_field("weapons", 182, "attack", 60)
        self.cs.set_graphic(recolor(64))
        self.cs.set_graphic(recolor(64, 1, (0, 255, 0, 255)))
        layers = self.cs.to_layers()
        self.assertEqual([l.kind for l in layers], ["changeset", "graphics"])
        self.assertEqual(len(layers[0].edits), 1)
        self.assertEqual(layers[0].edits[0].value, 60)
        g = layers[1].edits[0]
        self.assertEqual(g.original, recolor(64).original)
        self.assertEqual(g.new, recolor(64, 1, (0, 255, 0, 255)).new)
        st = PatchStack(self.image, PROFILE, FINDINGS)
        for l in layers:
            st.add(l)
        self.assertEqual([c for c in st.conflicts() if c.kind == "CONFLITO"], [])
        self.assertEqual(attack(st.build().data), 60)

    def test_historico_visivel(self):
        with self.cs.group("frase"):
            self.cs.set_field("weapons", 3, "attack", 7, origin="IA")
        h = self.cs.history()
        self.assertEqual((h[0]["alvo"], h[0]["origem"], h[0]["rótulo"]), ("weapons[3].attack", "IA", "frase"))

    def test_ida_e_volta_em_dicionario(self):
        self.cs.set_field("weapons", 182, "attack", 45)
        self.cs.set_graphic(recolor(64))
        self.cs.set_field("weapons", 1, "attack", 3)
        self.cs.undo()
        again = ChangeSet.from_dict(json.loads(json.dumps(self.cs.to_dict())))
        self.assertEqual(again.to_dict(), self.cs.to_dict())
        self.assertEqual(again.redo()[0].target, "weapons[1].attack")


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "jogos").mkdir()
        (root / "patches").mkdir()
        self.bin = root / "jogos" / "Vandal Hearts II (USA).bin"
        self.bin.write_bytes(cd())
        self.cue = root / "jogos" / "Vandal Hearts II (USA).cue"
        self.cue.write_text('FILE "Vandal Hearts II (USA).bin" BINARY\n  TRACK 01 MODE2/2352\n')
        self.ppf = root / "patches" / "take_turns_sintetico.ppf"
        self.ppf.write_bytes(ppf.build_ppf3(cd(), cd(slus_with([(SAME_SECTOR_OUTSIDE_TABLE, b"\xEE")]))))
        self.folder = root / "projetos" / "rebalance"

    def tearDown(self):
        self.tmp.cleanup()

    def make(self):
        p = Project.create(self.folder, "Rebalance 2026", self.cue)
        p.add_patch(self.ppf, "Take Turns")
        p.add_changeset("Rebalance")
        cs = p.bind("Rebalance")
        with cs.group("espadas"):
            cs.set_field("weapons", 1, "attack", 11)
            cs.set_field("weapons", 2, "attack", 12)
        cs.set_field("weapons", 182, "attack", 45)
        cs.set_graphic(recolor(64))
        cs.set_field("weapons", 3, "attack", 13)
        cs.undo()  # fica no refazer
        return p

    def test_perfil_detectado_e_caminhos_relativos(self):
        p = self.make()
        self.assertEqual(p.profile_id, "SLUS-00940-USA")
        self.assertEqual(p.base_image, "../../jogos/Vandal Hearts II (USA).cue")
        self.assertEqual(p.patches["Take Turns"].path, "../../patches/take_turns_sintetico.ppf")
        self.assertEqual(p.base_sha256, RomImage.open(self.bin).sha256)

    def test_salvo_e_reaberto_identico(self):
        p = self.make()
        path = p.save()
        self.assertEqual(path.name, "Rebalance 2026" + EXT)
        q = Project.load(path)
        self.assertEqual(q.to_dict(), p.to_dict())
        self.assertEqual(q.save().read_text(encoding="utf-8"), path.read_text(encoding="utf-8"))
        a, b = p.stack().build().data, q.stack().build().data
        self.assertEqual(a, b)
        self.assertEqual(attack(a, 182), 45)
        self.assertEqual(attack(a, 3), attack(cd(), 3))  # desfeito
        cs = q.bind("Rebalance")
        cs.redo()
        self.assertEqual(attack(q.stack().build().data, 3), 13)

    def test_pasta_movida_junto_continua_abrindo(self):
        p = self.make()
        p.save()
        import shutil
        root = Path(self.tmp.name)
        new_root = root.parent / (root.name + "_copia")
        shutil.copytree(root, new_root)
        try:
            q = Project.load(new_root / "projetos" / "rebalance" / ("Rebalance 2026" + EXT))
            self.assertEqual(q.check_hashes(), [])
            self.assertEqual(q.stack().build().data, p.stack().build().data)
        finally:
            shutil.rmtree(new_root)

    def test_patch_alterado_recusado(self):
        p = self.make()
        p.save()
        data = bytearray(self.ppf.read_bytes())
        data[-1] ^= 1
        self.ppf.write_bytes(bytes(data))
        q = Project.load(p.path)
        with self.assertRaisesRegex(ProjectError, "P4"):
            q.stack()
        q.stack(accept_changed_files=True)

    def test_imagem_base_alterada_recusada(self):
        p = self.make()
        p.save()
        data = bytearray(self.bin.read_bytes())
        data[-1] ^= 1
        self.bin.write_bytes(bytes(data))
        with self.assertRaisesRegex(ProjectError, "imagem base mudou"):
            Project.load(p.path).stack()

    def test_ordem_e_ativacao(self):
        p = self.make()
        self.assertEqual([o["name"] for o in p.order], ["Take Turns", "Rebalance"])
        p.move("Rebalance", 0)
        self.assertEqual([o["name"] for o in p.order], ["Rebalance", "Take Turns"])
        full = p.stack().build().data
        p.set_active("Take Turns", False)
        without = p.stack().build().data
        self.assertNotEqual(full, without)
        slus = RomImage.from_bytes(without).read_file("SLUS_009.40")
        self.assertNotEqual(slus[SAME_SECTOR_OUTSIDE_TABLE], 0xEE)
        with self.assertRaises(ProjectError):
            p.add_changeset("Take Turns")

    def test_projeto_invalido_recusado(self):
        p = self.make()
        path = p.save()
        d = json.loads(path.read_text(encoding="utf-8"))
        d["order"].append({"type": "changeset", "name": "fantasma"})
        path.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(ProjectError):
            Project.load(path)
        d["format"] = 99
        path.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(ProjectError):
            Project.load(path)

    def test_patch_novo_entra_antes_dos_changesets(self):
        p = Project.create(self.folder, "X", self.bin)
        p.add_changeset("Rebalance")
        p.add_patch(self.ppf, "Take Turns")
        self.assertEqual([o["name"] for o in p.order], ["Take Turns", "Rebalance"])

    def test_nao_ppf_recusado(self):
        p = Project.create(self.folder, "X", self.bin)
        other = Path(self.tmp.name) / "patches" / "x.ips"
        other.write_bytes(b"PATCH...EOF")
        with self.assertRaises(ProjectError):
            p.add_patch(other)


if __name__ == "__main__":
    unittest.main()
