"""Read the data.acd archive of a car."""

import struct

import pytest

from apps.catalog import acd

TYRES = "\r\n".join(
    [
        "[HEADER]",
        "VERSION=10",
        "",
        "[FRONT]",
        "NAME=Slick Soft",
        "SHORT_NAME=S",
        "WIDTH=0.300",
        "RADIUS=0.340             ; tyre radius in meters",
        "PRESSURE_IDEAL=26        ; ideal pressure for grip",
        "FZ0=3768",
        "DX_REF=1.59",
        "DY_REF=1.58",
        "WEAR_CURVE=slicks_front.lut",
    ]
    * 60
).encode()


def pack(files: dict[str, bytes], folder: str, fifth: int = 77, new_format: bool = True) -> bytes:
    """An archive made with the same scrambling (the fifth number of the key is free)."""
    key = acd._key(folder, fifth)
    out = struct.pack("<ii", -1111, 1) if new_format else b""
    for name, content in files.items():
        out += struct.pack("<i", len(name)) + name.encode() + struct.pack("<i", len(content))
        for index, byte in enumerate(content):
            out += bytes([(byte + key[index % len(key)]) & 0xFF, 0, 0, 0])
    return out


@pytest.mark.parametrize("fifth", [3, 77, 200])
@pytest.mark.parametrize("new_format", [True, False])
def test_reads_the_files(fifth, new_format):
    data = pack(
        {"tyres.ini": TYRES, "power.lut": b"0|0\r\n5000|300"},
        "ks_ferrari_488_gt3",
        fifth,
        new_format,
    )
    files = acd.read_acd(data, "ks_ferrari_488_gt3")
    assert files["tyres.ini"] == TYRES
    assert files["power.lut"] == b"0|0\r\n5000|300"


def test_a_folder_in_a_different_case_is_found():
    data = pack({"tyres.ini": TYRES}, "trr_gt3_bmw_m4_gt3")
    assert acd.read_acd(data, "TRR_GT3_bmw_m4_gt3")["tyres.ini"] == TYRES


def test_a_wrong_folder_name_is_refused_and_not_guessed():
    data = pack({"tyres.ini": TYRES}, "ks_ferrari_488_gt3")
    with pytest.raises(acd.AcdError):
        acd.read_acd(data, "ks_mazda_miata")


@pytest.mark.parametrize(
    "data", [b"", b"\x01\x00", b"\xff" * 40, struct.pack("<ii", -1111, 1) + b"\x05\x00"]
)
def test_a_broken_archive_is_refused(data):
    with pytest.raises(acd.AcdError):
        acd.read_acd(data, "ks_ferrari_488_gt3")
