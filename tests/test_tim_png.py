"""TIM e PNG sem Pillow: procura, exportação e reimportação com o mesmo tamanho."""
import struct
import unittest
import zlib

from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import png, tim
from tests.fixture_cd import CdBuilder

PAL = [0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF] + [0x0421 * i for i in range(1, 12)]  # 16 cores
PIX4 = [[(x + y) % 5 for x in range(8)] for y in range(4)]


def tim4():
    return tim.build(4, 8, 4, PIX4, clut=[PAL, [0x1111] * 16])


def png_with_filters(width, height, rows):
    """PNG RGBA com um filtro diferente em cada linha (1..4), para exercitar a leitura."""
    raw = bytearray()
    prev = bytes(width * 4)
    for y, r in enumerate(rows):
        line = b"".join(bytes(p) for p in r)
        f = 1 + y % 4
        out = bytearray()
        for i in range(len(line)):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            pred = {1: a, 2: b, 3: (a + b) >> 1, 4: png._paeth(a, b, c)}[f]
            out.append((line[i] - pred) & 0xFF)
        raw += bytes([f]) + out
        prev = line
    chunk = png._chunk
    return (png.SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


class PngTest(unittest.TestCase):
    def test_indexado_ida_e_volta(self):
        pal = [(0, 0, 0, 0), (255, 0, 0, 255), (0, 255, 0, 128)]
        data = png.write_indexed(3, 2, [[0, 1, 2], [2, 1, 0]], pal)
        img = png.read(data)
        self.assertEqual((img.width, img.height, img.color_type), (3, 2, 3))
        self.assertEqual(img.rows, [[0, 1, 2], [2, 1, 0]])
        self.assertEqual(img.palette, pal)

    def test_filtros_1_a_4(self):
        rows = [[(x * 30 % 256, y * 50 % 256, (x * y) % 256, 255) for x in range(5)] for y in range(8)]
        self.assertEqual(png.read(png_with_filters(5, 8, rows)).rows, rows)

    def test_entrelacado_recusado(self):
        data = bytearray(png.write_rgba(1, 1, [[(1, 2, 3, 255)]]))
        ihdr = bytearray(data[16:29])
        ihdr[12] = 1
        data[16:29] = ihdr
        data[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + bytes(ihdr)))
        with self.assertRaisesRegex(png.PngError, "entrelaçado"):
            png.read(bytes(data))

    def test_crc_errado_recusado(self):
        data = bytearray(png.write_rgba(1, 1, [[(1, 2, 3, 255)]]))
        data[20] ^= 1
        with self.assertRaises(png.PngError):
            png.read(bytes(data))


