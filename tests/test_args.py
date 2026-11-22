"""Construcción de argumentos de yt-dlp (sin Qt)."""

import pytest

from firedownload.config import Settings
from firedownload.core import ytdlp

URL = "https://www.youtube.com/watch?v=aaaaaaaaaaa"


@pytest.fixture(autouse=True)
def no_js(monkeypatch):
    monkeypatch.setattr(ytdlp, "find_js_runtime", lambda: None)


def build(tmp_path, ffmpeg=True, **kwargs):
    options = Settings(download_path=str(tmp_path), **kwargs).download_options()
    return ytdlp.build_args(URL, options, ffmpeg=ffmpeg)


def test_quality_is_translated_not_passed_raw(tmp_path):
    args = build(tmp_path, quality="720p")
    assert "720p" not in args
    assert "bv*[height<=720]+ba/b[height<=720]" in args


def test_url_goes_after_double_dash(tmp_path):
    assert build(tmp_path)[-2:] == ["--", URL]


def test_mp4_prefers_h264_and_m4a(tmp_path):
    args = build(tmp_path, video_format="mp4")
    assert args[args.index("-S") + 1] == "res,vcodec:h264,acodec:m4a"


def test_mkv_has_no_sort(tmp_path):
    assert "-S" not in build(tmp_path, video_format="mkv")


def test_several_audio_tracks_force_mkv(tmp_path):
    args = build(tmp_path, audio_langs=["es-US", "en-US"])
    assert args[args.index("--merge-output-format") + 1] == "mkv"
    assert "--audio-multistreams" in args
    assert "+ba[language^=es-US]+ba[language^=en-US]" in args[args.index("-f") + 1]


def test_audio_only(tmp_path):
    args = build(tmp_path, audio_only=True, audio_format="mp3", audio_langs=["es"])
    assert args[args.index("-f") + 1] == "ba[language^=es]/ba/b"
    assert ["-x", "--audio-format", "mp3", "--audio-quality", "0"] == args[args.index("-x"):args.index("-x") + 5]


def test_subtitles_embed_is_downgraded_without_ffmpeg(tmp_path):
    args = build(tmp_path, ffmpeg=False, subs_mode="embed", subs_langs=["es"])
    assert "--embed-subs" not in args and "--convert-subs" not in args
    assert "--write-subs" in args


def test_subtitles_only_skips_download(tmp_path):
    args = build(tmp_path, subs_mode="only", subs_langs=["es", "en"])
    assert "--skip-download" in args and "-f" not in args
    assert args[args.index("--sub-langs") + 1] == "es,en"


def test_no_subtitle_langs_means_no_subtitles(tmp_path):
    assert "--write-subs" not in build(tmp_path, subs_mode="files", subs_langs=[])


def test_thumbnail_not_embedded_in_webm(tmp_path):
    assert "--embed-thumbnail" not in build(tmp_path, video_format="webm", embed_thumbnail=True)
    assert "--embed-thumbnail" in build(tmp_path, video_format="mp4", embed_thumbnail=True)


def test_playlist_items_are_validated(tmp_path):
    options = Settings(download_path=str(tmp_path), download_playlist=True).download_options()
    options["playlist_items"] = "1-3,5"
    assert "--playlist-items" in ytdlp.build_args(URL, options)
    options["playlist_items"] = "1; rm -rf /"
    assert "--playlist-items" not in ytdlp.build_args(URL, options)


def test_download_hardening_flags(tmp_path):
    args = build(tmp_path)
    assert {"--socket-timeout", "--concurrent-fragments", "--trim-filenames"} <= set(args)
    assert "--no-colors" not in args


def test_js_runtime_is_passed(monkeypatch, tmp_path):
    monkeypatch.setattr(ytdlp, "find_js_runtime", lambda: ("deno", "/x/deno"))
    monkeypatch.setattr(ytdlp, "find_ytdlp", lambda: ("/usr/bin/yt-dlp",))
    args = build(tmp_path)
    assert args[args.index("--js-runtimes") + 1] == "deno:/x/deno"
    assert "--remote-components" not in args


def test_network_options(tmp_path):
    args = build(tmp_path, speed_limit="2M", proxy="http://h:1", cookies_browser="firefox")
    assert args[args.index("--limit-rate") + 1] == "2M"
    assert args[args.index("--proxy") + 1] == "http://h:1"
    assert args[args.index("--cookies-from-browser") + 1] == "firefox"


def test_format_selector_without_language():
    assert ytdlp.format_selector(None, []) == "bv*+ba/b"


def test_humanize_error():
    assert "anti-bots" in ytdlp.humanize_error("ERROR: Sign in to confirm you're not a bot")
    assert ytdlp.humanize_error("ERROR: algo raro") == "algo raro"


def test_without_ffmpeg_video_is_a_single_file(tmp_path):
    args = build(tmp_path, ffmpeg=False, quality="720p", audio_langs=["es", "en"])
    assert args[args.index("-f") + 1] == "b[height<=720]/b"
    assert "--merge-output-format" not in args and "-S" not in args and "--audio-multistreams" not in args


def test_without_ffmpeg_audio_is_not_converted(tmp_path):
    args = build(tmp_path, ffmpeg=False, audio_only=True, audio_format="mp3")
    assert "-x" not in args and "--audio-format" not in args
    assert args[args.index("-f") + 1] == "ba[ext=m4a]/ba/b"


def test_js_flags_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(ytdlp, "find_js_runtime", lambda: ("deno", "/x/deno"))
    options = Settings(download_path=str(tmp_path)).download_options()
    assert "--js-runtimes" in ytdlp.build_args(URL, options)
    assert "--js-runtimes" not in ytdlp.build_args(URL, options, js=False)
