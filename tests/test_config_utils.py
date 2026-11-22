"""Ajustes, utilidades y persistencia JSON (sin Qt)."""

from firedownload.config import Paths, Settings, lang_list, quality_height, sanitize_options
from firedownload.core import history, utils


def test_settings_sanitize_garbage():
    s = Settings(max_concurrent="abc", retries=99, quality="9p", speed_limit="rm -rf", proxy="x", audio_langs="es, ;ls")
    assert (s.max_concurrent, s.retries, s.quality, s.speed_limit, s.proxy) == (2, 10, "Best", "", "")
    assert s.audio_langs == ["es"]


def test_settings_load_ignores_unknown_keys_and_corrupt_file():
    Paths.ensure()
    Paths.CONFIG_FILE.write_text('{"junk": 1, "retries": 5}')
    assert Settings.load().retries == 5
    Paths.CONFIG_FILE.write_text("{no json")
    assert Settings.load().retries == 3
    assert Paths.CONFIG_FILE.with_suffix(".json.bak").exists()


def test_sanitize_options_blocks_injection():
    options = sanitize_options({"speed_limit": "--exec rm", "playlist_items": "1;2", "retries": 2, "evil": 1})
    assert options["speed_limit"] == "" and "playlist_items" not in options and options["retries"] == 2
    assert "evil" not in options
    assert sanitize_options({"playlist_items": "1-3,5"})["playlist_items"] == "1-3,5"


def test_quality_and_langs():
    assert quality_height("4K") == 2160 and quality_height("720p") == 720 and quality_height("Best") is None
    assert lang_list("es, en,es") == ["es", "en"]


def test_validate_url():
    assert utils.validate_url("https://youtu.be/x.y")
    assert not utils.validate_url("javascript:alert(1)")
    assert not utils.validate_url("https://localhost")
    assert not utils.validate_url("https://a.b/ c")


def test_is_playlist_url():
    assert utils.is_playlist_url("https://www.youtube.com/playlist?list=PL123")
    assert not utils.is_playlist_url("https://www.youtube.com/watch?v=abc&list=PL123")
    assert not utils.is_playlist_url("https://vimeo.com/1")


def test_formatters():
    assert utils.format_duration(90) == "1:30" and utils.format_duration(3700) == "1:01:40"
    assert utils.format_date("20240131") == "2024-01-31"
    assert utils.format_count(1_234_567) == "1.2M"


def test_history_roundtrip_and_corruption():
    history.add({"url": "a", "title": "A"})
    history.add({"url": "b", "title": "B"})
    history.remove_by_url("a")
    assert [e["url"] for e in history.load()] == ["b"]
    Paths.HISTORY_FILE.write_text("[oops")
    assert history.load() == []
    history.clear()
    assert history.load() == []


def test_speed_and_size_helpers():
    assert utils.parse_speed("at    5.20MiB/s ETA") == 5.2 * 1024**2
    assert utils.parse_speed("Unknown B/s") == 0.0 and utils.parse_speed("") == 0.0
    assert utils.parse_speed("2.0MB/s") == 2_000_000
    assert utils.format_size(1536) == "1.5 KiB" and utils.format_size(10) == "10 B"
    assert utils.format_speed(5 * 1024**2) == "5.0 MiB/s"


def test_free_space_uses_nearest_existing_parent(tmp_path):
    assert utils.free_space(tmp_path / "no" / "existe" / "todavia") > 0


def test_window_settings_are_sanitized_and_not_sent_to_downloads():
    s = Settings(window_size=[10, "x"], last_tab=99)
    assert s.window_size == [640, 700] and s.last_tab == 3
    assert Settings(window_size="mal").window_size == [960, 700]
    options = Settings().download_options()
    assert "window_size" not in options and "last_tab" not in options


def test_about_metadata_is_defined():
    import firedownload

    assert firedownload.__version__ and firedownload.__author__ and "@" in firedownload.__contact__
    assert firedownload.__github__ and firedownload.__site_web__


def test_external_url_adds_scheme_only_when_missing():
    assert utils.external_url("github.com/Dragoland/firedownload") == "https://github.com/Dragoland/firedownload"
    assert utils.external_url("bitcriollo.pages.dev") == "https://bitcriollo.pages.dev"
    assert utils.external_url("https://a.b") == "https://a.b"
    assert utils.external_url("mailto:x@y.z") == "mailto:x@y.z"