class TimTest(unittest.TestCase):
    def setUp(self):
        self.t = tim4()
        self.blob = b"lixo\x10\x00\x00\x00lixo" + self.t + b"\x10\x00\x00\x00" + b"\xFF" * 20
        self.info = tim.scan(self.blob)[0]

    def test_procura_e_cabecalho(self):
        self.assertEqual(len(tim.scan(self.blob)), 1)
        i = self.info
        self.assertEqual((i.offset, i.bpp, i.width, i.height, i.size), (12, 4, 8, 4, len(self.t)))
        self.assertEqual((i.vram_pos, i.clut_pos, i.clut_colors, i.clut_count), ((320, 0), (0, 480), 16, 2))
        self.assertIn("4bpp 8×4", i.describe())

    def test_exporta_png_indexado(self):
        img = png.read(tim.export_png(self.blob, self.info))
        self.assertEqual(img.rows, PIX4)
        self.assertEqual(img.palette[0], (0, 0, 0, 0))
        self.assertEqual(img.palette[1], (255, 0, 0, 255))

    def test_reimportar_sem_mudanca_devolve_mesmos_bytes(self):
        out = tim.import_drawing(self.blob, self.info, tim.export_png(self.blob, self.info))
        self.assertEqual(out, self.t)

    def test_paleta_reordenada_aceita(self):
        img = png.read(tim.export_png(self.blob, self.info))
        order = list(range(16))[::-1]
        pal = [img.palette[i] for i in order]
        rows = [[order.index(v) for v in r] for r in img.rows]
        out = tim.import_drawing(self.blob, self.info, png.write_indexed(8, 4, rows, pal))
        self.assertEqual(out, self.t)

    def test_redesenho_muda_so_pixels(self):
        rows = [r[:] for r in PIX4]
        rows[0][0] = 4
        pal = [tim.to_rgba(v) for v in PAL]
        out = tim.import_drawing(self.blob, self.info, png.write_indexed(8, 4, rows, pal))
        self.assertEqual(len(out), len(self.t))
        diff = [i for i in range(len(out)) if out[i] != self.t[i]]
        rel = self.info.pixel_offset - self.info.offset
        self.assertEqual(diff, [rel])
        self.assertEqual(tim.indices(out, tim.parse(out, 0))[0][0], 4)

    def test_cor_fora_da_paleta_recusada(self):
        rows = [[(9, 9, 9, 255)] * 8 for _ in range(4)]
        with self.assertRaisesRegex(tim.TimError, "não existe na paleta"):
            tim.import_drawing(self.blob, self.info, png.write_rgba(8, 4, rows))

    def test_tamanho_diferente_recusado(self):
        with self.assertRaisesRegex(tim.TimError, "tamanho"):
            tim.import_drawing(self.blob, self.info, png.write_indexed(4, 4, [[0] * 4] * 4, [(0, 0, 0, 0)]))

    def test_recolorir_nao_altera_pixels(self):
        img = png.read(tim.export_png(self.blob, self.info))
        pal = list(img.palette)
        pal[1] = (255, 0, 255, 255)
        out = tim.import_colors(self.blob, self.info, png.write_indexed(8, 4, img.rows, pal))
        o = tim.parse(out, 0)
        self.assertEqual(tim.indices(out, o), PIX4)
        self.assertEqual(out[o.pixel_offset:], self.t[o.pixel_offset:])
        self.assertEqual(tim.palette(out, o)[1], 0x7C1F)
        self.assertEqual(tim.palette(out, o, 1), [0x1111] * 16)  # a outra paleta fica igual

    def test_recolorir_com_pixels_mudados_recusado(self):
        img = png.read(tim.export_png(self.blob, self.info))
        rows = [r[:] for r in img.rows]
        rows[1][1] = 0
        with self.assertRaisesRegex(tim.TimError, "pixels"):
            tim.import_colors(self.blob, self.info, png.write_indexed(8, 4, rows, img.palette))

    def test_preto_opaco_recebe_stp(self):
        self.assertEqual(tim.from_rgba((0, 0, 0, 255)), 0x8000)
        self.assertEqual(tim.from_rgba((0, 0, 0, 0)), 0x0000)
        self.assertEqual(tim.from_rgba((255, 255, 255, 255)), 0x7FFF)
        self.assertEqual(tim.to_rgba(0x8000), (0, 0, 0, 255))

    def test_16bpp_ida_e_volta(self):
        t = tim.build(16, 2, 2, [[0x001F, 0x8000], [0x0000, 0x7FFF]])
        info = tim.parse(t, 0)
        img = png.read(tim.export_png(t, info))
        self.assertEqual(img.rows[0][1], (0, 0, 0, 255))
        self.assertEqual(tim.import_drawing(t, info, tim.export_png(t, info)), t)

    def test_tim_incoerente_recusado(self):
        bad = bytearray(self.t)
        bad[8] ^= 0x40  # tamanho da CLUT
        with self.assertRaises(tim.TimError):
            tim.parse(bytes(bad), 0)


class TimNoCdTest(unittest.TestCase):
    def test_subpasta_encontrada_e_form2_ignorado(self):
        t = tim4()
        cd = CdBuilder().build({"DATA/CHR/SPR.BIN": b"\x00" * 100 + t, "MOVIE/X.STR": t},
                               form2={"MOVIE/X.STR"})
        found = tim.scan_image(RomImage.from_bytes(cd))
        self.assertEqual([(p, i.offset) for p, i in found], [("DATA/CHR/SPR.BIN", 100)])


if __name__ == "__main__":
    unittest.main()
