#!/usr/bin/env python3
"""Import an owned XEX into local Ghidra and export focused function context."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_ADDRESSES = ("0x82415DC8", "0x82415EE8", "0x8241A630")
SECRET_LOG_PATTERN = re.compile(
    r"(?i)((?:file|session) key\s*=\s*)(?:[0-9a-f]{2}(?:\s+|$))+"
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_address(value: str) -> str:
    try:
        number = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid address: {value}") from error
    if not 0 <= number <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError(f"address is outside the 32-bit guest range: {value}")
    return f"0x{number:08X}"


def main() -> int:
    root = repository_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xex", type=Path, default=root / "game" / "default.xex")
    parser.add_argument(
        "--address", action="append", type=normalized_address,
        help="guest function address; repeat as needed (defaults to current hotspots)",
    )
    parser.add_argument("--analysis-timeout", type=int, default=900, metavar="SECONDS")
    parser.add_argument("--no-analysis", action="store_true", help="reuse prior analysis")
    args = parser.parse_args()

    manifest_path = root / ".tools" / "ghidra" / "toolchain.json"
    if not manifest_path.is_file():
        print("error: run scripts/ghidra/bootstrap.py first", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ghidra_home = Path(manifest["ghidra_home"])
    java_home = Path(manifest["java_home"])
    headless = ghidra_home / "support" / (
        "analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless"
    )

    xex = args.xex.expanduser().resolve()
    if not xex.is_file():
        print(f"error: XEX does not exist: {xex}", file=sys.stderr)
        return 1
    digest = file_sha256(xex)
    project_root = root / ".ghidra" / "projects"
    export_root = root / ".ghidra" / "exports" / digest
    project_root.mkdir(parents=True, exist_ok=True)
    export_root.mkdir(parents=True, exist_ok=True)
    addresses = args.address or list(DEFAULT_ADDRESSES)

    command = [str(headless), str(project_root), f"mcla_{digest[:12]}"]
    if args.no_analysis:
        command.extend(["-process", xex.name, "-noanalysis"])
    else:
        command.extend(["-import", str(xex), "-overwrite"])
    command.extend([
        "-scriptPath", str(root / "scripts" / "ghidra"),
        "-postScript", "ExportFunctionContext.java", str(export_root), *addresses,
        "-analysisTimeoutPerFile", str(args.analysis_timeout),
    ])

    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(java_home)
    environment["PATH"] = str(java_home / "bin") + os.pathsep + environment.get("PATH", "")
    if os.name != "nt":
        # Keep Ghidra's per-user state inside the repository's ignored workspace.
        # This also makes headless use work in restricted build environments.
        for variable, directory in (
            ("XDG_CONFIG_HOME", root / ".ghidra" / "config"),
            ("XDG_CACHE_HOME", root / ".ghidra" / "cache"),
            ("XDG_DATA_HOME", root / ".ghidra" / "data"),
        ):
            directory.mkdir(parents=True, exist_ok=True)
            environment[variable] = str(directory)
    print(f"XEX SHA-256: {digest}")
    print(f"Focused exports: {export_root}")
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(SECRET_LOG_PATTERN.sub(r"\1[REDACTED]\n", line), end="")
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
