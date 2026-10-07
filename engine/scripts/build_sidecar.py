"""Build the engine as a one-file executable and hand it to Tauri as the sidecar.

Tauri looks for ``binaries/mekiki-engine-<target-triple>[.exe]`` next to ``tauri.conf.json``.
Run from ``engine/``::

    uv sync --group bundle
    uv run python scripts/build_sidecar.py [--target <triple>]
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
BUILD_DIR = ENGINE_DIR / "build"
BINARIES_DIR = ENGINE_DIR.parent / "desktop" / "src-tauri" / "binaries"
NAME = "mekiki-engine"

# Used when rustc is not on the PATH, e.g. on a machine that only builds the engine.
FALLBACK_TRIPLES = {
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
}


def host_triple() -> str:
    """The Rust target triple Tauri will build for, which names the sidecar binary."""
    try:
        output = subprocess.run(["rustc", "-vV"], check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        key = (platform.system(), platform.machine())
        if key not in FALLBACK_TRIPLES:
            sys.exit(f"Unknown platform {key}: pass --target explicitly.")
        return FALLBACK_TRIPLES[key]
    return next(
        line.split(":", 1)[1].strip() for line in output.splitlines() if line.startswith("host:")
    )


def build() -> Path:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--noconfirm",
            "--clean",
            "--name",
            NAME,
            "--distpath",
            str(BUILD_DIR / "dist"),
            "--workpath",
            str(BUILD_DIR / "work"),
            "--specpath",
            str(BUILD_DIR),
            # uvicorn picks its protocol and loop implementations by import string.
            "--collect-submodules",
            "uvicorn",
            "--hidden-import",
            "sqlalchemy.dialects.sqlite",
            str(ENGINE_DIR / "mekiki_engine" / "__main__.py"),
        ],
        check=True,
        cwd=ENGINE_DIR,
    )
    suffix = ".exe" if platform.system() == "Windows" else ""
    return BUILD_DIR / "dist" / f"{NAME}{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", help="Rust target triple (default: the host's)")
    args = parser.parse_args()

    triple = args.target or host_triple()
    executable = build()
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    destination = BINARIES_DIR / f"{NAME}-{triple}{executable.suffix}"
    shutil.copy2(executable, destination)
    print(f"Sidecar ready: {destination}")


if __name__ == "__main__":
    main()
