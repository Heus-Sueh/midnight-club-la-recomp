#!/usr/bin/env python3
"""Install the pinned, local Ghidra/XEXLoaderWV/JDK toolchain.

The install is intentionally repository-local and gitignored. Every remote
archive is pinned by URL and SHA-256 so an upstream replacement fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


GHIDRA_VERSION = "12.0.4"
GHIDRA_DIRECTORY = "ghidra_12.0.4_PUBLIC"
GHIDRA_ASSET = {
    "name": "ghidra_12.0.4_PUBLIC_20260303.zip",
    "url": "https://github.com/NationalSecurityAgency/ghidra/releases/download/"
    "Ghidra_12.0.4_build/ghidra_12.0.4_PUBLIC_20260303.zip",
    "sha256": "c3b458661d69e26e203d739c0c82d143cc8a4a29d9e571f099c2cf4bda62a120",
}
XEX_LOADER_VERSION = "13.0.0"
XEX_LOADER_ASSET = {
    "name": "ghidra_12.0.4_PUBLIC_20260325_XEXLoaderWV.zip",
    "url": "https://github.com/SaveEditors/XEXLoaderWV/releases/download/13.0.0/"
    "ghidra_12.0.4_PUBLIC_20260325_XEXLoaderWV.zip",
    "sha256": "498b9c2a2430585cc49a13db33603b6a46cfe84b157985f9be2c4360f917fa5a",
}
JDK_ASSETS = {
    "linux": {
        "name": "OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz",
        "url": "https://github.com/adoptium/temurin21-binaries/releases/download/"
        "jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz",
        "sha256": "ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94",
    },
    "windows": {
        "name": "OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip",
        "url": "https://github.com/adoptium/temurin21-binaries/releases/download/"
        "jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip",
        "sha256": "f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e",
    },
}


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(asset: dict[str, str], cache: Path) -> Path:
    destination = cache / asset["name"]
    if destination.exists() and sha256(destination) == asset["sha256"]:
        print(f"Using verified cache: {destination}")
        return destination
    if destination.exists():
        destination.unlink()

    cache.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading {asset['name']}...")
    try:
        with urllib.request.urlopen(asset["url"]) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual = sha256(temporary)
        if actual != asset["sha256"]:
            raise RuntimeError(
                f"SHA-256 mismatch for {asset['name']}: expected "
                f"{asset['sha256']}, got {actual}"
            )
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def safe_path(root: Path, member_name: str) -> Path:
    candidate = (root / member_name).resolve()
    if root.resolve() not in (candidate, *candidate.parents):
        raise RuntimeError(f"archive entry escapes destination: {member_name}")
    return candidate


def extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            safe_path(destination, member.filename)
        source.extractall(destination)


def extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            member_path = safe_path(destination, member.name)
            if member.issym() or member.islnk():
                link_target = (member_path.parent / member.linkname).resolve()
                root = destination.resolve()
                if root not in (link_target, *link_target.parents):
                    raise RuntimeError(
                        f"archive link escapes destination: {member.name} -> {member.linkname}"
                    )
        source.extractall(destination, filter="data")


def first_directory(root: Path) -> Path:
    directories = [path for path in root.iterdir() if path.is_dir()]
    if len(directories) != 1:
        raise RuntimeError(f"expected one top-level directory in {root}")
    return directories[0]


def install_archive(archive: Path, destination: Path) -> Path:
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary_name:
        temporary = Path(temporary_name)
        if archive.name.endswith(".tar.gz"):
            extract_tar(archive, temporary)
        else:
            extract_zip(archive, temporary)
        extracted = first_directory(temporary)
        extracted.replace(destination)
    return destination


def platform_name() -> str:
    name = platform.system().lower()
    if name not in JDK_ASSETS:
        raise RuntimeError(f"unsupported host OS: {platform.system()}")
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError(f"unsupported architecture: {platform.machine()}")
    return name


def find_java_home(tool_root: Path) -> Path | None:
    executable = "java.exe" if os.name == "nt" else "java"
    for candidate in sorted(tool_root.glob("jdk-21*")):
        if (candidate / "bin" / executable).is_file():
            return candidate
    return None


def verify(ghidra_home: Path, java_home: Path) -> None:
    java = java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    headless = ghidra_home / "support" / (
        "analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless"
    )
    loader = ghidra_home / "Ghidra" / "Extensions" / "XEXLoaderWV" / "lib" / "XEXLoaderWV.jar"
    missing = [path for path in (java, headless, loader) if not path.is_file()]
    if missing:
        raise RuntimeError("incomplete Ghidra toolchain: " + ", ".join(map(str, missing)))
    if os.name != "nt":
        # Python's ZIP extractor does not restore Unix executable mode bits.
        # Restore scripts plus ELF tools used by analyzers and the decompiler.
        for launcher in (headless, ghidra_home / "support" / "launch.sh", ghidra_home / "ghidraRun"):
            if not launcher.is_file():
                raise RuntimeError(f"missing Ghidra launcher: {launcher}")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        for candidate in ghidra_home.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                is_elf = candidate.open("rb").read(4) == b"\x7fELF"
            except OSError:
                continue
            if is_elf or candidate.suffix == ".sh":
                candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only", action="store_true", help="validate an existing local install"
    )
    args = parser.parse_args()

    root = repository_root()
    tool_root = root / ".tools" / "ghidra"
    cache = tool_root / "downloads"
    ghidra_home = tool_root / GHIDRA_DIRECTORY
    java_home = find_java_home(tool_root)

    if not args.verify_only:
        host = platform_name()
        java_archive = download(JDK_ASSETS[host], cache)
        java_home = install_archive(java_archive, tool_root / "jdk-21.0.12.1+1")
        ghidra_archive = download(GHIDRA_ASSET, cache)
        install_archive(ghidra_archive, ghidra_home)
        loader_archive = download(XEX_LOADER_ASSET, cache)
        loader_home = ghidra_home / "Ghidra" / "Extensions" / "XEXLoaderWV"
        install_archive(loader_archive, loader_home)

    if java_home is None:
        raise RuntimeError("portable JDK 21 is not installed; run bootstrap without --verify-only")
    verify(ghidra_home, java_home)
    manifest = {
        "ghidra_version": GHIDRA_VERSION,
        "ghidra_home": str(ghidra_home),
        "java_home": str(java_home),
        "xex_loader_version": XEX_LOADER_VERSION,
    }
    tool_root.mkdir(parents=True, exist_ok=True)
    (tool_root / "toolchain.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, urllib.error.URLError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
