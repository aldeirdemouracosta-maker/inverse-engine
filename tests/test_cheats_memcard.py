"""Marco 8: cheats GameShark a partir do perfil e memory card (.mcr/.mcs)."""
import copy
import json
import random
import struct
import unittest
from pathlib import Path

from inverse_engine.core.profile import RomProfile
from inverse_engine.formats import memcard, png
from inverse_engine.formats.psexe import PsExe
from inverse_engine.research import cheats
from tests.fixture_cd import make_slus
from tests.test_patch_stack import FINDINGS

ROOT = Path(__file__).resolve().parent.parent
SLUS = make_slus(names={182: "Rebelrod"})


def profile_without_ram():
    """Perfil real sem `record_ram` (para testar a recusa sem endereço com evidência)."""
    d = json.loads((ROOT / "profiles" / "SLUS-00940-USA.json").read_text(encoding="utf-8"))
    d["tables"]["weapons"].pop("record_ram", None)
    return RomProfile(d)


def profile_with_ram(address="0x800A0000", finding="F-0003"):
    d = json.loads((ROOT / "profiles" / "SLUS-00940-USA.json").read_text(encoding="utf-8"))
    d["tables"]["weapons"]["record_ram"] = {"address": address, "finding": finding}
    return RomProfile(d)


def db_with_ram_evidence(status="CONFIRMADO"):
    db = copy.deepcopy(FINDINGS)
    db.findings["F-0003"] = {"id": "F-0003", "subject": "weapons.record_ram", "status": status,
                             "evidence": [{"kind": "emulator_breakpoint", "detail": "sintético", "date": None}],
                             "history": []}
    return db


class CheatTest(unittest.TestCase):
    def test_perfil_real_tem_ram_das_armas_com_evidencia(self):
        t = RomProfile.load(ROOT / "profiles" / "SLUS-00940-USA.json").table("weapons")
        self.assertEqual(t.record_ram, 0x8006C35C)       # = 0x8006C000 + 0xB5C − 0x800
        c = cheats.field_cheat(t, SLUS, 182, "attack", 45, FINDINGS)
        self.assertFalse(c.experimental)                  # F-0003 e F-0011 PROVAVEL
        self.assertEqual(c.address, 0x8006C35C + 182 * 22 + 0xA)
        s = RomProfile.load(ROOT / "profiles" / "SLUS-00940-USA.json").table("skills")
        self.assertEqual(s.record_ram, 0x8008154C)       # = 0x8006C000 + 0x15D4C − 0x800

    def test_sem_endereco_com_evidencia_recusa(self):
        t = profile_without_ram().table("weapons")
        with self.assertRaisesRegex(cheats.CheatError, "Modo Pesquisa"):
            cheats.field_cheat(t, SLUS, 182, "attack", 45, FINDINGS)

    def test_modo_pesquisa_usa_endereco_do_executavel_como_experimental(self):
        t = profile_without_ram().table("weapons")
        c = cheats.field_cheat(t, SLUS, 182, "attack", 45, FINDINGS, research_mode=True)
        addr = PsExe.parse(SLUS).file_to_ram(0xB5C) + 182 * 22 + 0xA
        self.assertEqual(c.address, addr)
        self.assertEqual(c.lines, [f"80{addr & 0xFFFFFF:06X} 002D"])
        self.assertTrue(c.experimental)
        self.assertIn("HIPOTESE", c.note)

    def test_codigo_bate_com_o_endereco_ram_esperado(self):
        t = profile_with_ram().table("weapons")
        c = cheats.field_cheat(t, SLUS, 182, "attack", 45, db_with_ram_evidence())
        self.assertEqual(c.address, 0x800A0000 + 182 * 22 + 0xA)
        self.assertEqual(c.lines, ["800A0FAE 002D"])
        self.assertFalse(c.experimental)  # record_ram CONFIRMADO e ataque PROVAVEL
        self.assertTrue(cheats.field_cheat(t, SLUS, 182, "price", 1, db_with_ram_evidence()).experimental)

    def test_record_ram_em_hipotese_recusado(self):
        t = profile_with_ram().table("weapons")
        db = db_with_ram_evidence("HIPOTESE")
        with self.assertRaisesRegex(cheats.CheatError, "sem evidência"):
            cheats.field_cheat(t, SLUS, 182, "attack", 45, db)
        self.assertTrue(cheats.field_cheat(t, SLUS, 182, "attack", 45, db, research_mode=True).experimental)

    def test_8_bits_impar_e_condicional(self):
        t = profile_with_ram().table("weapons")
        db = db_with_ram_evidence()
        self.assertEqual(cheats.field_cheat(t, SLUS, 0, "range", 3, db).lines, ["300A0007 0003"])
        odd = profile_with_ram("0x800A0001").table("weapons")
        self.assertEqual(cheats.field_cheat(odd, SLUS, 0, "attack", 0x1234, db).lines,
                         ["300A000B 0034", "300A000C 0012"])
        c = cheats.field_cheat(t, SLUS, 182, "attack", 45, db, only_if=30)
        self.assertEqual(c.lines, ["D00A0FAE 001E", "800A0FAE 002D"])
        with self.assertRaises(cheats.CheatError):
            cheats.field_cheat(t, SLUS, 182, "attack", 70000, db)

    def test_exportar_duckstation_e_texto(self):
        t = profile_with_ram().table("weapons")
        cs = [cheats.field_cheat(t, SLUS, 182, "attack", 45, db_with_ram_evidence())]
        cht = cheats.to_duckstation(cs)
        self.assertIn("[weapons[182].attack = 45]", cht)
        self.assertIn("Type = Gameshark", cht)
        self.assertIn("800A0FAE 002D", cht)
        self.assertIn("# weapons[182].attack = 45", cheats.to_text(cs))


