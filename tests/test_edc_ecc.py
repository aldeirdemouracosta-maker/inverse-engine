"""EDC/ECC: conferência contra a definição do ECMA-130, independente do algoritmo usado."""
import random
import struct
import unittest

from inverse_engine.formats import edc_ecc
from inverse_engine.formats.disc import open_disc, RAW_SECTOR
from tests.fixture_cd import raw_sector, CdBuilder


def gf_mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11D
        b >>= 1
    return r


def gf_pow(a: int, n: int) -> int:
    r = 1
    for _ in range(n):
        r = gf_mul(r, a)
    return r


def syndromes_zero(vec: list[int]) -> bool:
    """H = [[1…1], [α^(n-1) … α^1, 1]] com α = 2 (ECMA-130, anexo A)."""
    n = len(vec)
    s0 = 0
    s1 = 0
    for i, v in enumerate(vec):
        s0 ^= v
        s1 ^= gf_mul(v, gf_pow(2, n - 1 - i))
    return s0 == 0 and s1 == 0


def words_from(sector: bytes) -> tuple[list[int], list[int]]:
    """Os 2340 bytes a partir do 12 como 1170 palavras: plano MSB e LSB (ECMA-130 §14)."""
    body = sector[12:12 + 2340]
    return [body[2 * i + 1] for i in range(1170)], [body[2 * i] for i in range(1170)]


def random_sector(rng: random.Random, lba: int, form2: bool = False, mode: int = 2) -> bytes:
    size = 2324 if form2 else 2048
    return edc_ecc.compute(raw_sector(lba, bytes(rng.randrange(256) for _ in range(size)), form2, mode))


class EdcTest(unittest.TestCase):
    def test_polinomio_e_o_do_ecma130(self):
        # P(x) = (x^16 + x^15 + x^2 + 1)(x^16 + x^2 + x + 1) sobre GF(2)
        a, b = (1 << 16) | (1 << 15) | (1 << 2) | 1, (1 << 16) | (1 << 2) | (1 << 1) | 1
        prod = 0
        for i in range(17):
            if b >> i & 1:
                prod ^= a << i
        self.assertEqual(prod, 0x18001801B)
        rev = int(f"{prod & 0xFFFFFFFF:032b}"[::-1], 2)
        self.assertEqual(rev, edc_ecc.EDC_POLY_REFLECTED)

    def test_tabela_igual_ao_calculo_bit_a_bit(self):
        rng = random.Random(1)
        data = bytes(rng.randrange(256) for _ in range(500))
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0xD8018001 if crc & 1 else 0)
        self.assertEqual(edc_ecc.edc(data), crc)

    def test_residuo_zero_com_edc_anexado(self):
        s = random_sector(random.Random(2), 20)
        self.assertEqual(edc_ecc.edc(s[16:2076]), 0)


class EccTest(unittest.TestCase):
    def test_sindromes_p_e_q_zeradas_em_40_setores(self):
        rng = random.Random(3)
        for n in range(40):
            mode = 1 if n % 5 == 0 else 2
            s = bytearray(random_sector(rng, 100 + n, mode=mode))
            if mode == 2:
                s[12:16] = b"\x00\x00\x00\x00"  # Mode 2: cabeçalho entra como zero no ECC
            for plane in words_from(bytes(s)):
                for np_ in range(43):  # P: 43 colunas de 24 palavras + 2 de paridade
                    vec = [plane[np_ + 43 * m] for m in range(24)] + [plane[1032 + np_], plane[1075 + np_]]
                    self.assertTrue(syndromes_zero(vec), f"P setor {n} coluna {np_}")
                for nq in range(26):  # Q: 26 diagonais de 43 palavras + 2 de paridade
                    vec = [plane[(43 * nq + 44 * m) % 1118] for m in range(43)]
                    vec += [plane[1118 + nq], plane[1144 + nq]]
                    self.assertTrue(syndromes_zero(vec), f"Q setor {n} diagonal {nq}")

    def test_regravar_setor_valido_nao_muda_nada(self):
        s = random_sector(random.Random(4), 30)
        self.assertEqual(edc_ecc.compute(s), s)
        self.assertTrue(edc_ecc.is_valid(s))

    def test_bit_trocado_detectado(self):
        rng = random.Random(5)
        s = random_sector(rng, 31)
        for pos in (24, 1000, 2071, 18, edc_ecc.P_AT + 3, edc_ecc.Q_AT + 50):
            bad = bytearray(s)
            bad[pos] ^= 0x10
            self.assertFalse(edc_ecc.is_valid(bytes(bad)), pos)

    def test_form2_edc(self):
        s = random_sector(random.Random(6), 40, form2=True)
        self.assertNotEqual(s[2348:2352], b"\x00" * 4)
        self.assertTrue(edc_ecc.is_valid(s))
        zeroed = s[:2348] + b"\x00" * 4
        self.assertTrue(edc_ecc.is_valid(zeroed))  # EDC de Form 2 é opcional
        bad = bytearray(s)
        bad[100] ^= 1
        self.assertFalse(edc_ecc.is_valid(bytes(bad)))

    def test_cd_da_fixture_tem_edc_ecc_valido(self):
        disc = open_disc(CdBuilder().build({"A.BIN": b"a" * 3000, "V.STR": b"v" * 100}, form2={"V.STR"}))
        for lba in range(disc.sector_count):
            self.assertTrue(edc_ecc.is_valid(disc.raw_sector(lba)), lba)
        self.assertEqual(len(disc.data) % RAW_SECTOR, 0)


if __name__ == "__main__":
    unittest.main()
