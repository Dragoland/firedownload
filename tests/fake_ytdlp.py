"""yt-dlp falso para las pruebas: imita su salida real sin red ni descargas."""

import json
import os
import sys
import time

args = sys.argv[1:]
url = args[-1] if args else ""
delay = float(os.environ.get("FAKE_YTDLP_DELAY", "0.02"))
fail = os.environ.get("FAKE_YTDLP_FAIL") == "1"


def out(line: str) -> None:
    print(line, flush=True)


if os.environ.get("FAKE_YTDLP_NO_JS") == "1" and "--js-runtimes" in args:
    print("yt-dlp: error: no such option: --js-runtimes", file=sys.stderr, flush=True)
    sys.exit(2)

if "--simulate" in args:
    blocked = os.environ.get("FAKE_YTDLP_UNAVAILABLE")
    if blocked and blocked in url:
        out(f"ERROR: [youtube] {blocked}: This video is unavailable")
        sys.exit(1)
    out("[debug] fake yt-dlp -v")
    out("[youtube] aaaaaaaaaaa: Downloading webpage")
    out("[info] aaaaaaaaaaa: Downloading 1 format(s): 18")
    sys.exit(0)

if "--version" in args:
    out("2099.01.01")
    sys.exit(0)

if "-g" in args:
    out("http://127.0.0.1:9/stream.mp4")
    sys.exit(0)

if "-J" in args:
    if url.startswith("ytsearch"):
        out(json.dumps({"entries": [
            {"id": "aaaaaaaaaaa", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "Resultado uno",
             "channel": "Canal", "duration": 61, "thumbnails": [{"url": "http://127.0.0.1:9/a.jpg", "width": 336}]},
            {"id": "bbbbbbbbbbb", "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "title": "Resultado dos",
             "channel": "Canal", "duration": 3700},
        ]}))
    elif "playlist" in url:
        out(json.dumps({"_type": "playlist", "title": "Lista", "entries": [
            {"id": "aaaaaaaaaaa", "title": "Uno"}, {"id": "bbbbbbbbbbb", "title": "Dos"}, {"id": "ccccccccccc", "title": "Tres"},
        ]}))
    else:
        out(json.dumps({
            "id": "aaaaaaaaaaa", "title": "Vídeo falso", "uploader": "Autor", "duration": 125,
            "upload_date": "20240131", "view_count": 1500, "description": "Descripción",
            "thumbnails": [{"url": "http://127.0.0.1:9/t.jpg", "width": 640}],
            "formats": [
                {"vcodec": "avc1", "height": 1080, "acodec": "none"},
                {"vcodec": "avc1", "height": 720, "acodec": "none"},
                {"vcodec": "none", "acodec": "mp4a", "language": "es-US", "format_note": "Spanish"},
                {"vcodec": "none", "acodec": "opus", "language": "en-US", "format_note": "English"},
            ],
            "subtitles": {"es": [{"name": "Spanish"}]},
            "automatic_captions": {"en": [{"name": "English"}]},
        }))
    sys.exit(0)

if os.environ.get("FAKE_YTDLP_EMPTY") == "1":
    sys.exit(0)

if os.environ.get("FAKE_YTDLP_ARCHIVE_SKIP") == "1":
    out("[download] aaaaaaaaaaa: has already been recorded in the archive")
    sys.exit(0)

template = args[args.index("-o") + 1]
folder = os.path.dirname(template)
os.makedirs(folder, exist_ok=True)
final = os.path.join(folder, "Fake Video.mp4")

if "--skip-download" in args:
    out(f"[info] Writing video subtitles to: {final[:-4]}.es.vtt")
    out("[SubtitlesConvertor] Converting subtitles")
    sys.exit(0)

selector = args[args.index("-f") + 1] if "-f" in args else ""
if os.environ.get("FAKE_YTDLP_NOFORMAT") == "1" and ("-S" in args or "height<=" in selector):
    out("ERROR: [youtube] aaaaaaaaaaa: Requested format is not available. Use --list-formats for a list of available formats")
    sys.exit(1)
two_streams = "-x" not in args and "+" in selector
items = 2 if "--yes-playlist" in args and "playlist" in url else 1

out("[youtube] aaaaaaaaaaa: Downloading webpage")
for item in range(1, items + 1):
    if items > 1:
        out(f"[download] Downloading item {item} of {items}")
    for stream in (("f137.mp4", "f140.m4a") if two_streams else (None,)):
        path = final if stream is None else f"{final[:-4]}.{stream}"
        out(f"[download] Destination: {path}")
        for pct in (0, 25, 50, 75, 100):
            out(f"[download] {pct:5.1f}% of   10.00MiB at    1.00MiB/s ETA 00:01")
            time.sleep(delay)
            if fail and pct == 50:
                out("ERROR: [youtube] aaaaaaaaaaa: Sign in to confirm you're not a bot")
                sys.exit(1)
    if two_streams:
        out(f'[Merger] Merging formats into "{final}"')
    with open(final, "w", encoding="utf-8") as handle:
        handle.write("fake")
    if "-x" in args and "--audio-format" in args:
        with open(final[:-4] + ".mp3", "w", encoding="utf-8") as handle:
            handle.write("fake")
sys.exit(0)