def make_mcs(name=b"BASLUS-00940VH2TEST", blocks=2, seed=1):
    rng = random.Random(seed)
    head = bytearray(128)
    struct.pack_into("<IIH", head, 0, memcard.FIRST, blocks * memcard.BLOCK, 0xFFFF)
    head[0x0A:0x0A + len(name)] = name
    head[127] = memcard.checksum(head)
    b0 = bytearray(rng.randrange(256) for _ in range(memcard.BLOCK))
    b0[:4] = b"SC\x11\x01"
    title = "ＶＨ２　ＴＥＳＴ".encode("shift_jis")
    b0[4:0x44] = title.ljust(64, b"\x00")
    struct.pack_into("<16H", b0, 0x60, *([0] + [0x7C00 + k for k in range(15)]))
    b0[128:256] = bytes((k % 16) | ((k // 16 % 16) << 4) for k in range(128))
    rest = bytes(rng.randrange(256) for _ in range(memcard.BLOCK * (blocks - 1)))
    return bytes(head) + bytes(b0) + rest


class MemCardTest(unittest.TestCase):
    def test_cartao_vazio(self):
        c = memcard.MemCard.blank()
        self.assertEqual((c.saves(), len(c.free_slots()), c.bad_checksums()), ([], 15, []))
        with self.assertRaises(memcard.MemCardError):
            memcard.MemCard(b"\x00" * 100)
        with self.assertRaises(memcard.MemCardError):
            memcard.MemCard(b"XX" + bytes(memcard.CARD_SIZE - 2))

    def test_listar_exportar_e_reimportar_com_checksum(self):
        mcs = make_mcs()
        card = memcard.MemCard.blank()
        s = card.import_mcs(mcs)
        self.assertEqual((s.name, s.blocks, s.size, s.title, s.icon_frames), ("BASLUS-00940VH2TEST", [0, 1],
                                                                               2 * memcard.BLOCK, "VH2 TEST", 1))
        self.assertTrue(s.checksum_ok)
        self.assertEqual(card.bad_checksums(), [])
        self.assertEqual(card.export_mcs(s), mcs)
        other = memcard.MemCard.blank()
        other.import_mcs(card.export_mcs(s))
        self.assertEqual(other.to_bytes(), card.to_bytes())
        again = memcard.MemCard(card.to_bytes())  # regravado e relido
        self.assertEqual([x.name for x in again.saves()], ["BASLUS-00940VH2TEST"])

    def test_encadeamento_em_blocos_nao_contiguos(self):
        card = memcard.MemCard.blank()
        card.import_mcs(make_mcs(b"BASLUS-00940A", 1, 2))
        card.import_mcs(make_mcs(b"BASLUS-00940B", 1, 3))
        a = next(s for s in card.saves() if s.name.endswith("A"))
        card.data[(a.slot + 1) * 128] = 0xA1  # apagado → bloco livre no meio
        card.data[(a.slot + 1) * 128 + 127] = memcard.checksum(card.data[(a.slot + 1) * 128:(a.slot + 2) * 128])
        s = card.import_mcs(make_mcs(b"BASLUS-00940C", 3, 4))
        self.assertEqual(s.blocks, [0, 2, 3])
        self.assertEqual(card.export_mcs(s), make_mcs(b"BASLUS-00940C", 3, 4))

    def test_duplicado_e_sem_espaco_recusados(self):
        card = memcard.MemCard.blank()
        card.import_mcs(make_mcs())
        with self.assertRaisesRegex(memcard.MemCardError, "já existe"):
            card.import_mcs(make_mcs())
        with self.assertRaisesRegex(memcard.MemCardError, "livre"):
            card.import_mcs(make_mcs(b"BASLUS-00940BIG", 14))

    def test_checksum_corrompido_detectado(self):
        card = memcard.MemCard.blank()
        s = card.import_mcs(make_mcs())
        card.data[(s.slot + 1) * 128 + 20] ^= 1
        self.assertIn(s.slot + 1, card.bad_checksums())
        self.assertFalse(card.saves()[0].checksum_ok)

    def test_icone_png(self):
        card = memcard.MemCard.blank()
        s = card.import_mcs(make_mcs())
        img = png.read(card.icon_png(s))
        self.assertEqual((img.width, img.height), (16, 16))
        self.assertEqual(img.rows[0][:4], [0, 0, 1, 0])
        self.assertEqual(img.palette[0][3], 0)  # cor 0 transparente


if __name__ == "__main__":
    unittest.main()
