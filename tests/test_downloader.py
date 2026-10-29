# testes do downloader. nada vai pra internet: o "youtube" é um servidor local que serve um .ogg
import functools, http.server, json, os, threading, time
from pathlib import Path
import pytest
pytest.importorskip("yt_dlp")
from PySide6.QtWidgets import QApplication
from hexsound.importers import links, matcher, spotify
from hexsound.importers.worker import LinkWorker
from test_ui_smoke import win  # noqa: F401

HERE = Path(__file__).parent
if not links.ffmpeg_path():
    pytest.skip("ffmpeg indisponível", allow_module_level=True)

def test_classify_and_extract_spotify():
    assert links.classify("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=abc") == "spotify"
    assert links.classify("https://open.spotify.com/intl-pt/playlist/37i9dQZF1DXcBWIGoYBM5M") == "spotify"
    assert links.classify("spotify:album:1DFixLWuPkv3KT3TnV35m3") == "spotify"
    assert links.extract_links("olha: spotify:track:4uLU6hMCjMI75M1A2tKUQC e https://youtu.be/dQw4w9WgXcQ") == \
        ["spotify:track:4uLU6hMCjMI75M1A2tKUQC", "https://youtu.be/dQw4w9WgXcQ"]
    assert spotify.parse_link("https://open.spotify.com/intl-pt/track/4uLU6hMCjMI75M1A2tKUQC?si=x") == ("track", "4uLU6hMCjMI75M1A2tKUQC")
    assert spotify.parse_link("https://open.spotify.com/artist/0TnOYISbd1XYRBk9myaseg") is None

def _page(entity):
    return '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}) + "</script></html>"

def test_parse_embed_playlist_and_track():
    pl = _page({"type": "playlist", "name": "Meu Mix", "coverArt": {"sources": [{"url": "http://x/a.jpg", "width": 64}, {"url": "http://x/b.jpg", "width": 640}]},
                "trackList": [{"uri": "spotify:track:AAAAAAAAAAAAAAAAAAAAAA", "title": "Song One", "subtitle": "Artist A,\xa0Artist B", "duration": 215000},
                              {"uri": "spotify:track:BBBBBBBBBBBBBBBBBBBBBB", "title": "Song Two", "subtitle": "Artist C", "duration": 180000}, {"title": "sem id"}]})
    name, items = spotify.parse_embed(pl, "playlist", "x")
    assert name == "Meu Mix" and [i["title"] for i in items] == ["Song One", "Song Two"] and items[0]["duration"] == 215 and items[0]["id"] == "AAAAAAAAAAAAAAAAAAAAAA"
    assert items[0]["artist"] == "Artist A, Artist B"
    tr = _page({"type": "track", "name": "Solo", "artists": [{"name": "Ana"}, {"name": "Bia"}], "duration": 200000, "coverArt": {"sources": [{"url": "http://x/c.jpg", "width": 300}]}})
    n, items = spotify.parse_embed(tr, "track", "TTTTTTTTTTTTTTTTTTTTTT")
    assert n is None and items[0]["artist"] == "Ana, Bia" and items[0]["cover_url"] == "http://x/c.jpg" and items[0]["id"] == "TTTTTTTTTTTTTTTTTTTTTT"
    assert spotify.parse_embed("<html>nada</html>", "track", "x") is None

def test_parse_og_fallback():
    html = '<meta property="og:title" content="Blinding Lights"/><meta property="og:description" content="The Weeknd · After Hours · Song · 2020"/><meta property="og:image" content="http://i/c.jpg"/>'
    n, items = spotify.parse_og(html, "track", "ID1")
    assert items[0]["title"] == "Blinding Lights" and items[0]["artist"] == "The Weeknd" and items[0]["cover_url"] == "http://i/c.jpg"

def test_matcher_prefers_original_over_cover_and_wrong_length():
    c = [{"title": "Blinding Lights (Cover by Someone)", "artist": "Someone", "duration": 200, "id": "1"},
         {"title": "The Weeknd - Blinding Lights (Official Audio)", "artist": "TheWeekndVEVO", "duration": 201, "id": "2"},
         {"title": "Blinding Lights 10 hours", "artist": "Loop", "duration": 36000, "id": "3"}]
    assert matcher.pick(c, "Blinding Lights", "The Weeknd", 200)["id"] == "2"
    assert matcher.pick([{"title": "Totally different song", "artist": "x", "duration": 200, "id": "9"}], "Blinding Lights", "The Weeknd", 200) is None

