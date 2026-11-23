"""Funciones de la versión 1.0: argumentos, perfiles, notificaciones, localización de herramientas y build (sin Qt)."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from firedownload.config import Paths, Settings, sanitize_options, sanitize_profile
from firedownload.core import notify, profiles, ytdlp
from firedownload.core import utils as utils_module

URL = "https://www.youtube.com/watch?v=aaaaaaaaaaa"


@pytest.fixture(autouse=True)
def no_js(monkeypatch):
    monkeypatch.setattr(ytdlp, "find_js_runtime", lambda: None)


def build(tmp_path, ffmpeg=True, **kwargs):
    extra = {k: kwargs.pop(k) for k in ("sections",) if k in kwargs}
    options = Settings(download_path=str(tmp_path), **kwargs).download_options()
    options.update(extra)
    return ytdlp.build_args(URL, options, ffmpeg=ffmpeg)


# ---------- argumentos ----------
def test_download_archive_and_overwrite(tmp_path):
    args = build(tmp_path, use_archive=True, overwrite="overwrite")
    assert args[args.index("--download-archive") + 1] == str(Paths.ARCHIVE_FILE)
    assert "--force-overwrites" in args
    plain = build(tmp_path)
    assert "--download-archive" not in plain and "--force-overwrites" not in plain


def test_sponsorblock_modes_need_ffmpeg(tmp_path):
    assert build(tmp_path, sponsorblock="remove")[build(tmp_path, sponsorblock="remove").index("--sponsorblock-remove") + 1] == "sponsor,selfpromo,interaction"
    assert "--sponsorblock-mark" in build(tmp_path, sponsorblock="mark")
    assert "--sponsorblock-remove" not in build(tmp_path, ffmpeg=False, sponsorblock="remove")


def test_sections_are_passed_only_when_valid_and_with_ffmpeg(tmp_path):
    args = build(tmp_path, sections=["*60-150", "*10.5-inf", "rm -rf", "*1-"])
    assert [args[i + 1] for i, a in enumerate(args) if a == "--download-sections"] == ["*60-150", "*10.5-inf"]
    assert "--force-keyframes-at-cuts" in args
    assert "--download-sections" not in build(tmp_path, ffmpeg=False, sections=["*1-2"])


def test_cookies_file_has_priority_over_browser(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    args = build(tmp_path, cookies_file=str(cookies), cookies_browser="firefox")
    assert args[args.index("--cookies") + 1] == str(cookies) and "--cookies-from-browser" not in args
    missing = build(tmp_path, cookies_file=str(tmp_path / "no.txt"), cookies_browser="firefox")
    assert "--cookies" not in missing and "--cookies-from-browser" in missing


def test_fallback_selector_has_no_restrictions(tmp_path):
    options = Settings(download_path=str(tmp_path), quality="720p", audio_langs=["es"]).download_options()
    args = ytdlp.build_args(URL, options, fallback=True)
    assert args[args.index("-f") + 1] == "bv*+ba/b" and "-S" not in args
    assert ytdlp.build_args(URL, options, ffmpeg=False, fallback=True)[ytdlp.build_args(URL, options, ffmpeg=False, fallback=True).index("-f") + 1] == "b"


def test_ffmpeg_location_when_installed_by_the_app(monkeypatch, tmp_path):
    exe = tmp_path / "bin" / "ffmpeg"
    monkeypatch.setattr(ytdlp, "find_tool", lambda name: exe if name == "ffmpeg" else None)
    args = build(tmp_path)
    assert args[args.index("--ffmpeg-location") + 1] == str(exe.parent)


def test_remote_components_are_opt_in(monkeypatch):
    monkeypatch.setattr(ytdlp, "find_js_runtime", lambda: ("deno", "/x/deno"))
    monkeypatch.setattr(ytdlp, "find_ytdlp", lambda: (sys.executable, "-m", "yt_dlp"))
    monkeypatch.setattr(ytdlp.importlib.util, "find_spec", lambda name: None)
    assert "--remote-components" not in ytdlp.js_runtime_args()
    assert ytdlp.js_runtime_args(allow_remote=True)[-2:] == ["--remote-components", "ejs:github"]


# ---------- configuración y perfiles ----------
def test_new_settings_are_sanitized():
    s = Settings(sponsorblock="raro", overwrite="x", profiles="mal", use_archive=1)
    assert (s.sponsorblock, s.overwrite, s.profiles, s.use_archive) == ("off", "skip", {}, True)


def test_profiles_are_validated_and_limited():
    s = Settings(profiles={"Mío": {"quality": "9p", "audio_only": 1, "evil": "x", "subs_langs": "es,;ls"}, "": {"quality": "720p"}})
    assert s.profiles == {"Mío": {"audio_only": True, "quality": "Best", "subs_langs": ["es"]}}
    many = Settings(profiles={f"p{i}": {"quality": "720p"} for i in range(50)})
    assert len(many.profiles) == 20
    assert sanitize_profile("no") == {}


def test_profiles_never_leak_into_download_options():
    options = Settings(profiles={"x": {"quality": "720p"}}, notifications=False).download_options()
    assert "profiles" not in options and "notifications" not in options


def test_builtin_profiles_are_valid_and_custom_ones_cannot_shadow_them():
    for name, values in profiles.BUILTIN_PROFILES.items():
        assert sanitize_profile(values) == dict(sorted(values.items())), name
    s = Settings(profiles={"Música · MP3 con carátula": {"quality": "720p"}, "Propio": {"quality": "480p"}})
    merged = profiles.all_profiles(s)
    assert merged["Música · MP3 con carátula"] == profiles.BUILTIN_PROFILES["Música · MP3 con carátula"]
    assert merged["Propio"]["quality"] == "480p"


def test_profile_snapshot_roundtrip():
    s = Settings(quality="720p", audio_only=True, subs_langs=["es"])
    snap = profiles.snapshot(s)
    assert snap["quality"] == "720p" and snap["audio_only"] is True and snap["subs_langs"] == ["es"]
    assert sanitize_profile(snap) == snap


def test_sanitize_options_keeps_only_valid_sections():
    options = sanitize_options({"sections": ["*1-2", "malo", 5]})
    assert options["sections"] == ["*1-2"]
    assert "sections" not in sanitize_options({"sections": ["x"]})


# ---------- utilidades ----------
def test_parse_timestamp():
    assert utils_module.parse_timestamp("1:02:03") == 3723
    assert utils_module.parse_timestamp("2:30") == 150 and utils_module.parse_timestamp("45") == 45
    assert utils_module.parse_timestamp("  ") is None
    with pytest.raises(ValueError):
        utils_module.parse_timestamp("abc")
    with pytest.raises(ValueError):
        utils_module.parse_timestamp("-5")


def test_ytdlp_outdated_by_date():
    today = date(2026, 11, 23)
    assert utils_module.ytdlp_is_outdated("2026.01.01", today=today)
    assert not utils_module.ytdlp_is_outdated("2026.11.01", today=today)
    assert not utils_module.ytdlp_is_outdated("rara", today=today)


def test_managed_tool_has_priority_and_refresh_clears_cache(monkeypatch, tmp_path):
    suffix = ".exe" if sys.platform == "win32" else ""
    binary = tmp_path / f"yt-dlp{suffix}"
    binary.write_text("x")
    monkeypatch.setattr(utils_module, "tool_dirs", lambda: [tmp_path])
    utils_module.refresh_tools()
    assert utils_module.find_ytdlp() == (str(binary),)
    assert utils_module.find_tool("ffmpeg") is None
    binary.unlink()
    assert utils_module.find_ytdlp() == (str(binary),), "sigue en caché hasta refrescar"
    utils_module.refresh_tools()
    assert utils_module.find_ytdlp() != (str(binary),)


def test_managed_deno_is_the_preferred_js_runtime(monkeypatch, tmp_path):
    suffix = ".exe" if sys.platform == "win32" else ""
    deno = tmp_path / f"deno{suffix}"
    deno.write_text("x")
    monkeypatch.setattr(utils_module, "tool_dirs", lambda: [tmp_path])
    utils_module.refresh_tools()
    assert utils_module.find_js_runtime() == ("deno", str(deno))
    utils_module.refresh_tools()


# ---------- notificaciones ----------
def test_notification_commands():
    argv, env = notify.command_for("Título", "Mensaje", "darwin")
    assert argv[0] == "osascript" and argv[-2:] == ["Título", "Mensaje"] and env == {}
    argv, env = notify.command_for("T", "M", "win32")
    assert "-Command" in argv and env == {"FD_TITLE": "T", "FD_MSG": "M"}
    assert "$env:FD_TITLE" in argv[-1], "el texto viaja por variables de entorno, no dentro del script"


def test_notify_send_on_linux_and_silent_without_it(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda name: "/usr/bin/notify-send")
    argv, _ = notify.command_for("T", "M", "linux")
    assert argv == ["notify-send", "-a", "FireDownload", "--", "T", "M"]
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)
    assert notify.command_for("T", "M", "linux") is None
    called = []
    monkeypatch.setattr(notify.subprocess, "Popen", lambda *a, **k: called.append(a))
    notify.send("T", "M")
    if sys.platform not in ("win32", "darwin"):
        assert not called


# ---------- build_exe.py ----------
@pytest.fixture
def build_exe():
    spec = importlib.util.spec_from_file_location("build_exe", Path(__file__).resolve().parents[1] / "build_exe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_per_platform(build_exe):
    win = build_exe.pyinstaller_args(onefile=False, system="windows")
    assert "--windowed" in win and "--onedir" in win and any(a.endswith(";assets") for a in win)
    linux = build_exe.pyinstaller_args(onefile=True, system="linux")
    assert "--onefile" in linux and any(a.endswith(":assets") for a in linux)
    mac = build_exe.pyinstaller_args(onefile=False, system="macos")
    assert "--osx-bundle-identifier" in mac
    assert build_exe.output_path(onefile=False, system="windows").name == "FireDownload"
    assert build_exe.output_path(onefile=True, system="windows").name == "FireDownload.exe"
    assert build_exe.output_path(onefile=False, system="macos").name == "FireDownload.app"


def test_build_script_archives_and_linux_launchers(build_exe, tmp_path, monkeypatch):
    monkeypatch.setattr(build_exe, "DIST", tmp_path / "dist")
    folder = tmp_path / "FireDownload"
    folder.mkdir()
    (folder / "FireDownload").write_text("bin")
    build_exe.write_linux_launchers(folder)
    assert (folder / "FireDownload.desktop").read_text().startswith("[Desktop Entry]")
    assert "ln -sf" in (folder / "install.sh").read_text()
    tar = build_exe.make_archive(folder, "pkg", "linux")
    zipped = build_exe.make_archive(folder, "pkg", "windows")
    assert tar.name == "pkg.tar.gz" and zipped.name == "pkg.zip" and tar.stat().st_size and zipped.stat().st_size
    import zipfile

    assert "FireDownload/FireDownload" in zipfile.ZipFile(zipped).namelist()


def test_build_script_names_archives_with_version_and_system(build_exe):
    import firedownload

    stem = build_exe.archive_stem()
    assert stem.startswith(f"FireDownload-{firedownload.__version__}-")
    assert build_exe.main(["--dry-run"]) == 0
