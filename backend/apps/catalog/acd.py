"""Read the data.acd file of an Assetto Corsa car (the same as Content Manager does).

A car keeps its physics files (tyres.ini, engine.ini, setup.ini, ...) in a data.acd archive. The
files are scrambled with a key that comes from the name of the car folder, so the folder name
is needed to read them. The layout is:

    [int32 -1111, int32 version]      only in the newer archives
    then for each file:
    int32 name length, name, int32 size, and the content with 4 bytes for each byte of the file
    (only the first of every 4 bytes is the data)

A car can also have an unpacked "data" folder instead. The caller handles that case.

The key is 8 numbers joined with "-". We know how 7 of them come from the folder name. The
fifth is not known, but it is one byte, so we test the 256 values and keep the one that makes
the start of an INI file read as a clean INI file. A wrong key gives wrong numbers without any
error, so the key must be clearly better than all the others, or the archive is refused.
"""

import struct

MAX_ENTRIES = 1000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
NEW_FORMAT = -1111
KEY_FILES = 6
MAX_ODD_SHARE = 0.004
MIN_RATIO = 3
MIN_GAP = 40

# The bytes that an INI file does not use. A key that is almost right gives text with a few wrong
# letters, and about one wrong byte in six lands in this set, so the wrong keys show thousands of
# them in a whole archive and the right key shows almost none.
ODD = bytes(set(range(256)) - set(range(32, 127)) - {9, 10, 13} | set(b"<>@^`|{}~!$" + bytes([92])))


class AcdError(Exception):
    pass


def _wrap(value: int) -> int:
    """A signed 32-bit integer, as the game's own code does."""
    return (value + 0x80000000) % 0x100000000 - 0x80000000


def _divide(left: int, right: int) -> int:
    """A division that rounds toward zero, like C."""
    if right == 0:
        return 0
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


def _remainder(left: int, right: int) -> int:
    return left - _divide(left, right) * right if right else 0


def _key(folder: str, fifth: int) -> bytes:
    """The key of a car folder: 8 numbers joined with "-" (that text is the key)."""
    n = [ord(c) for c in folder]
    size = len(n)
    parts = [_wrap(sum(n))]

    value = 0
    for i in range(0, size - 1, 2):
        value = _wrap(_wrap(value * n[i]) - n[i + 1])
    parts.append(value)

    value = 0
    for i in range(1, size - 3, 3):
        value = _wrap(value * n[i])
        value = _divide(value, n[i + 1] + 0x1B)
        value = _wrap(value - 0x1B - n[i - 1])
    parts.append(value)

    value = 0x1683
    for i in range(1, size):
        value -= n[i]
    parts.append(_wrap(value))

    parts.append(fifth)

    value = 0x65
    for i in range(0, size - 2, 2):
        value -= n[i]
    parts.append(_wrap(value))

    value = 0xAB
    for i in range(0, size - 2, 2):
        value = _remainder(value, n[i])
    parts.append(value)

    value = 0xAB
    for i in range(0, size - 1):
        value = _wrap(_divide(value, n[i]) + n[i + 1])
    parts.append(value)

    return "-".join(str(part & 0xFF) for part in parts).encode()


TABLES = [bytes((byte - shift) & 0xFF for byte in range(256)) for shift in range(256)]


def _decrypt(chunk: bytes, key: bytes) -> bytes:
    """Subtract the key from the bytes. Every byte of the key works on its own stride, and a
    translate table does that stride at C speed."""
    out = bytearray(len(chunk))
    size = len(key)
    for offset in range(size):
        out[offset::size] = chunk[offset::size].translate(TABLES[key[offset]])
    return bytes(out)


def _odd_count(texts: list[bytes], key: bytes) -> int:
    return sum(len(text) - len(_decrypt(text, key).translate(None, ODD)) for text in texts)


def _find_key(folder: str, texts: list[bytes]) -> bytes:
    """The key that gives the cleanest text for the INI files. The folder name is tried as it
    is, then in lower case (a mod can be packed with a different case)."""
    scored = sorted(
        (_odd_count(texts, key), key)
        for name in dict.fromkeys([folder, folder.lower()])
        for key in (_key(name, fifth) for fifth in range(256))
    )
    best, key = scored[0]
    others = [odd for odd, other in scored if other != key]
    total = sum(len(text) for text in texts)
    if best > total * MAX_ODD_SHARE or others[0] < max(best * MIN_RATIO, best + MIN_GAP):
        raise AcdError("unknown_key")
    return key


def read_acd(data: bytes, folder: str) -> dict[str, bytes]:
    """The files of an archive, by name in lower case. Raises AcdError for a broken archive."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise AcdError("too_big")
    position = 0
    chunks: dict[str, bytes] = {}
    try:
        if struct.unpack_from("<i", data, 0)[0] == NEW_FORMAT:
            position = 8
        while position < len(data):
            if len(chunks) >= MAX_ENTRIES:
                raise AcdError("too_many_files")
            (name_length,) = struct.unpack_from("<i", data, position)
            position += 4
            if not 0 < name_length <= 200:
                raise AcdError("bad_name")
            name = data[position : position + name_length].decode("latin-1")
            position += name_length
            (size,) = struct.unpack_from("<i", data, position)
            position += 4
            if not 0 <= size <= MAX_FILE_BYTES or position + size * 4 > len(data):
                raise AcdError("bad_size")
            # Only the first of every 4 bytes is the data.
            chunks[name.lower()] = data[position : position + size * 4 : 4]
            position += size * 4
    except (struct.error, UnicodeDecodeError) as error:
        raise AcdError("broken") from error
    texts = sorted(
        (chunk for name, chunk in chunks.items() if name.endswith(".ini") and len(chunk) >= 300),
        key=len,
        reverse=True,
    )
    if not texts:
        raise AcdError("no_ini_file")
    texts = texts[:KEY_FILES]
    key = _find_key(folder, texts)
    return {name: _decrypt(chunk, key) for name, chunk in chunks.items()}
