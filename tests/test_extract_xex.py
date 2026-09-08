from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_xex.py"
SCRIPTS = SCRIPT.parent
sys.path.insert(0, str(SCRIPTS))
import xdvdfs

SPEC = importlib.util.spec_from_file_location("extract_xex", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
extract_xex = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extract_xex
SPEC.loader.exec_module(extract_xex)


def make_iso(path: Path, game_offset: int = 0x20600) -> bytes:
    root_sector = 40
    file_sector = 50
    payload = b"XEX2" + bytes(range(64))
    name = b"default.xex"
    entry = struct.pack(
        "<HHIIBB", 0, 0, file_sector, len(payload), 0, len(name)
    ) + name

    size = game_offset + (file_sector + 1) * xdvdfs.SECTOR_SIZE
    image = bytearray(size)
    descriptor = game_offset + xdvdfs.VOLUME_DESCRIPTOR_SECTOR * xdvdfs.SECTOR_SIZE
    image[descriptor : descriptor + len(xdvdfs.XDVDFS_MAGIC)] = xdvdfs.XDVDFS_MAGIC
    struct.pack_into(
        "<II",
        image,
        descriptor + len(xdvdfs.XDVDFS_MAGIC),
        root_sector,
        len(entry),
    )
    root_offset = game_offset + root_sector * xdvdfs.SECTOR_SIZE
    image[root_offset : root_offset + len(entry)] = entry
    file_offset = game_offset + file_sector * xdvdfs.SECTOR_SIZE
    image[file_offset : file_offset + len(payload)] = payload
    path.write_bytes(image)
    return payload


def make_multi_file_iso(path: Path, game_offset: int = 0x20600) -> dict[str, bytes]:
    root_sector = 40
    first_sector = 50
    second_sector = 51
    payloads = {
        "default.xex": b"XEX2" + bytes(range(32)),
        "xarchive_audlo.rpf": b"audio archive payload",
    }

    first_name = b"default.xex"
    first = struct.pack(
        "<HHIIBB", 0, 0, first_sector, len(payloads["default.xex"]), 0, len(first_name)
    ) + first_name
    first += bytes((-len(first)) % 4)
    second_offset = len(first)
    second_name = b"xarchive_audlo.rpf"
    second = struct.pack(
        "<HHIIBB",
        0,
        0,
        second_sector,
        len(payloads["xarchive_audlo.rpf"]),
        0,
        len(second_name),
    ) + second_name
    first = bytearray(first)
    struct.pack_into("<H", first, 2, second_offset // 4)
    directory = bytes(first) + second

    size = game_offset + (second_sector + 1) * xdvdfs.SECTOR_SIZE
    image = bytearray(size)
    descriptor = game_offset + xdvdfs.VOLUME_DESCRIPTOR_SECTOR * xdvdfs.SECTOR_SIZE
    image[descriptor : descriptor + len(xdvdfs.XDVDFS_MAGIC)] = xdvdfs.XDVDFS_MAGIC
    struct.pack_into(
        "<II",
        image,
        descriptor + len(xdvdfs.XDVDFS_MAGIC),
        root_sector,
        len(directory),
    )
    root_offset = game_offset + root_sector * xdvdfs.SECTOR_SIZE
    image[root_offset : root_offset + len(directory)] = directory
    for sector, payload in (
        (first_sector, payloads["default.xex"]),
        (second_sector, payloads["xarchive_audlo.rpf"]),
    ):
        offset = game_offset + sector * xdvdfs.SECTOR_SIZE
        image[offset : offset + len(payload)] = payload
    path.write_bytes(image)
    return payloads


class XboxIsoTest(unittest.TestCase):
    def test_extracts_default_xex_and_hashes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso_path = root / "game.iso"
            output = root / "game" / "default.xex"
            payload = make_iso(iso_path)

            with xdvdfs.XboxIso(iso_path) as iso:
                entry = iso.find_file("DEFAULT.XEX")
                digest = iso.extract_xex(entry, output)

            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(
                digest,
                "9791945ccb23070662bf5e51457114417dc7784f84d3032107bc6e2ec9b32c33",
            )

    def test_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso_path = root / "game.iso"
            output = root / "default.xex"
            make_iso(iso_path)
            output.write_bytes(b"keep")

            with xdvdfs.XboxIso(iso_path) as iso:
                with self.assertRaises(FileExistsError):
                    iso.extract_xex(iso.find_file("default.xex"), output)

            self.assertEqual(output.read_bytes(), b"keep")

    def test_rejects_non_xdvdfs_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso_path = Path(temporary) / "not-xbox.iso"
            iso_path.write_bytes(b"not an xbox iso")
            with self.assertRaises(xdvdfs.IsoFormatError):
                with xdvdfs.XboxIso(iso_path):
                    pass

    def test_extracts_complete_tree_and_skips_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            iso_path = root / "game.iso"
            output = root / "game"
            payloads = make_multi_file_iso(iso_path)
            output.mkdir()
            (output / "default.xex").write_bytes(b"existing")

            with xdvdfs.XboxIso(iso_path) as iso:
                written, skipped, written_bytes = iso.extract_tree(
                    output, skip_existing=True
                )

            self.assertEqual((written, skipped), (1, 1))
            self.assertEqual(written_bytes, len(payloads["xarchive_audlo.rpf"]))
            self.assertEqual((output / "default.xex").read_bytes(), b"existing")
            self.assertEqual(
                (output / "xarchive_audlo.rpf").read_bytes(),
                payloads["xarchive_audlo.rpf"],
            )


if __name__ == "__main__":
    unittest.main()
