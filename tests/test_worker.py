"""DownloadWorker con un yt-dlp falso: progreso, errores, pausa real y cancelación."""

import time

import pytest

pytest.importorskip("PySide6.QtCore")
psutil = pytest.importorskip("psutil")

from firedownload.config import Settings  # noqa: E402
from firedownload.core.worker import DownloadWorker  # noqa: E402

URL = "https://www.youtube.com/watch?v=aaaaaaaaaaa"


def make_worker(settings, url=URL, **overrides):
    options = settings.download_options()
    options.update(overrides)
    worker = DownloadWorker("t1", url, options)
    events = {"progress": [], "paths": [], "done": [], "phase": []}
    worker.phase.connect(lambda _i, text: events["phase"].append(text))
    worker.progress.connect(lambda _u, pct, _s, _e: events["progress"].append(pct))
    worker.destination.connect(lambda _u, path: events["paths"].append(path))
    worker.finished_sig.connect(lambda *args: events["done"].append(args))
    return worker, events


def test_two_streams_report_monotonic_global_progress(fake_ytdlp, settings, wait):
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    _url, ok, _msg, path = ev["done"][0]
    assert ok and path.endswith("Fake Video.mp4")
    assert ev["progress"] == sorted(ev["progress"])
    assert ev["progress"][-1] == pytest.approx(100)
    assert any(40 < p < 60 for p in ev["progress"]), "el vídeo debe ocupar solo la primera mitad"


def test_playlist_progress_spans_items(fake_ytdlp, settings, wait):
    worker, ev = make_worker(settings, "https://www.youtube.com/playlist?list=PL1", download_playlist=True)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    assert ev["done"][0][1] is True
    assert ev["progress"] == sorted(ev["progress"]) and ev["progress"][-1] == pytest.approx(100)


def test_failure_is_humanized_and_has_diagnostics(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_FAIL", "1")
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    _url, ok, message, _path = ev["done"][0]
    assert not ok and "anti-bots" in message
    assert "ERROR" in worker.diagnostics() and "Comando:" in worker.diagnostics()


def test_subtitles_only_returns_converted_path(fake_ytdlp, settings, wait):
    worker, ev = make_worker(settings, subs_mode="only", subs_langs=["es"])
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    assert ev["done"][0][1] and ev["done"][0][3].endswith(".es.srt")


def test_pause_really_stops_the_process(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: len(ev["progress"]) >= 2)
    worker.pause()
    procs = worker._tree()
    assert procs and all(p.status() == psutil.STATUS_STOPPED for p in procs)
    wait(lambda: False, timeout=0.3)
    seen = len(ev["progress"])
    wait(lambda: False, timeout=0.9)
    assert len(ev["progress"]) == seen, "no debe haber progreso mientras está en pausa"
    worker.resume()
    assert wait(lambda: ev["done"], timeout=30)
    worker.wait()
    assert ev["done"][0][1] is True


def test_cancel_while_paused(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_DELAY", "0.3")
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: len(ev["progress"]) >= 1)
    worker.pause()
    worker.cancel()
    assert wait(lambda: ev["done"])
    worker.wait()
    assert ev["done"][0][1] is False and ev["done"][0][2] == "Cancelado" and worker.cancelled


def test_item_id_travels_in_signals(fake_ytdlp, settings, wait):
    worker, ev = make_worker(settings)
    ids = []
    worker.finished_sig.connect(lambda item_id, *_: ids.append(item_id))
    worker.start()
    assert wait(lambda: ids)
    worker.wait()
    assert ids == ["t1"]


def test_phases_are_reported(fake_ytdlp, settings, wait):
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    assert "Obteniendo información…" in ev["phase"] and "Uniendo vídeo y audio…" in ev["phase"]


def test_exit_zero_without_a_file_is_a_failure(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_EMPTY", "1")
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    _id, ok, message, _path = ev["done"][0]
    assert not ok and "sin descargar ningún archivo" in message


def test_old_ytdlp_without_js_options_is_retried(fake_ytdlp, settings, wait, monkeypatch):
    from firedownload.core import ytdlp as ytdlp_module

    monkeypatch.setenv("FAKE_YTDLP_NO_JS", "1")
    monkeypatch.setattr(ytdlp_module, "find_js_runtime", lambda: ("deno", "/x/deno"))
    worker, ev = make_worker(settings)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    assert ev["done"][0][1] is True
    assert "--js-runtimes" not in worker.diagnostics()


def test_archive_skip_counts_as_success_without_file(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_ARCHIVE_SKIP", "1")
    worker, ev = make_worker(settings, use_archive=True)
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    _id, ok, message, path = ev["done"][0]
    assert ok and path == "" and "archivo de descargas" in message


def test_unavailable_format_is_retried_with_a_plain_selector(fake_ytdlp, settings, wait, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_NOFORMAT", "1")
    worker, ev = make_worker(settings, quality="720p")
    worker.start()
    assert wait(lambda: ev["done"])
    worker.wait()
    assert ev["done"][0][1] is True
    assert "Reintentando con otro formato…" in ev["phase"]
    assert "height<=720" not in worker.diagnostics().split("Salida")[0]