def test_same_song_detection():
    S = matcher.is_same_song
    assert S("The Weeknd - Blinding Lights (Official Video)", "VEVO", 200, "Blinding Lights", "The Weeknd", 201)
    assert S("Song (feat. X)", "A", 180, "Song", "A", 180)
    assert not S("Song", "A", 180, "Song", "A", 240)  # mesma palavra, duração diferente = outra faixa
    assert not S("Song", "A", 180, "Another", "A", 180)

def test_mp3_tags_roundtrip(tmp_path):
    from mutagen.id3 import ID3
    import subprocess
    f = tmp_path / "a.mp3"
    subprocess.run([links.ffmpeg_path(), "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", str(f)], check=True)
    from PySide6.QtGui import QImage, QColor
    QApplication.instance() or QApplication([])
    img = tmp_path / "c.png"
    qi = QImage(8, 8, QImage.Format_RGB32)
    qi.fill(QColor("red"))
    qi.save(str(img))
    from hexsound.metadata.tags import write_mp3_tags, read_tags, extract_cover
    write_mp3_tags(str(f), "Título é", "Artista", "Álbum", str(img))
    t = read_tags(str(f))
    assert (t["title"], t["artist"], t["album"]) == ("Título é", "Artista", "Álbum")
    assert extract_cover(str(f), tmp_path / "cv") and ID3(str(f)).getall("APIC")

