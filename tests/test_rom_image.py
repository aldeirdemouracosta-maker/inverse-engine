"""RomImage: CD sintético com subpastas, arquivo Form 2 e executável avulso."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core.rom_image import RomImage, resolve_cue
from inverse_engine.formats import disc as cd
from inverse_engine.formats.psexe import PsExe
from tests.fixture_cd import CdBuilder, make_slus, LOAD_ADDRESS

BIG = bytes((i * 7) & 0xFF for i in range(5000))  # 3 setores


def build_cd():
    files = {
        "SYSTEM.CNF": b"BOOT = cdrom:\\SLUS_009.40;1\r\n",
        "SLUS_009.40": make_slus(),
        "DATA/BIG.BIN": BIG,
        "DATA/SUB/DEEP.DAT": b"fundo da arvore",
        "MOVIE/INTRO.STR": b"\x11" * 3000,
    }
    return CdBuilder().build(files, form2={"MOVIE/INTRO.STR"}), files


class RomImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bin, cls.files = build_cd()
        cls.image = RomImage.from_bytes(cls.bin)

    def test_lista_arquivos_com_subpastas(self):
        paths = {f.path for f in self.image.list_files()}
        for p in ("SYSTEM.CNF", "SLUS_009.40", "DATA", "DATA/BIG.BIN", "DATA/SUB", "DATA/SUB/DEEP.DAT",
                  "MOVIE/INTRO.STR"):
            self.assertIn(p, paths)

    def test_le_arquivos_iguais_ao_original(self):
        for p in ("SYSTEM.CNF", "SLUS_009.40", "DATA/BIG.BIN", "DATA/SUB/DEEP.DAT"):
            self.assertEqual(self.image.read_file(p), self.files[p], p)

    def test_nome_com_versao_e_minusculas(self):
        self.assertEqual(self.image.read_file("data/sub/deep.dat;1"), b"fundo da arvore")

    def test_form2_listado_e_nunca_lido_como_dados(self):
        entry = next(f for f in self.image.list_files() if f.path == "MOVIE/INTRO.STR")
        self.assertTrue(entry.form2)
        with self.assertRaises(cd.DiscError):
            self.image.read_file("MOVIE/INTRO.STR")
        kinds = {k for _, k in self.image.non_data_sectors()}
        self.assertEqual(kinds, {"mode2_form2"})

    def test_offset_de_arquivo_para_lba_e_bin(self):
        f = self.image.disc.get("DATA/BIG.BIN")
        lba, pos = self.image.file_offset_to_lba("DATA/BIG.BIN", 2048 + 5)
        self.assertEqual((lba, pos), (f.lba + 1, 5))
        b = self.image.file_offset_to_bin("DATA/BIG.BIN", 2048 + 5)
        self.assertEqual(b, (f.lba + 1) * cd.RAW_SECTOR + 24 + 5)
        self.assertEqual(self.bin[b], BIG[2048 + 5])
        self.assertEqual(self.image.bin_offset_to_user(b), (f.lba + 1, 5))
        self.assertEqual(self.image.disc.lba_to_file_offset(f.lba + 1, 5), ("DATA/BIG.BIN", 2053))

    def test_bytes_de_sistema_nao_sao_dados_de_usuario(self):
        f = self.image.disc.get("DATA/BIG.BIN")
        base = f.lba * cd.RAW_SECTOR
        for pos in (0, 11, 12, 15, 16, 23, 24 + 2048, 24 + 2048 + 4, cd.RAW_SECTOR - 1):
            got = self.image.bin_offset_to_user(base + pos)
            if 24 <= pos < 24 + 2048:
                self.assertIsNotNone(got)
            else:
                self.assertIsNone(got, pos)

    def test_offset_fora_do_arquivo_recusado(self):
        with self.assertRaises(cd.DiscError):
            self.image.file_offset_to_lba("DATA/SUB/DEEP.DAT", 100)

    def test_encontra_executavel_pelo_conteudo(self):
        self.assertEqual(self.image.find_executable(), "SLUS_009.40")

    def test_executavel_avulso(self):
        slus = make_slus()
        img = RomImage.from_bytes(slus, "SLUS_009.40")
        self.assertEqual(img.kind, "file")
        self.assertEqual(img.read_file("SLUS_009.40"), slus)
        self.assertIsNone(img.file_offset_to_lba("SLUS_009.40", 0x900))
        self.assertEqual(img.sha256, hashlib.sha256(slus).hexdigest())

    def test_ram_arquivo(self):
        exe = PsExe.parse(make_slus())
        self.assertEqual(exe.file_to_ram(0x800), LOAD_ADDRESS)
        self.assertEqual(exe.ram_to_file(LOAD_ADDRESS + 0x35C), 0xB5C)
        with self.assertRaises(ValueError):
            exe.file_to_ram(0x10)

    def test_cue_resolve_bin_e_original_intocado(self):
        with tempfile.TemporaryDirectory() as d:
            binp = Path(d) / "Jogo (USA).bin"
            binp.write_bytes(self.bin)
            cue = Path(d) / "Jogo (USA).cue"
            cue.write_text('FILE "Jogo (USA).bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
            self.assertEqual(resolve_cue(cue), binp)
            before = hashlib.sha256(binp.read_bytes()).hexdigest()
            img = RomImage.open(cue)
            img.read_file("DATA/BIG.BIN")
            self.assertEqual(img.kind, "bin")
            self.assertEqual(hashlib.sha256(binp.read_bytes()).hexdigest(), before)

    def test_nao_bin_sem_pvd_recusado(self):
        broken = bytearray(self.bin)
        start = 16 * cd.RAW_SECTOR + 24
        broken[start + 1:start + 6] = b"XXXXX"
        with self.assertRaises(cd.DiscError):
            cd.open_disc(bytes(broken))


if __name__ == "__main__":
    unittest.main()
