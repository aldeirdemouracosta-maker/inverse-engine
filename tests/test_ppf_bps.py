"""PPF 1/2/3 e BPS com imagens sintéticas."""
import random
import struct
import unittest
import zlib

from inverse_engine.formats import bps, ppf


def image(n=0x9320 + 4096, seed=1):
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(n))


def patched(src, changes):
    out = bytearray(src)
    for off, data in changes:
        out[off:off + len(data)] = data
    return bytes(out)


class PpfTest(unittest.TestCase):
    def setUp(self):
        self.src = image()
        self.dst = patched(self.src, [(10, b"\xAA\xBB"), (0x9400, b"x" * 300), (len(self.src) - 1, b"\x00")])

    def test_ppf3_ida_e_volta(self):
        p = ppf.parse(ppf.build_ppf3(self.src, self.dst, "teste"))
        self.assertEqual(p.version, 3)
        self.assertEqual(p.description, "teste")
        self.assertIsNone(p.check_block(self.src))
        self.assertEqual(p.apply_to(self.src), self.dst)
        self.assertEqual(sum(len(d) for _, d in p.records), 2 + 300 + 1)

    def test_ppf3_com_undo_e_sem_bloco(self):
        p = ppf.parse(ppf.build_ppf3(self.src, self.dst, blockcheck=False, undo=True))
        self.assertIsNone(p.block)
        self.assertEqual(p.apply_to(self.src), self.dst)
        self.assertEqual(p.undo[0], self.src[10:12])

    def test_bloco_de_conferencia_errado(self):
        p = ppf.parse(ppf.build_ppf3(self.src, self.dst))
        other = patched(self.src, [(0x9320 + 5, b"\x00\x01")])
        self.assertIn("não confere", p.check_block(other))

    def test_ppf3_com_file_id_diz(self):
        raw = ppf.build_ppf3(self.src, self.dst)
        diz = b"Patch de teste"
        for tail in (struct.pack("<H", len(diz)), struct.pack("<I", len(diz))):
            p = ppf.parse(raw + ppf.DIZ_BEGIN + diz + ppf.DIZ_END + tail)
            self.assertEqual(p.file_id, "Patch de teste")
            self.assertEqual(p.apply_to(self.src), self.dst)

    def test_ppf2(self):
        recs = struct.pack("<IB", 10, 2) + b"\xAA\xBB"
        raw = b"PPF20\x01" + b"d".ljust(50) + struct.pack("<I", len(self.src)) + self.src[0x9320:0x9320 + 1024] + recs
        p = ppf.parse(raw)
        self.assertEqual(p.version, 2)
        self.assertIsNone(p.check_block(self.src))
        self.assertIn("tamanho", p.check_block(self.src + b"\x00"))
        self.assertEqual(p.apply_to(self.src)[10:12], b"\xAA\xBB")

    def test_ppf1(self):
        raw = b"PPF10\x00" + b"d".ljust(50) + struct.pack("<IB", 3, 1) + b"\x55"
        p = ppf.parse(raw)
        self.assertEqual((p.version, p.records), (1, [(3, b"\x55")]))

    def test_invalido_e_truncado(self):
        with self.assertRaises(ppf.PpfError):
            ppf.parse(b"IPS00")
        with self.assertRaises(ppf.PpfError):
            ppf.parse(b"PPF10\x00" + b" " * 50 + struct.pack("<IB", 3, 9) + b"\x55")


class BpsTest(unittest.TestCase):
    def test_ida_e_volta(self):
        src = image(20000, 2)
        dst = patched(src, [(0, b"Z"), (5000, b"q" * 40), (19999, b"\x01")])
        patch = bps.create(src, dst, "meta")
        self.assertEqual(bps.apply(src, patch), dst)
        self.assertLess(len(patch), 200)

    def test_destino_maior_e_menor(self):
        src = image(1000, 3)
        for dst in (src + b"extra", src[:500]):
            self.assertEqual(bps.apply(src, bps.create(src, dst)), dst)

    def test_origem_errada_e_patch_corrompido(self):
        src = image(1000, 4)
        patch = bps.create(src, patched(src, [(1, b"\x00")]))
        with self.assertRaises(bps.BpsError):
            bps.apply(patched(src, [(900, b"\xFF\xFE")]), patch)
        bad = bytearray(patch)
        bad[8] ^= 1
        with self.assertRaises(bps.BpsError):
            bps.apply(src, bytes(bad))

    def test_source_copy_e_target_copy(self):
        # Patch montado à mão para exercitar as quatro ações.
        src = b"ABCDEFGH"
        tgt = b"ABCDxyxyxyEF"
        body = b"BPS1" + bps._vlq(len(src)) + bps._vlq(len(tgt)) + bps._vlq(0)
        body += bps._vlq((4 - 1) << 2 | bps.SOURCE_READ)                     # ABCD
        body += bps._vlq((2 - 1) << 2 | bps.TARGET_READ) + b"xy"             # xy
        body += bps._vlq((4 - 1) << 2 | bps.TARGET_COPY) + bps._vlq(4 << 1)  # xyxy (sobreposto)
        body += bps._vlq((2 - 1) << 2 | bps.SOURCE_COPY) + bps._vlq(4 << 1)  # EF
        body += struct.pack("<II", zlib.crc32(src), zlib.crc32(tgt))
        body += struct.pack("<I", zlib.crc32(body))
        self.assertEqual(bps.apply(src, body), tgt)


if __name__ == "__main__":
    unittest.main()
