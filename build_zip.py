"""Genera firedownload-<versión>.zip con todos los archivos del proyecto."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from firedownload import __version__  # noqa: E402

NAME = f"firedownload-{__version__}"
EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", "venv", "build", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def collect() -> list[Path]:
    files = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or EXCLUDED_DIRS.intersection(rel.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> int:
    target = ROOT / f"{NAME}.zip"
    files = collect()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f"{NAME}/{path.relative_to(ROOT).as_posix()}")
    print(f"Creado {target} ({len(files)} archivos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
