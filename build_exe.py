#!/usr/bin/env python3
"""Compila FireDownload en un ejecutable para el sistema en el que se ejecuta.

    Windows -> dist/FireDownload/FireDownload.exe   + FireDownload-<versión>-windows-<arq>.zip
    Linux   -> dist/FireDownload/FireDownload       + FireDownload-<versión>-linux-<arq>.tar.gz
    macOS   -> dist/FireDownload.app                + FireDownload-<versión>-macos-<arq>.zip

PyInstaller no compila de forma cruzada: ejecútalo en cada sistema (o usa el flujo de GitHub Actions).

Uso:
    python build_exe.py                 # carpeta con el ejecutable + archivo comprimido
    python build_exe.py --onefile       # un único ejecutable (arranque algo más lento)
    python build_exe.py --with-tools    # incluye yt-dlp, FFmpeg y Deno en tools/ (modo portable)
    python build_exe.py --install-deps  # instala PyInstaller y las dependencias si faltan
    python build_exe.py --dry-run       # muestra lo que haría sin compilar
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from firedownload import __version__  # noqa: E402

APP_NAME = "FireDownload"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def target_system() -> str:
    """«windows», «linux» o «macos» según donde se ejecute."""
    return {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux")


def target_arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("amd64", "x86_64") else machine


def archive_stem() -> str:
    return f"{APP_NAME}-{__version__}-{target_system()}-{target_arch()}"


def _convert_icon(system: str) -> Path | None:
    """Icono para el ejecutable a partir de assets/Logo.png (necesita Pillow en Windows y macOS)."""
    logo = ROOT / "assets" / "Logo.png"
    if not logo.is_file() or system == "linux":
        return None
    try:
        from PIL import Image
    except ImportError:
        print("Aviso: instala Pillow para que el ejecutable lleve el icono del logo.")
        return None
    BUILD.mkdir(exist_ok=True)
    target = BUILD / ("Logo.ico" if system == "windows" else "Logo.icns")
    Image.open(logo).convert("RGBA").save(target)
    return target


def pyinstaller_args(*, onefile: bool, system: str | None = None) -> list[str]:
    """Argumentos de PyInstaller para este sistema."""
    system = system or target_system()
    separator = ";" if system == "windows" else ":"
    args = [
        str(ROOT / "main.py"),
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile" if onefile else "--onedir",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--add-data", f"{ROOT / 'assets'}{separator}assets",
        "--add-data", f"{ROOT / 'LICENSE'}{separator}.",
        "--exclude-module", "tkinter",
    ]
    icon = _convert_icon(system)
    if icon is not None:
        args += ["--icon", str(icon)]
    if system == "macos":
        args += ["--osx-bundle-identifier", "io.github.dragoland.firedownload"]
    return args


def output_path(*, onefile: bool, system: str | None = None) -> Path:
    """Dónde deja PyInstaller el resultado."""
    system = system or target_system()
    if system == "macos":
        return DIST / f"{APP_NAME}.app"
    if onefile:
        return DIST / (f"{APP_NAME}.exe" if system == "windows" else APP_NAME)
    return DIST / APP_NAME


def write_linux_launchers(folder: Path) -> None:
    """Archivo .desktop e install.sh para integrar la carpeta en el menú de aplicaciones."""
    (folder / f"{APP_NAME}.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=FireDownload\n"
        "Comment=Gestor de descargas de vídeo y audio\nExec=firedownload %U\nIcon=firedownload\n"
        "Terminal=false\nCategories=Network;AudioVideo;\n",
        encoding="utf-8",
    )
    script = folder / "install.sh"
    script.write_text(
        "#!/bin/sh\n"
        "# Instala FireDownload para el usuario actual (sin permisos de administrador).\n"
        "set -e\n"
        'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
        'DEST="$HOME/.local/share/FireDownload"\n'
        'mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"\n'
        'cp -r "$HERE"/. "$DEST"/\n'
        'ln -sf "$DEST/FireDownload" "$HOME/.local/bin/firedownload"\n'
        'ICON="$DEST/_internal/assets/Logo.png"\n'
        '[ -f "$ICON" ] && cp "$ICON" "$HOME/.local/share/icons/firedownload.png"\n'
        'cp "$DEST/FireDownload.desktop" "$HOME/.local/share/applications/firedownload.desktop"\n'
        'echo "FireDownload instalado. Búscalo en tu menú de aplicaciones o ejecuta: firedownload"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)


def bundle_tools(folder: Path) -> None:
    """Descarga yt-dlp, FFmpeg y Deno a `tools/` junto al ejecutable (modo portable)."""
    from firedownload.core import tools

    target = folder / "tools"
    for name in tools.TOOL_NAMES:
        spec = tools.spec_for(name)
        if spec is None:
            print(f"- {name}: sin descarga oficial para este sistema ({tools.unsupported_reason(name)})")
            continue
        print(f"- Descargando {name}…")
        tools.install(spec, dest_dir=target)
    print("Aviso: FFmpeg se distribuye bajo GPL; si publicas este paquete, cumple sus condiciones de licencia.")


def make_archive(source: Path, stem: str, system: str | None = None) -> Path:
    """Comprime el resultado: .tar.gz en Linux, .zip en Windows y macOS (conserva permisos)."""
    system = system or target_system()
    DIST.mkdir(exist_ok=True)
    if system == "linux":
        target = DIST / f"{stem}.tar.gz"
        with tarfile.open(target, "w:gz") as archive:
            archive.add(source, arcname=source.name)
        return target
    target = DIST / f"{stem}.zip"
    if system == "macos" and shutil.which("ditto"):
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(source), str(target)], check=True)
        return target
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        if source.is_dir():
            for path in sorted(source.rglob("*")):
                archive.write(path, Path(source.name) / path.relative_to(source))
        else:
            archive.write(source, source.name)
    return target


def ensure_pyinstaller(install: bool) -> bool:
    if importlib.util.find_spec("PyInstaller"):
        return True
    if not install:
        print("Falta PyInstaller. Instálalo con:  pip install pyinstaller   (o ejecuta con --install-deps)")
        return False
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "pyinstaller", "pillow"], check=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compila FireDownload para este sistema.")
    parser.add_argument("--onefile", action="store_true", help="un único ejecutable en lugar de una carpeta")
    parser.add_argument("--with-tools", action="store_true", help="incluye yt-dlp, FFmpeg y Deno en tools/")
    parser.add_argument("--no-archive", action="store_true", help="no crear el .zip/.tar.gz")
    parser.add_argument("--install-deps", action="store_true", help="instala PyInstaller y dependencias si faltan")
    parser.add_argument("--dry-run", action="store_true", help="muestra el plan sin compilar")
    options = parser.parse_args(argv)

    system = target_system()
    print(f"FireDownload {__version__} · sistema: {system} {target_arch()} · modo: {'un archivo' if options.onefile else 'carpeta'}")
    args = pyinstaller_args(onefile=options.onefile, system=system)
    result = output_path(onefile=options.onefile, system=system)
    if options.dry_run:
        print("PyInstaller " + " ".join(args))
        print(f"Resultado: {result}")
        print(f"Archivo: dist/{archive_stem()}" + (".tar.gz" if system == "linux" else ".zip"))
        return 0

    if not ensure_pyinstaller(options.install_deps):
        return 1
    import PyInstaller.__main__ as pyinstaller

    pyinstaller.run(args)
    if not result.exists():
        print("La compilación no generó el resultado esperado.")
        return 1

    if result.is_dir() and system != "macos":
        for extra in ("LICENSE", "README.md"):
            shutil.copy2(ROOT / extra, result / extra)
        if system == "linux":
            write_linux_launchers(result)
    if options.with_tools:
        bundle_tools(result if result.is_dir() and system != "macos" else result.parent)
    if not options.no_archive:
        print(f"Archivo: {make_archive(result, archive_stem(), system)}")
    print(f"Listo: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
