"""Instalador de herramientas: verificación SHA-256, extracción segura y cancelación (sin Qt, con servidor local)."""

import functools
import hashlib
import http.server
import io
import sys
import tarfile
import threading
import zipfile

import pytest

from firedownload.core import tools

SUFFIX = ".exe" if sys.platform == "win32" else ""


@pytest.fixture
def server(tmp_path):
    """Sirve tmp_path/www por HTTP en un puerto libre."""
    root = tmp_path / "www"
    root.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


def publish(root, name, data: bytes, checksum=True, bad=False):
    (root / name).write_bytes(data)
    digest = hashlib.sha256(b"otra cosa" if bad else data).hexdigest()
    if checksum:
        (root / "SUMS").write_text(f"{digest}  {name}\n")


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def spec(base, asset, archive="", members=("ffmpeg", "ffprobe")):
    return tools.ToolSpec("test", base + asset, base + "SUMS", asset, archive, members)


def test_install_zip_extracts_only_requested_basenames(server, tmp_path):
    root, base = server
    data = make_zip({
        f"build/bin/ffmpeg{SUFFIX}": b"FF", f"build/bin/ffprobe{SUFFIX}": b"FP",
        "build/doc/readme.txt": b"x", f"../../evil/ffmpeg{SUFFIX}.bak": b"no",
    })
    publish(root, "pkg.zip", data)
    dest = tmp_path / "bin"
    installed = tools.install(spec(base, "pkg.zip", "zip"), dest_dir=dest)
    assert sorted(p.name for p in installed) == [f"ffmpeg{SUFFIX}", f"ffprobe{SUFFIX}"]
    assert (dest / f"ffmpeg{SUFFIX}").read_bytes() == b"FF"
    assert sorted(p.name for p in dest.iterdir()) == [f"ffmpeg{SUFFIX}", f"ffprobe{SUFFIX}"], "sin restos ni rutas externas"
    assert not (tmp_path / "evil").exists()


def test_install_tar_xz(server, tmp_path):
    root, base = server
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
        for name, content in ((f"pkg/bin/ffmpeg{SUFFIX}", b"A"), (f"pkg/bin/ffprobe{SUFFIX}", b"B")):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    publish(root, "pkg.tar.xz", buffer.getvalue())
    installed = tools.install(spec(base, "pkg.tar.xz", "tar.xz"), dest_dir=tmp_path / "bin")
    assert len(installed) == 2


def test_install_single_binary_is_renamed_and_executable(server, tmp_path):
    root, base = server
    publish(root, "yt-dlp_linux", b"#!/bin/sh\necho 1\n")
    result = tools.install(tools.ToolSpec("yt-dlp", base + "yt-dlp_linux", base + "SUMS", "yt-dlp_linux", "", ("yt-dlp",)), dest_dir=tmp_path / "bin")
    assert result[0].name == f"yt-dlp{SUFFIX}"
    if sys.platform != "win32":
        assert result[0].stat().st_mode & 0o111


def test_wrong_checksum_is_rejected_and_nothing_is_installed(server, tmp_path):
    root, base = server
    publish(root, "pkg.zip", make_zip({f"ffmpeg{SUFFIX}": b"x", f"ffprobe{SUFFIX}": b"y"}), bad=True)
    dest = tmp_path / "bin"
    with pytest.raises(tools.ToolError, match="SHA-256"):
        tools.install(spec(base, "pkg.zip", "zip"), dest_dir=dest)
    assert list(dest.iterdir()) == []


def test_missing_checksum_entry_fails_closed(server, tmp_path):
    root, base = server
    publish(root, "pkg.zip", make_zip({f"ffmpeg{SUFFIX}": b"x", f"ffprobe{SUFFIX}": b"y"}))
    (root / "SUMS").write_text(f"{'0' * 64}  otro.zip\n{'1' * 64}  mas.zip\n")
    with pytest.raises(tools.ToolError, match="seguridad"):
        tools.install(spec(base, "pkg.zip", "zip"), dest_dir=tmp_path / "bin")


def test_archive_without_expected_executables(server, tmp_path):
    root, base = server
    publish(root, "pkg.zip", make_zip({"solo/doc.txt": b"x"}))
    with pytest.raises(tools.ToolError, match="no contiene"):
        tools.install(spec(base, "pkg.zip", "zip"), dest_dir=tmp_path / "bin")


def test_download_failure_is_a_tool_error(tmp_path):
    with pytest.raises(tools.ToolError):
        tools.install(tools.ToolSpec("t", "http://127.0.0.1:9/x", "http://127.0.0.1:9/s", "x", "", ("t",)), dest_dir=tmp_path / "bin")


def test_cancel_stops_before_installing(server, tmp_path):
    root, base = server
    publish(root, "yt-dlp_linux", b"x" * 300_000)
    with pytest.raises(tools.ToolCancelled):
        tools.install(
            tools.ToolSpec("yt-dlp", base + "yt-dlp_linux", base + "SUMS", "yt-dlp_linux", "", ("yt-dlp",)),
            dest_dir=tmp_path / "bin",
            cancelled=lambda: True,
        )
    assert list((tmp_path / "bin").iterdir()) == []


def test_progress_is_reported(server, tmp_path):
    root, base = server
    publish(root, "yt-dlp_linux", b"x" * 200_000)
    seen = []
    tools.install(
        tools.ToolSpec("yt-dlp", base + "yt-dlp_linux", base + "SUMS", "yt-dlp_linux", "", ("yt-dlp",)),
        dest_dir=tmp_path / "bin",
        progress=lambda done, total: seen.append((done, total)),
    )
    assert seen and seen[-1] == (200_000, 200_000)


def test_expected_hash_formats():
    digest = "a" * 64
    assert tools.expected_hash(f"{digest}  yt-dlp_linux\n{'b' * 64}  yt-dlp.exe", "yt-dlp_linux") == digest
    assert tools.expected_hash(f"{digest} *pkg.zip", "pkg.zip") == digest
    assert tools.expected_hash(digest + "\n", "cualquiera.zip") == digest
    assert tools.expected_hash(f"{digest}  otro", "pkg.zip") is None


@pytest.mark.parametrize("name, system, machine, asset", [
    ("yt-dlp", "win32", "AMD64", "yt-dlp.exe"),
    ("yt-dlp", "linux", "x86_64", "yt-dlp_linux"),
    ("yt-dlp", "linux", "aarch64", "yt-dlp_linux_aarch64"),
    ("yt-dlp", "darwin", "arm64", "yt-dlp_macos"),
    ("deno", "linux", "x86_64", "deno-x86_64-unknown-linux-gnu.zip"),
    ("deno", "darwin", "aarch64", "deno-aarch64-apple-darwin.zip"),
    ("deno", "win32", "x86_64", "deno-x86_64-pc-windows-msvc.zip"),
    ("ffmpeg", "linux", "x86_64", "ffmpeg-master-latest-linux64-gpl.tar.xz"),
    ("ffmpeg", "win32", "x86_64", "ffmpeg-master-latest-win64-gpl.zip"),
])
def test_spec_per_platform(name, system, machine, asset):
    spec_ = tools.spec_for(name, system, machine)
    assert spec_ is not None and spec_.asset == asset and spec_.url.startswith("https://github.com/")
    assert spec_.url.endswith(asset) and spec_.checksum_url.startswith("https://github.com/")


def test_no_automatic_ffmpeg_on_macos():
    assert tools.spec_for("ffmpeg", "darwin", "arm64") is None