@pytest.fixture(scope="module")
def server():
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
    class Q(http.server.ThreadingHTTPServer):
        daemon_threads = True
    h.func.log_message = lambda *a, **k: None
    srv = Q(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()

def _fake_net(monkeypatch, server, items, name="Meu Mix", url_for=lambda it: None):
    monkeypatch.setattr(spotify, "fetch", lambda url: (name, [dict(i) for i in items]))
    monkeypatch.setattr(links, "ensure_js_runtime", lambda log=None: None)
    import hexsound.importers.worker as W
    monkeypatch.setattr(W, "ensure_js_runtime", lambda log=None: None)
    def cands(prefix, q):
        if prefix.startswith("sc"):
            return []
        return [{"id": "yt_" + q.split()[-1].lower(), "title": q.replace("  ", " ") + " (Official Audio)", "artist": "Topic", "channel": "Artist - Topic",
                 "duration": 6.0, "url": f"{server}/_song.ogg", "thumb": None, "description": ""}]
    monkeypatch.setattr(links, "search_candidates", cands)

SP = [{"id": "AAAAAAAAAAAAAAAAAAAAAA", "title": "Alpha", "artist": "Band", "album": "Rec", "duration": 6.0, "cover_url": None, "source": "spotify", "url": "https://open.spotify.com/track/AAAAAAAAAAAAAAAAAAAAAA"},
      {"id": "BBBBBBBBBBBBBBBBBBBBBB", "title": "Bravo", "artist": "Band", "album": "Rec", "duration": 6.0, "cover_url": None, "source": "spotify", "url": "https://open.spotify.com/track/BBBBBBBBBBBBBBBBBBBBBB"}]

def _run(w):
    ev = {"state": [], "track": [], "known": [], "queue": [], "done": None, "meta": None}
    w.state.connect(lambda *a: ev["state"].append(a))
    w.track.connect(lambda it, p: ev["track"].append((it, p)))
    w.known.connect(ev["known"].append)
    w.queue.connect(ev["queue"].append)
    w.done.connect(lambda *a: ev.__setitem__("done", a))
    w.meta.connect(lambda m: ev.__setitem__("meta", m))
    app = QApplication.instance() or QApplication([])
    w._run()
    for _ in range(5):
        app.processEvents()  # sinais vindos das threads de download são entregues na fila de eventos
    return ev

def test_spotify_playlist_downloads_mp3_with_tags_and_dedupes(tmp_path, monkeypatch, server):
    _fake_net(monkeypatch, server, SP)
    from hexsound.metadata.tags import read_tags
    w = LinkWorker("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", set(), tmp_path)
    ev = _run(w)
    assert ev["done"] == (2, 0, 0) and ev["meta"] == "Meu Mix" and len(ev["queue"][0]) == 2
    for it, path in ev["track"]:
        assert path.endswith(".mp3") and Path(path).stat().st_size > 1000
        t = read_tags(path)
        assert t["title"] == it["title"] and t["artist"] == "Band" and t["album"] == "Rec"
    assert {s[1] for s in ev["state"]} >= {"searching", "downloading", "converting", "done"}
    assert max(s[2] for s in ev["state"] if s[1] == "downloading") > 0
    # 2ª vez: biblioteca já tem as faixas → nada é baixado de novo
    known = {(it["source"], it["id"]) for it, _ in ev["track"]}
    ev2 = _run(LinkWorker("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", known, tmp_path))
    assert ev2["done"] == (0, 0, 2) and not ev2["track"] and len(ev2["known"]) == 2

def test_duplicate_by_title_and_inside_same_playlist(tmp_path, monkeypatch, server):
    items = [dict(SP[0]), dict(SP[0], id="CCCCCCCCCCCCCCCCCCCCCC"), dict(SP[1])]  # "Alpha" duas vezes na mesma playlist
    _fake_net(monkeypatch, server, items)
    ev = _run(LinkWorker("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", set(), tmp_path, [(77, "Bravo (Official Video)", "Band", 6.0)], workers=1))
    assert ev["done"] == (1, 0, 2)  # Bravo já existe (outra versão do título); 2º Alpha é repetido
    assert {"track_id": 77} in ev["known"] and len(ev["track"]) == 1

def test_no_match_and_cancel(tmp_path, monkeypatch, server):
    _fake_net(monkeypatch, server, SP)
    monkeypatch.setattr(links, "search_candidates", lambda p, q: [])
    ev = _run(LinkWorker("spotify:track:AAAAAAAAAAAAAAAAAAAAAA", set(), tmp_path))
    assert ev["done"] == (0, 2, 0) and any(s[1] == "failed" and "não achei" in s[3] for s in ev["state"])
    _fake_net(monkeypatch, server, SP)
    w = LinkWorker("spotify:track:AAAAAAAAAAAAAAAAAAAAAA", set(), tmp_path / "c")
    w.cancel()
    ev = _run(w)
    assert ev["done"][0] == 0 and not ev["track"] and not list((tmp_path / "c").glob("*.part"))

def test_direct_link_is_converted_to_mp3(tmp_path, monkeypatch, server):
    monkeypatch.setattr(links, "classify", lambda t: "youtube_video")
    monkeypatch.setattr(links, "ensure_js_runtime", lambda log=None: None)
    import hexsound.importers.worker as W
    monkeypatch.setattr(W, "ensure_js_runtime", lambda log=None: None)
    monkeypatch.setattr(W, "classify", lambda t: "youtube_video")
    monkeypatch.setattr(links, "fetch_entries", lambda u, s: [{"id": "vid1", "title": "Artist X - Real Title (Official Video)", "artist": "Chan", "album": "", "duration": 6.0,
                                                               "url": f"{server}/_song.ogg", "source": "youtube", "thumb": None}])
    monkeypatch.setattr(W.links, "fetch_entries", links.fetch_entries)
    ev = _run(LinkWorker(f"{server}/_song.ogg", set(), tmp_path))
    it, path = ev["track"][0]
    assert path.endswith(".mp3") and Path(path).stat().st_size > 1000 and ev["done"] == (1, 0, 0) and it["title"]

def test_smart_meta_splits_artist_and_title():
    assert links.smart_meta({"title": "Artist X - Real Title (Official Video)", "uploader": "VEVO"}, {}) == ("Real Title", "Artist X")
    assert links.smart_meta({"title": "Whatever", "track": "Real", "artist": "Ana"}, {}) == ("Real", "Ana")
    assert links.smart_meta({"title": "Just a title", "uploader": "Band - Topic"}, {}) == ("Just a title", "Band")

def _wait(cond, t=40):
    end = time.time() + t
    while time.time() < end and not cond():
        QApplication.processEvents()
        time.sleep(0.02)
    QApplication.processEvents()
    assert cond()

def test_import_page_end_to_end(win, tmp_path, monkeypatch, server):
    _fake_net(monkeypatch, server, SP)
    win.settings.set("download_dir", str(tmp_path / "dl"))
    p = win.page["Import Music"]
    win.go_page("Import Music")
    assert p.dest.findData("__new__") >= 0 and p.go.text() == "Download"
    p.dest.setCurrentIndex(p.dest.findData("__new__"))
    p.link.setText("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    p.go.click()
    assert not p.go.isEnabled() and p.stop.isVisible() is not None
    _wait(lambda: p.worker is not None and not p.worker.isRunning() and p.go.isEnabled())
    assert len(p.queue.rows) == 2 and all(r.state == "done" for r in p.queue.rows.values())
    pls = win.lib.playlists()
    assert [x["name"] for x in pls] == ["Meu Mix"] and len(win.lib.playlist_tracks(pls[0]["id"])) == 2
    tr = win.lib.tracks()
    assert len(tr) == 2 and all(t["source"] == "spotify" and t["path"].endswith(".mp3") for t in tr)
    assert p.play_all.isVisible() and "2 added" in p.summary.text()
    p.play_all.click()
    assert win.cur is not None and win.queue.current is not None
    # mesma playlist de novo: duplicatas ignoradas, nenhuma playlist nova se repetir no mesmo destino
    p.dest.setCurrentIndex(p.dest.findData(pls[0]["id"]))
    p.link.setText("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M")
    p.go.click()
    _wait(lambda: not p.worker.isRunning() and p.go.isEnabled())
    assert len(win.lib.tracks()) == 2 and "2 already in library" in p.summary.text()
    # link inválido não trava a tela
    p.link.setText("isso não é link")
    p.go.click()
    _wait(lambda: not p.worker.isRunning() and p.go.isEnabled())
    assert len(win.lib.tracks()) == 2

def test_import_page_cancel_button(win, tmp_path, monkeypatch, server):
    _fake_net(monkeypatch, server, SP)
    gate = threading.Event()
    real = links.search_candidates
    monkeypatch.setattr(links, "search_candidates", lambda pr, q: (gate.wait(5), real(pr, q))[1])
    win.settings.set("download_dir", str(tmp_path / "dl"))
    p = win.page["Import Music"]
    win.go_page("Import Music")
    p.link.setText("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M")
    p.go.click()
    _wait(lambda: len(p.queue.rows) == 2)
    p.cancel()
    gate.set()
    _wait(lambda: not p.worker.isRunning() and p.go.isEnabled())
    assert win.lib.tracks() == [] and all(r.state == "cancelled" for r in p.queue.rows.values())

def test_403_retries_other_youtube_clients(tmp_path, monkeypatch, server):
    calls = []
    real = links._run
    def fake(fn, cookies_browser=None):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        return real(fn, cookies_browser)
    monkeypatch.setattr(links, "_run", fake)
    entry = {"id": "x", "title": "T", "artist": "A", "duration": 6.0, "url": f"{server}/_song.ogg", "source": "youtube"}
    path = links.download_audio(entry, tmp_path)
    assert len(calls) == 3 and path.endswith(".mp3") and Path(path).exists()
    assert links._blocked(RuntimeError("HTTP Error 403: Forbidden")) and not links._blocked(RuntimeError("Video unavailable"))

def test_403_everywhere_gives_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr(links, "_run", lambda fn, cookies_browser=None: (_ for _ in ()).throw(RuntimeError("HTTP Error 403: Forbidden")))
    with pytest.raises(RuntimeError) as e:
        links.download_audio({"id": "x", "title": "T", "artist": "A", "duration": 1, "url": "https://youtu.be/x", "source": "youtube"}, tmp_path)
    assert "yt-dlp" in links.clean_error(e.value) and "403" in links.clean_error(e.value)

def test_spotify_track_tries_next_candidate_when_first_fails(tmp_path, monkeypatch, server):
    _fake_net(monkeypatch, server, SP[:1])
    bad = {"id": "bad", "title": "Band Alpha (Official Audio)", "artist": "Topic", "channel": "Band - Topic", "duration": 6.0, "url": f"{server}/nao_existe.ogg", "thumb": None, "description": ""}
    good = dict(bad, id="good", url=f"{server}/_song.ogg")
    monkeypatch.setattr(links, "search_candidates", lambda p, q: [bad, good] if p.startswith("yt") else [])
    ev = _run(LinkWorker("spotify:track:AAAAAAAAAAAAAAAAAAAAAA", set(), tmp_path, workers=1))
    assert ev["done"] == (1, 0, 0) and ev["track"][0][1].endswith(".mp3")

def test_retry_button_on_failed_track(win, tmp_path, monkeypatch, server):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    _fake_net(monkeypatch, server, SP[:1])
    good = links.search_candidates
    monkeypatch.setattr(links, "search_candidates", lambda p, q: [])  # 1ª vez: nada encontrado
    win.settings.set("download_dir", str(tmp_path / "dl"))
    p = win.page["Import Music"]
    win.go_page("Import Music")
    p.link.setText("spotify:track:AAAAAAAAAAAAAAAAAAAAAA")
    p.go.click()
    _wait(lambda: not p.worker.isRunning() and p.go.isEnabled())
    row = p.queue.rows[0]
    assert row.state == "failed" and row.retryable and p.retry.isVisible() and win.lib.tracks() == []
    row.resize(900, row.H)
    pill = row._pill()
    assert pill.right() <= row.width() and not row.playable
    monkeypatch.setattr(links, "search_candidates", good)  # agora a fonte responde
    QTest.mouseClick(row, Qt.LeftButton, Qt.NoModifier, pill.center().toPoint())  # clica no botão Retry da linha
    _wait(lambda: p.worker is not None and not p.worker.isRunning() and p.go.isEnabled() and len(win.lib.tracks()) == 1)
    assert len(p.queue.rows) == 1 and list(p.queue.rows.values())[0].state == "done" and "1 added" in p.summary.text() and not p.retry.isVisible()
    assert win.lib.tracks()[0]["path"].endswith(".mp3")
