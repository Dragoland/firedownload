"""Parseo de metadatos y búsquedas (sin Qt)."""

import json

import pytest

from firedownload.core import info


def test_parse_video():
    data = {
        "title": "T", "uploader": "U", "duration": 125, "upload_date": "20240131",
        "thumbnails": [{"url": "small", "width": 168}, {"url": "big", "width": 720}],
        "chapters": [{}, {}],
        "formats": [
            {"vcodec": "avc1", "height": 1080, "acodec": "none"},
            {"vcodec": "avc1", "height": 720, "acodec": "none"},
            {"vcodec": "none", "acodec": "mp4a", "language": "es-US", "format_note": "Spanish"},
        ],
        "subtitles": {"es": [{"name": "Spanish"}], "live_chat": [{}]},
        "automatic_captions": {"en": [{"name": "English"}]},
    }
    media = info.parse_info(json.dumps(data), "u")
    assert media.heights == [1080, 720]
    assert media.audio_tracks == [("es-US", "Spanish")]
    assert media.subtitles == [("es", "Spanish")] and media.auto_captions == [("en", "English")]
    assert media.thumbnail == "big" and media.chapters == 2 and not media.is_playlist


def test_parse_playlist_keeps_original_positions():
    raw = json.dumps({"_type": "playlist", "title": "P", "entries": [{"id": "1", "title": "A"}, None, {"id": "3"}]})
    media = info.parse_info(raw, "u")
    assert media.is_playlist and media.playlist_count == 2
    assert media.playlist_entries == [(1, "A"), (3, "3")]


def test_parse_info_rejects_garbage():
    with pytest.raises(ValueError):
        info.parse_info("not json", "u")


def test_parse_search():
    raw = json.dumps({"entries": [
        {"id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk", "title": "A", "channel": "C",
         "duration": 60, "thumbnails": [{"url": "t1", "width": 168}, {"url": "t2", "width": 336}]},
        {"id": "zzz"},
        {"url": "abcdefghijk", "title": "B"},
    ]})
    results = info.parse_search(raw)
    assert [(r.title, r.thumbnail) for r in results] == [("A", "t2"), ("B", "")]
    assert results[1].url == "https://www.youtube.com/watch?v=abcdefghijk"


def test_compress_ranges():
    assert info.compress_ranges([1, 2, 3, 5, 7, 8]) == "1-3,5,7-8"
    assert info.compress_ranges([4]) == "4"
    assert info.compress_ranges([]) == ""


def test_search_args_collapse_whitespace():
    assert info.search_args("ytsearch", " hola   mundo ", 20, {})[-1] == "ytsearch20:hola mundo"
