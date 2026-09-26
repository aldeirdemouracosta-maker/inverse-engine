import struct
from pathlib import Path

from vh2studio.core import BinarySource, ChangeSet, encode_scalar, decode_scalar
from vh2studio.tim import scan_tims, decode_tim


def test_binary_scan_and_changes(tmp_path):
    p=tmp_path/'sample.bin'
    data=bytearray(range(256))*4
    data[100:102]=struct.pack('<H',0xB6)
    p.write_bytes(data)
    src=BinarySource.load(p)
    assert 100 in src.scan_value(0xB6,'u16le')
    assert 100 in src.scan_hex_pattern('B6 00')
    cs=ChangeSet(src)
    cs.stage(100,b'\x34\x12','test')
    assert cs.validate()==[]
    out=tmp_path/'out.bin'
    cs.build_copy(out)
    assert out.read_bytes()[100:102]==b'\x34\x12'
    assert p.read_bytes()[100:102]==b'\xB6\x00'
    ips=tmp_path/'out.ips'
    cs.export_ips(ips)
    assert ips.read_bytes().startswith(b'PATCH') and ips.read_bytes().endswith(b'EOF')


def make_16bpp_tim():
    # 2x2 TIM, no CLUT, 16bpp
    hdr=b'\x10\x00\x00\x00'+struct.pack('<I',2)
    pixels=struct.pack('<HHHH',0x001F,0x03E0,0x7C00,0x7FFF)
    block_len=12+len(pixels)
    block=struct.pack('<IHHHH',block_len,0,0,2,2)+pixels
    return hdr+block


def test_tim_decoder(tmp_path):
    tim=make_16bpp_tim()
    blob=b'abc'+tim+b'xyz'
    infos=scan_tims(blob)
    assert len(infos)==1
    assert infos[0].offset==3
    im,info=decode_tim(blob,3)
    assert im.size==(2,2)
    assert info.bpp==16


def test_scalar_roundtrip():
    for dtype,val in [('u8',12),('u16le',500),('u32le',0x12345678),('s16le',-20)]:
        raw=encode_scalar(val,dtype)
        assert decode_scalar(raw,dtype)==val
