"""Minimal, dependency-free XDVDFS reader shared by the extraction tools."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterable


SECTOR_SIZE = 2048
VOLUME_DESCRIPTOR_SECTOR = 32
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
POSSIBLE_GAME_OFFSETS = (
    0x00000000,
    0x0000FB20,
    0x00020600,
    0x02080000,
    0x0FD90000,
)
DIRECTORY_HEADER_SIZE = 14
MAX_DIRECTORY_SIZE = 32 * 1024 * 1024
MAX_DIRECTORY_NODES = 500_000
COPY_CHUNK_SIZE = 4 * 1024 * 1024


class IsoFormatError(RuntimeError):
    """Raised when an image is not a safe, readable XDVDFS game volume."""


@dataclass(frozen=True)
class IsoEntry:
    path: str
    offset: int
    size: int
    attributes: int

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & 0x10)


def parse_game_offset(value: str) -> int:
    parsed = int(value, 0)
    if parsed < 0:
        raise ValueError("offset must be non-negative")
    return parsed


def normalize_member(value: str) -> str:
    value = value.replace("\\", "/")
    if not value or value.startswith("/"):
        raise ValueError("member path must be relative")
    components = value.split("/")
    if any(component in ("", ".", "..") for component in components):
        raise ValueError("member path contains an unsafe component")
    return "/".join(components)


class XboxIso:
    def __init__(self, path: Path, game_offset: int | None = None) -> None:
        self.path = path
        self.requested_game_offset = game_offset
        self.file: BinaryIO | None = None
        self.file_size = 0
        self.game_offset = 0
        self.entries: list[IsoEntry] = []

    def __enter__(self) -> "XboxIso":
        try:
            self.file = self.path.open("rb")
        except OSError as exc:
            raise IsoFormatError(f"could not open ISO: {exc}") from exc
        try:
            self.file.seek(0, os.SEEK_END)
            self.file_size = self.file.tell()
            self.game_offset = self._find_game_offset()
            root_offset, root_size = self._read_root_info()
            self.entries = list(self._walk_directory(root_offset, root_size))
        except Exception:
            self.file.close()
            self.file = None
            raise
        return self

    def __exit__(self, *_: object) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None

    def _read_at(self, offset: int, size: int) -> bytes:
        if self.file is None:
            raise RuntimeError("ISO is not open")
        if offset < 0 or size < 0 or offset > self.file_size - size:
            raise IsoFormatError("ISO contains an out-of-range offset")
        self.file.seek(offset)
        data = self.file.read(size)
        if len(data) != size:
            raise IsoFormatError("unexpected end of ISO")
        return data

    def _find_game_offset(self) -> int:
        candidates = (
            (self.requested_game_offset,)
            if self.requested_game_offset is not None
            else POSSIBLE_GAME_OFFSETS
        )
        for candidate in candidates:
            magic_offset = candidate + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE
            if magic_offset > self.file_size - len(XDVDFS_MAGIC):
                continue
            if self._read_at(magic_offset, len(XDVDFS_MAGIC)) == XDVDFS_MAGIC:
                return candidate
        if self.requested_game_offset is not None:
            raise IsoFormatError(
                f"XDVDFS signature not found at game offset 0x{self.requested_game_offset:X}"
            )
        raise IsoFormatError("not a recognized Xbox 360 XDVDFS game ISO")

    def _read_root_info(self) -> tuple[int, int]:
        descriptor_offset = self.game_offset + VOLUME_DESCRIPTOR_SECTOR * SECTOR_SIZE
        root_sector, root_size = struct.unpack(
            "<II", self._read_at(descriptor_offset + len(XDVDFS_MAGIC), 8)
        )
        if root_size < DIRECTORY_HEADER_SIZE or root_size > MAX_DIRECTORY_SIZE:
            raise IsoFormatError("invalid XDVDFS root directory size")
        root_offset = self.game_offset + root_sector * SECTOR_SIZE
        if root_offset > self.file_size - root_size:
            raise IsoFormatError("XDVDFS root directory lies outside the ISO")
        return root_offset, root_size

    @staticmethod
    def _validate_name(name_bytes: bytes) -> str:
        try:
            name = name_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise IsoFormatError("XDVDFS entry has a non-ASCII name") from exc
        if (
            name in ("", ".", "..")
            or "/" in name
            or "\\" in name
            or any(ord(character) < 0x20 for character in name)
        ):
            raise IsoFormatError("XDVDFS entry has an unsafe name")
        return name

    def _walk_directory(self, root_offset: int, root_size: int) -> Iterable[IsoEntry]:
        pending: list[tuple[int, int, int, str]] = [(root_offset, root_size, 0, "")]
        visited: set[tuple[int, int]] = set()
        paths: set[str] = set()

        while pending:
            directory_offset, directory_size, node_offset, prefix = pending.pop()
            node_key = (directory_offset, node_offset)
            if node_key in visited:
                raise IsoFormatError("XDVDFS directory tree contains a cycle")
            visited.add(node_key)
            if len(visited) > MAX_DIRECTORY_NODES:
                raise IsoFormatError("XDVDFS directory tree is unexpectedly large")
            if (
                node_offset < 0
                or node_offset % 4
                or node_offset > directory_size - DIRECTORY_HEADER_SIZE
            ):
                raise IsoFormatError("XDVDFS directory entry offset is invalid")

            entry_offset = directory_offset + node_offset
            header = self._read_at(entry_offset, DIRECTORY_HEADER_SIZE)
            left, right, sector, length, attributes, name_length = struct.unpack(
                "<HHIIBB", header
            )
            if name_length == 0 or name_length > 240:
                raise IsoFormatError("XDVDFS directory entry name length is invalid")
            if node_offset + DIRECTORY_HEADER_SIZE + name_length > directory_size:
                raise IsoFormatError("XDVDFS directory entry exceeds its table")

            name = self._validate_name(
                self._read_at(entry_offset + DIRECTORY_HEADER_SIZE, name_length)
            )
            full_path = f"{prefix}/{name}" if prefix else name
            folded_path = full_path.casefold()
            if folded_path in paths:
                raise IsoFormatError(f"duplicate XDVDFS path: {full_path}")
            paths.add(folded_path)

            for child in (left, right):
                if child:
                    child_offset = child * 4
                    if child_offset > directory_size - DIRECTORY_HEADER_SIZE:
                        raise IsoFormatError("XDVDFS child entry offset is invalid")
                    pending.append((directory_offset, directory_size, child_offset, prefix))

            data_offset = self.game_offset + sector * SECTOR_SIZE
            if data_offset > self.file_size - length:
                raise IsoFormatError(f"XDVDFS entry lies outside the ISO: {full_path}")

            entry = IsoEntry(full_path, data_offset, length, attributes)
            yield entry
            if entry.is_directory and length:
                if length < DIRECTORY_HEADER_SIZE or length > MAX_DIRECTORY_SIZE:
                    raise IsoFormatError(f"invalid directory size: {full_path}")
                pending.append((data_offset, length, 0, full_path))

    def find_file(self, member: str) -> IsoEntry:
        wanted = normalize_member(member).casefold()
        for entry in self.entries:
            if not entry.is_directory and entry.path.casefold() == wanted:
                return entry
        raise IsoFormatError(f"ISO does not contain {member}")

    def copy_file(
        self,
        entry: IsoEntry,
        output: Path,
        *,
        force: bool = False,
        require_xex: bool = False,
    ) -> str:
        if self.file is None:
            raise RuntimeError("ISO is not open")
        if entry.is_directory:
            raise IsoFormatError(f"cannot extract directory as a file: {entry.path}")
        if require_xex and (entry.size < 4 or self._read_at(entry.offset, 4) != b"XEX2"):
            raise IsoFormatError(f"{entry.path} does not have an XEX2 header")
        if output.exists() and not force:
            raise FileExistsError(f"output already exists: {output} (use --force to replace it)")

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{output.name}.",
                suffix=".tmp",
                dir=output.parent,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                remaining = entry.size
                read_offset = entry.offset
                while remaining:
                    chunk_size = min(remaining, COPY_CHUNK_SIZE)
                    chunk = self._read_at(read_offset, chunk_size)
                    destination.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                    read_offset += len(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary_path, output)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
        return digest.hexdigest()

    def extract_xex(self, entry: IsoEntry, output: Path, force: bool = False) -> str:
        return self.copy_file(entry, output, force=force, require_xex=True)

    @staticmethod
    def _safe_output_path(output_root: Path, member: str) -> Path:
        root = output_root.resolve()
        output = output_root.joinpath(*member.split("/"))
        resolved_output = output.resolve(strict=False)
        try:
            resolved_output.relative_to(root)
        except ValueError as exc:
            raise IsoFormatError(f"entry would escape output directory: {member}") from exc
        return output

    def extract_tree(
        self,
        output_root: Path,
        *,
        force: bool = False,
        skip_existing: bool = False,
        on_entry: Callable[[IsoEntry, Path, bool], None] | None = None,
    ) -> tuple[int, int, int]:
        if force and skip_existing:
            raise ValueError("force and skip_existing cannot be used together")
        if output_root.exists() and not output_root.is_dir():
            raise FileExistsError(f"output root is not a directory: {output_root}")

        output_root.mkdir(parents=True, exist_ok=True)
        directories = sorted(
            (entry for entry in self.entries if entry.is_directory),
            key=lambda entry: entry.path.casefold(),
        )
        files = sorted(
            (entry for entry in self.entries if not entry.is_directory),
            key=lambda entry: entry.path.casefold(),
        )

        for entry in directories:
            directory = self._safe_output_path(output_root, entry.path)
            if directory.exists() and not directory.is_dir():
                raise FileExistsError(f"directory path is occupied by a file: {directory}")
            directory.mkdir(parents=True, exist_ok=True)

        work: list[tuple[IsoEntry, Path, bool]] = []
        required_bytes = 0
        for entry in files:
            output = self._safe_output_path(output_root, entry.path)
            if output.exists():
                if output.is_dir():
                    raise FileExistsError(f"file path is occupied by a directory: {output}")
                if skip_existing:
                    work.append((entry, output, True))
                    continue
                if not force:
                    raise FileExistsError(
                        f"output already exists: {output} "
                        "(use --skip-existing or --force)"
                    )
            work.append((entry, output, False))
            required_bytes += entry.size

        available_bytes = shutil.disk_usage(output_root).free
        if required_bytes > available_bytes:
            raise OSError(
                f"not enough free space: need {required_bytes} bytes, "
                f"have {available_bytes} bytes"
            )

        written = 0
        skipped = 0
        written_bytes = 0
        for entry, output, already_exists in work:
            if on_entry is not None:
                on_entry(entry, output, already_exists)
            if already_exists:
                skipped += 1
                continue
            self.copy_file(entry, output, force=force)
            written += 1
            written_bytes += entry.size
        return written, skipped, written_bytes
