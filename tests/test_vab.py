"""Marco 9: SPU-ADPCM, VAB (VH+VB) e WAV com dados sintéticos."""
import struct
import unittest

from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import adpcm, vab, wav
from tests.fixture_cd import CdBuilder


def block(nibbles, shift=12, filt=0, flags=0):
    assert len(nibbles) == 28
    data = bytes((nibbles[2 * i] & 15) | ((nibbles[2 * i + 1] & 15) << 4) for i in range(14))
    return bytes([(filt << 4) | shift, flags]) + data


RAMP = [k % 16 for k in range(28)]                     # nibbles 0..15, 0..11
RAMP_PCM = [n - 16 if n >= 8 else n for n in RAMP]      # shift 12, filtro 0: o nibble com sinal


def build_vab(samples: list[bytes], programs: int = 1, inline: bool = True) -> bytes:
    vs = len(samples)
    vh_size = 32 + 128 * 16 + programs * 16 * 32 + 512
    total = vh_size + sum(len(s) for s in samples)
    hdr = vab.MAGIC + struct.pack("<IIIHHHHBBBBI", 7, 0, total, 0, programs, vs, vs, 127, 64, 0, 0, 0)
    progs = bytearray(128 * 16)
    progs[0] = vs                      # programa 0 com vs tons
    progs[1], progs[4] = 100, 64
    tones = bytearray(programs * 16 * 32)
    for k in range(vs):
        b = k * 32
        tones[b + 2], tones[b + 3], tones[b + 4], tones[b + 6], tones[b + 7] = 110, 64, 60, 0, 127
        struct.pack_into("<HHhh", tones, b + 16, 0x80FF, 0x5FC0, 0, k + 1)
    table = struct.pack("<256H", 0, *[len(s) // 8 for s in samples], *([0] * (255 - vs)))
    vh = hdr + bytes(progs) + bytes(tones) + table
    assert len(vh) == vh_size
    return vh + (b"".join(samples) if inline else b"")


class AdpcmTest(unittest.TestCase):
    def test_filtro_0_e_o_nibble_com_sinal(self):
        self.assertEqual(adpcm.decode(block(RAMP)), RAMP_PCM)

    def test_filtro_1_com_historico(self):
        first = block([1] + [0] * 27, shift=0)          # 4096 e depois zeros
        second = block([0] * 28, shift=12, filt=1)      # só o histórico: s = (s_ant × 60 + 32) >> 6
        pcm = adpcm.decode(first + second)
        self.assertEqual(pcm[0], 4096)
        self.assertEqual(pcm[1:28], [0] * 27)
        last = block([0] * 27 + [1], shift=0)           # 4096 na última amostra: o 2º bloco decai a partir dela
        pcm = adpcm.decode(last + second)
        exp, prev, older = [], 4096, 0
        for _ in range(28):
            prev, older = (prev * 60 + older * 0 + 32) >> 6, prev
            exp.append(prev)
        self.assertEqual(pcm[28:], exp)
        pcm = adpcm.decode(first + second)
        self.assertEqual(pcm[28:], [0] * 28)  # após 4096 vêm 27 zeros: o histórico chega zerado ao 2º bloco

    def test_satura_em_16_bits(self):
        pcm = adpcm.decode(block([7] * 28, shift=0) + block([7] * 28, shift=0, filt=1))
        self.assertEqual(max(pcm), 32767)
        self.assertTrue(all(-32768 <= s <= 32767 for s in pcm))

    def test_flags_e_erros(self):
        data = block(RAMP, flags=adpcm.FLAG_LOOP_START) + block(RAMP, flags=adpcm.FLAG_END | adpcm.FLAG_REPEAT)
        self.assertEqual(adpcm.loop_info(data), {"loop_start": 0, "end": 1, "repeat": True})
        self.assertEqual(len(adpcm.decode(data + block(RAMP), stop_at_end=True)), 56)
        with self.assertRaises(adpcm.AdpcmError):
            adpcm.decode(b"\x00" * 15)
        with self.assertRaises(adpcm.AdpcmError):
            adpcm.decode(bytes([0x5C]) + b"\x00" * 15)  # filtro 5


class VabTest(unittest.TestCase):
    def setUp(self):
        self.s1 = block(RAMP) + block(RAMP, flags=adpcm.FLAG_END)
        self.s2 = block([3] * 28)
        self.data = b"lixo" + build_vab([self.s1, self.s2]) + b"fim"

    def test_cabecalho_programas_tons_e_amostras(self):
        v = vab.scan(self.data)[0]
        self.assertEqual((v.offset, v.version, v.program_count, v.sample_count), (4, 7, 1, 2))
        self.assertEqual(v.sample_sizes, [32, 16])
        self.assertEqual([p["program"] for p in v.programs], [0])
        self.assertEqual([(t.sample, t.center) for t in v.tones], [(1, 60), (2, 60)])
        self.assertTrue(v.inline_vb)

    def test_wav_igual_ao_esperado(self):
        v = vab.scan(self.data)[0]
        w = wav.to_bytes(v.decode(0), vab.DEFAULT_RATE)
        samples, rate = wav.read(w)
        self.assertEqual(rate, 44100)
        self.assertEqual(samples, RAMP_PCM * 2)
        self.assertEqual(wav.read(wav.to_bytes(v.decode(1)))[0], [3] * 28)
        self.assertEqual(w[:4], b"RIFF")

    def test_vh_separado_do_vb(self):
        vh = build_vab([self.s1, self.s2], inline=False)
        v = vab.parse(vh)
        self.assertFalse(v.inline_vb)
        with self.assertRaisesRegex(vab.VabError, "VB"):
            v.decode(0)
        v.attach_vb(self.s1 + self.s2)
        self.assertEqual(v.decode(1), [3] * 28)
        with self.assertRaises(vab.VabError):
            v.attach_vb(self.s1)

    def test_cabecalho_incoerente_ignorado(self):
        bad = bytearray(build_vab([self.s2]))
        struct.pack_into("<H", bad, 0x12, 500)  # 500 programas
        self.assertEqual(vab.scan(bytes(bad)), [])

    def test_procura_no_cd_ignora_form2(self):
        v = build_vab([self.s2])
        cd = CdBuilder().build({"SOUND/SE.VAB": b"\x00" * 10 + v, "MOVIE/X.STR": v}, form2={"MOVIE/X.STR"})
        found = vab.scan_image(RomImage.from_bytes(cd))
        self.assertEqual([(p, x.offset) for p, x in found], [("SOUND/SE.VAB", 10)])


if __name__ == "__main__":
    unittest.main()
