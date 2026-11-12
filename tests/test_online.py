# busca online: nada vai pra internet (a busca e o download são simulados)
import json
import pytest
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QApplication
from hexsound.importers import online, worker as W
from test_ui_smoke import win  # noqa: F401


def _c(i, title, dur=200, thumb=None, **kw):
    return {"id": f"id{i}", "title": title, "artist": kw.get("artist", "Ana"), "channel": "", "duration": dur,
            "url": f"https://x/{i}", "thumb": thumb, "description": ""}


def _music(items):
    return lambda q, limit=8: [{"id": i, "title": t, "artist": "", "album": "", "duration": 0.0, "url": f"https://www.youtube.com/watch?v={i}",
                                "source": "youtube", "label": "YouTube Music", "thumb": f"https://i.ytimg.com/vi/{i}/mqdefault.jpg"} for i, t in items]


def _no_enrich(items):
    return items


def test_modo_songs_usa_youtube_music_e_soundcloud_intercalados():
    def fetch(prefix, q):
        assert prefix.startswith("scsearch")                  # YouTube comum nem é consultado quando o YouTube Music responde
        return [_c(10, "s1", thumb="http://t/s1.jpg"), _c(11, "s2"), _c(12, "set de 2 horas", dur=7200)]
    res, errs = online.search("x", "songs", fetch=fetch, music=_music([("AAAAAAAAAAA", "m1"), ("BBBBBBBBBBB", "m2")]), enrich=_no_enrich)
    assert errs == []
    assert [r["title"] for r in res] == ["m1", "s1", "m2", "s2"]       # fontes se alternam; set de 2 h do SoundCloud fica de fora
    assert res[0]["label"] == "YouTube Music" and res[0]["thumb"].startswith("https://i.ytimg.com/vi/AAAAAAAAAAA")
    assert res[1]["source"] == "soundcloud" and res[1]["thumb"] == "http://t/s1.jpg" and res[3]["thumb"] is None


def test_enrich_preenche_artista_e_tolera_falha(monkeypatch):
    class R:
        def __init__(self, d): self.d = d
        def read(self): return json.dumps(self.d).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake(req, timeout=0):
        if "AAAAAAAAAAA" in req.full_url:
            return R({"author_name": "Rick Astley - Topic"})
        raise OSError("sem rede")
    monkeypatch.setattr(online.urllib.request, "urlopen", fake)
    items = [{"id": "AAAAAAAAAAA", "artist": ""}, {"id": "BBBBBBBBBBB", "artist": ""}]
    out = online.enrich_artists(items)
    assert out[0]["artist"] == "Rick Astley" and out[1]["artist"] == ""    # falhou: continua sem artista, sem derrubar nada


def test_youtube_music_fora_do_ar_cai_para_busca_comum_filtrada():
    def boom(q, limit=8):
        raise RuntimeError("web_music indisponivel")
    def fetch(prefix, q):
        if prefix.startswith("ytsearch"):
            return [_c(1, "musica", dur=200), _c(2, "aula longa", dur=3800), _c(3, "ao vivo", dur=0), _c(4, "vinheta", dur=20)]
        return []
    res, errs = online.search("x", "songs", fetch=fetch, music=boom, enrich=_no_enrich)
    assert [r["title"] for r in res] == ["musica"]          # só 1 a 15 minutos; aula, ao vivo e vinheta saem
    assert len(errs) == 1 and errs[0].startswith("YouTube Music:")


def test_youtube_music_vazio_tambem_cai_para_busca_comum():
    fetch = lambda prefix, q: [_c(1, "musica", dur=200)] if prefix.startswith("ytsearch") else []
    res, _ = online.search("x", "ytmusic", fetch=fetch, music=_music([]), enrich=_no_enrich)
    assert [r["title"] for r in res] == ["musica"]


def test_modo_all_nao_filtra_nada_e_nao_usa_youtube_music():
    def music(q, limit=8):
        raise AssertionError("não deveria consultar o YouTube Music")
    def fetch(prefix, q):
        return [_c(1, "aula longa", dur=3800), _c(2, "ao vivo", dur=0)] if prefix.startswith("ytsearch") else [_c(10, "set", dur=7200)]
    res, _ = online.search("x", "all", fetch=fetch, music=music, enrich=_no_enrich)
    assert [r["title"] for r in res] == ["aula longa", "set"]        # ao vivo (sem duração) sempre sai: não baixa


def test_modo_soundcloud_so_consulta_soundcloud():
    seen = []
    def fetch(prefix, q):
        seen.append(prefix)
        return [_c(10, "s1")]
    res, _ = online.search("x", "soundcloud", fetch=fetch, music=lambda *a, **k: 1 / 0, enrich=_no_enrich)
    assert seen == ["scsearch8"] and [r["title"] for r in res] == ["s1"]


def test_uma_fonte_falhar_nao_derruba_a_outra():
    def fetch(prefix, q):
        raise RuntimeError("sem rede")
    res, errs = online.search("x", "songs", fetch=fetch, music=_music([("AAAAAAAAAAA", "m1")]), enrich=_no_enrich)
    assert [r["title"] for r in res] == ["m1"] and len(errs) == 1 and errs[0].startswith("soundcloud:")


def test_ytmusic_le_so_faixas_da_lista(monkeypatch):
    import yt_dlp
    seen = {}
    class FakeYDL:
        def __init__(self, opts): seen["opts"] = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            seen["url"] = url
            return {"entries": [{"id": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up"}, {"id": "VLPLxxxxxxxxxxxxxxxx", "title": "playlist"},
                                {"id": "short", "title": "x"}, None, {"id": "9bZkp7q19f0", "title": "Gangnam Style"}]}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    res = online.ytmusic("rick roll & co", 5)
    assert seen["url"] == "https://music.youtube.com/search?q=rick+roll+%26+co#songs"   # consulta codificada, seção Songs
    assert seen["opts"]["playlistend"] == 5 and seen["opts"]["extract_flat"] is True
    assert [r["id"] for r in res] == ["dQw4w9WgXcQ", "9bZkp7q19f0"]                      # playlist e id inválido ficam de fora
    assert res[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ" and res[0]["source"] == "youtube"


# ---- LinkWorker com faixas já prontas (é o que o botão Add usa)
def _run_worker(monkeypatch, tmp_path, known=(), songs=()):
    QApplication.instance() or QApplication([])
    calls = []
    def fake_dl(entry, dest, progress=None, stem=None):
        calls.append(entry["url"])
        f = tmp_path / f"{stem}.mp3"
        f.write_bytes(b"x")
        return str(f)
    monkeypatch.setattr(W.links, "download_audio", fake_dl)
    monkeypatch.setattr(W, "fetch_cover_url", lambda u: None)
    monkeypatch.setattr(W, "write_mp3_tags", lambda *a, **k: None)
    monkeypatch.setattr(W, "ensure_js_runtime", lambda log: None)
    entry = {"id": "abc", "title": "Song", "artist": "Ana", "album": "", "duration": 200.0, "url": "https://x/abc", "source": "youtube", "thumb": None}
    w = W.LinkWorker("", known, tmp_path, songs, idx_base=7, entries=[entry])
    got = {"track": [], "known": [], "state": [], "done": []}
    D = Qt.DirectConnection
    w.track.connect(lambda it, p: got["track"].append((it, p)), D)
    w.known.connect(lambda it: got["known"].append(it), D)
    w.state.connect(lambda i, s, p, m: got["state"].append((i, s)), D)
    w.done.connect(lambda a, b, c: got["done"].append((a, b, c)), D)
    w.run()
    return got, calls


def test_worker_baixa_faixa_pronta_sem_ler_link(monkeypatch, tmp_path):
    got, calls = _run_worker(monkeypatch, tmp_path)
    assert calls == ["https://x/abc"]                       # baixou direto, sem reler o link
    (it, path), = got["track"]
    assert it["idx"] == 7 and it["id"] == "abc" and it["title"] == "Song" and path.endswith("youtube_abc.mp3")
    assert (7, "done") in got["state"] and got["done"] == [(1, 0, 0)]


def test_worker_pula_faixa_que_ja_esta_na_biblioteca(monkeypatch, tmp_path):
    got, calls = _run_worker(monkeypatch, tmp_path, known={("youtube", "abc")})
    assert calls == [] and got["track"] == [] and got["known"] == [{"source": "youtube", "id": "abc"}]
    assert (7, "skipped") in got["state"] and got["done"] == [(0, 0, 1)]


def test_worker_texto_vazio_sem_faixas_continua_avisando(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    w = W.LinkWorker("sem link nenhum", set(), tmp_path)
    done = []
    w.done.connect(lambda a, b, c: done.append((a, b, c)), Qt.DirectConnection)
    w.run()
    assert done == [(0, 0, 0)]                              # comportamento antigo preservado


# ---- tela Search
class FakeWorker(QObject):
    state = Signal(int, str, float, str)
    track = Signal(dict, str)
    known = Signal(dict)
    log = Signal(str)
    done = Signal(int, int, int)
    started = []
    def __init__(self, text, known_ids, dest, songs, idx_base=0, entries=None):
        super().__init__()
        self.idx_base, self.entries, self.known_ids = idx_base, entries, known_ids
    def start(self):
        FakeWorker.started.append(self)
    def isFinished(self):
        return True


@pytest.fixture
def page(win, monkeypatch):  # noqa: F811
    import hexsound.ui.pages.search as S
    FakeWorker.started = []
    monkeypatch.setattr(S, "LinkWorker", FakeWorker)
    pg = win.page["Search"]
    monkeypatch.setattr(pg._svc, "search", lambda *a: None)
    monkeypatch.setattr(pg._thumbs, "fetch", lambda items: None)
    return pg


def _res(i, source="youtube"):
    return {"id": f"id{i}", "title": f"Song {i}", "artist": "Ana", "album": "", "duration": 200.0, "url": f"https://x/{i}", "source": source, "thumb": None}


def test_resultados_aparecem_e_resultado_velho_e_ignorado(page):
    page._token = 5
    page._online_done(4, [_res(1)], [])                      # busca antiga chegando atrasada
    assert not page.online.rows
    page._online_done(5, [_res(1), _res(2, "soundcloud")], [])
    assert len(page.online.rows) == 2 and "2 results" in page.online.status.text()
    assert all(r.state == "idle" for r in page.online.rows.values())


def test_erro_de_rede_mostra_mensagem(page):
    page._token = 1
    page._online_done(1, [], ["youtube: sem rede"])
    assert "Could not search" in page.online.status.text() and not page.online.rows


def test_faixa_que_ja_esta_na_biblioteca_vira_play(page, win):  # noqa: F811
    tid, _ = win.lib.add_track("Song 1", "Ana", "", 200.0, path="/tmp/a.mp3", source="youtube", source_id="id1")
    page._token = 1
    page._online_done(1, [_res(1)], [])
    row, = page.online.rows.values()
    assert row.state == "done" and "In library" in row.meta._full


def test_add_baixa_um_por_vez_e_grava_na_biblioteca(page, win):  # noqa: F811
    page._token = 1
    page._online_done(1, [_res(1), _res(2)], [])
    u1, u2 = list(page.online.rows)
    page.add_online(u1)
    page.add_online(u2)
    assert len(FakeWorker.started) == 1                      # o segundo espera a vez
    assert page.online.rows[u1].state == "waiting" and page.online.rows[u2].state == "waiting"
    w1 = FakeWorker.started[0]
    assert w1.idx_base == u1 and w1.entries[0]["url"] == "https://x/1"
    w1.state.emit(u1, "downloading", 40.0, "")
    assert page.online.rows[u1].state == "downloading" and page.online.rows[u1].btn.text() == "40%"
    w1.track.emit({"idx": u1, "title": "Song 1", "artist": "Ana", "album": "", "duration": 200.0, "source": "youtube", "id": "id1", "cover": None}, "/tmp/s1.mp3")
    w1.state.emit(u1, "done", 100.0, "")
    w1.done.emit(1, 0, 0)
    assert page.online.rows[u1].state == "done" and win.lib.find_source("youtube", "id1") is not None
    assert len(FakeWorker.started) == 2 and FakeWorker.started[1].idx_base == u2   # agora o segundo
    w2 = FakeWorker.started[1]
    w2.state.emit(u2, "failed", 0.0, "HTTP 403")
    w2.done.emit(0, 1, 0)
    assert page.online.rows[u2].state == "failed" and "HTTP 403" in page.online.status.text()
    page.add_online(u2)                                      # Retry
    assert len(FakeWorker.started) == 3 and page.online.rows[u2].state == "waiting"


def test_worker_que_cai_sem_avisar_nao_deixa_linha_presa(page):
    page._token = 1
    page._online_done(1, [_res(1)], [])
    uid, = page.online.rows
    page.add_online(uid)
    FakeWorker.started[0].done.emit(0, 1, 0)                 # terminou sem nenhum estado
    assert page.online.rows[uid].state == "failed"


def test_enter_na_barra_de_cima_busca_online(win, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(win.page["Search"], "search_online", lambda: calls.append(1))
    win._global_enter()
    assert calls == [1]


def test_busca_dispara_so_com_texto(page):
    sent = []
    page._svc.search = lambda *a: sent.append(a)
    page.q.setText("   ")
    page.search_online()
    assert sent == []
    page.q.setText("lofi")
    page.search_online()
    page.src.setCurrentIndex(page.src.findData("all"))
    page.search_online()
    assert sent[1][2] == "all"
    sent.pop()
    assert len(sent) == 1 and sent[0][1] == "lofi" and sent[0][2] == "songs"      # padrão: só músicas


# ---- prévia de 30 s
def test_preview_start():
    assert online.preview_start(0) == 20.0 and online.preview_start(None) == 20.0   # duração desconhecida (YouTube Music)
    assert online.preview_start(60) == 0.0                                          # faixa curta: do começo
    assert online.preview_start(100) == 25.0 and online.preview_start(400) == 45.0  # pula a introdução, no máximo 45 s


class _FakeYDL:
    info, seen = {}, []
    def __init__(self, opts): self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def extract_info(self, url, download=True):
        _FakeYDL.seen.append((url, self.opts, download))
        return _FakeYDL.info


def test_stream_url_pega_link_direto_sem_baixar(monkeypatch):
    import yt_dlp
    from hexsound.importers import links
    _FakeYDL.seen, _FakeYDL.info = [], {"url": "https://cdn/a.m4a", "http_headers": {"User-Agent": "UA"}, "protocol": "https"}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)
    url, headers = links._stream_url({"url": "https://www.youtube.com/watch?v=abc"}, ["android_vr"])
    assert (url, headers) == ("https://cdn/a.m4a", {"User-Agent": "UA"})
    _, opts, download = _FakeYDL.seen[0]
    assert download is False and opts["format"].startswith("bestaudio[ext=m4a]") and opts["extractor_args"]["youtube"]["player_client"] == ["android_vr"]


@pytest.mark.parametrize("info", [{}, {"url": "https://cdn/a", "fragments": [{}]}, {"url": "https://cdn/a", "protocol": "http_dash_segments"}])
def test_stream_url_recusa_formato_sem_link_simples(monkeypatch, info):
    import yt_dlp
    from hexsound.importers import links
    _FakeYDL.seen, _FakeYDL.info = [], info
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)
    with pytest.raises(RuntimeError, match="prévia"):
        links._stream_url({"url": "https://x/y"}, None)


def _fake_ffmpeg(monkeypatch, tmp_path, results):
    """results: lista de (returncode, stderr, bytes_gravados); devolve (links, cmds, clientes)"""
    import subprocess
    from hexsound.importers import links
    cmds, clients = [], []
    def fake_stream(entry, c):
        clients.append(c)
        return "https://cdn/x.m4a", {"User-Agent": "UA"}
    def fake_run(cmd, **kw):
        cmds.append(cmd)
        code, err, size = results[min(len(cmds), len(results)) - 1]
        if size:
            open(cmd[-1], "wb").write(b"x" * size)
        return subprocess.CompletedProcess(cmd, code, "", err)
    monkeypatch.setattr(links, "_stream_url", fake_stream)
    monkeypatch.setattr(links, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)
    return links, cmds, clients


def test_download_preview_uma_chamada_ao_ffmpeg(monkeypatch, tmp_path):
    links, cmds, _ = _fake_ffmpeg(monkeypatch, tmp_path, [(0, "", 5000)])
    path = links.download_preview({"id": "abc", "source": "soundcloud", "url": "https://soundcloud.com/a/b"}, tmp_path, 20, 30, stem="p")
    cmd, = cmds
    assert path == str(tmp_path / "p.mp3") and sorted(f.name for f in tmp_path.iterdir()) == ["p.mp3"]   # sem sobra de arquivo temporário
    assert cmd.index("-ss") < cmd.index("-i") and cmd[cmd.index("-ss") + 1] == "20.00" and cmd[cmd.index("-t") + 1] == "30.00"
    assert cmd[cmd.index("-headers") + 1] == "User-Agent: UA\r\n" and cmd[cmd.index("-i") + 1] == "https://cdn/x.m4a"
    assert "libmp3lame" in cmd and "-vn" in cmd and cmd[-1].endswith("p.part.mp3")


def test_download_preview_youtube_comeca_pelo_cliente_rapido_e_troca_no_403(monkeypatch, tmp_path):
    links, cmds, clients = _fake_ffmpeg(monkeypatch, tmp_path, [(1, "Server returned 403 Forbidden (access denied)", 0), (0, "", 5000)])
    links.download_preview({"id": "abc", "source": "youtube", "url": "https://www.youtube.com/watch?v=abc"}, tmp_path, 0, 30, stem="p")
    assert clients == [["android_vr"], None] and len(cmds) == 2


def test_download_preview_erro_comum_do_ffmpeg_nao_repete(monkeypatch, tmp_path):
    links, cmds, clients = _fake_ffmpeg(monkeypatch, tmp_path, [(1, "aviso\nInvalid data found when processing input", 0)])
    with pytest.raises(RuntimeError, match="ffmpeg: Invalid data"):
        links.download_preview({"id": "abc", "source": "youtube", "url": "https://www.youtube.com/watch?v=abc"}, tmp_path, 0, 30, stem="p")
    assert len(cmds) == 1 and list(tmp_path.iterdir()) == []


def test_download_preview_arquivo_vazio_e_erro(monkeypatch, tmp_path):
    links, _, _ = _fake_ffmpeg(monkeypatch, tmp_path, [(0, "", 10)])
    with pytest.raises(RuntimeError, match="prévia"):
        links.download_preview({"id": "abc", "source": "soundcloud", "url": "https://x/y"}, tmp_path, 0, 30, stem="p")
    assert list(tmp_path.iterdir()) == []


def test_download_preview_timeout(monkeypatch, tmp_path):
    import subprocess
    links, _, _ = _fake_ffmpeg(monkeypatch, tmp_path, [(0, "", 5000)])
    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 45)
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(RuntimeError, match="tempo esgotado"):
        links.download_preview({"id": "abc", "source": "soundcloud", "url": "https://x/y"}, tmp_path, 0, 30, stem="p")


def test_make_preview_cache_fallback_e_limpeza(monkeypatch, tmp_path):
    import os, time
    calls = []
    def fake_dl(entry, dest, start, seconds, stem):
        calls.append(start)
        if start == 20.0 and fake_dl.fail:
            raise RuntimeError("trecho fora da faixa")
        (dest / f"{stem}.mp3").write_bytes(b"x" * 5000)
        return str(dest / f"{stem}.mp3")
    fake_dl.fail = False
    monkeypatch.setattr(online.links, "download_preview", fake_dl)
    monkeypatch.setattr(online.links, "ensure_js_runtime", lambda *a: None)
    e = {"id": "AAAAAAAAAAA", "source": "youtube", "duration": 0}
    old = tmp_path / "preview_youtube_velha.mp3"
    old.write_bytes(b"x")
    os.utime(old, (time.time() - 3 * 86400,) * 2)
    p1 = online.make_preview(e, tmp_path)
    assert calls == [20.0] and not old.exists()               # tocou do ponto escolhido; prévia velha foi apagada
    assert online.make_preview(e, tmp_path) == p1 and calls == [20.0]   # segunda vez: reaproveita, não baixa
    (tmp_path / "preview_youtube_BBBBBBBBBBB.mp3").unlink(missing_ok=True)
    fake_dl.fail = True
    online.make_preview({"id": "BBBBBBBBBBB", "source": "youtube", "duration": 0}, tmp_path)
    assert calls[-2:] == [20.0, 0.0]                           # falhou no trecho: tenta do começo


def test_make_preview_403_nao_repete(monkeypatch, tmp_path):
    calls = []
    def fake_dl(entry, dest, start, seconds, stem):
        calls.append(start)
        raise RuntimeError("HTTP Error 403: Forbidden")
    monkeypatch.setattr(online.links, "download_preview", fake_dl)
    monkeypatch.setattr(online.links, "ensure_js_runtime", lambda *a: None)
    with pytest.raises(RuntimeError):
        online.make_preview({"id": "CCCCCCCCCCC", "source": "youtube", "duration": 0}, tmp_path)
    assert calls == [20.0]                                     # bloqueio não melhora tentando de novo


@pytest.fixture
def prev(page, win, monkeypatch):  # noqa: F811
    from hexsound.ui.nowstate import now
    fetched, toggles = [], []
    monkeypatch.setattr(page._pf, "fetch", lambda *a: fetched.append(a))
    monkeypatch.setattr(win.engine, "toggle", lambda: toggles.append(1))
    page._token = 1
    page._online_done(1, [_res(1), _res(2)], [])
    u1, u2 = list(page.online.rows)
    return page, win, now, fetched, toggles, u1, u2, monkeypatch


def test_previa_toca_pausa_a_biblioteca_e_volta(prev):
    page, win, now, fetched, toggles, u1, u2, mp = prev
    mp.setattr(now, "playing", True)
    page.preview_online(u1)
    assert page.online.rows[u1].pv.toolTip().startswith("Loading") and len(fetched) == 1
    token, uid, entry, dest = fetched[0]
    assert uid == u1 and entry["url"] == "https://x/1" and str(dest).endswith("previews")
    page._preview_ready(token, u1, "/tmp/p.mp3", "")
    assert toggles == [1] and page.online.rows[u1].pv.toolTip() == "Stop preview"   # a biblioteca pausou
    assert "preview" in page.online.status.text() and "loaded in" in page.online.status.text()   # mostra quanto demorou
    mp.setattr(now, "playing", False)
    page.prev.finished.emit()                                                     # a prévia acabou sozinha
    assert page._pv_uid is None and toggles == [1, 1] and page.online.rows[u1].pv.toolTip().startswith("Preview")


def test_previa_sem_musica_tocando_nao_mexe_na_biblioteca(prev):
    page, win, now, fetched, toggles, u1, u2, mp = prev
    mp.setattr(now, "playing", False)
    page.preview_online(u1)
    page._preview_ready(fetched[0][0], u1, "/tmp/p.mp3", "")
    page.preview_online(u1)                                                       # segundo clique para
    assert toggles == [] and page._pv_uid is None


def test_previa_erro_mostra_mensagem(prev):
    page, win, now, fetched, toggles, u1, u2, mp = prev
    page.preview_online(u1)
    page._preview_ready(fetched[0][0], u1, "", "HTTP 403")
    assert "Preview failed: HTTP 403" in page.online.status.text() and page.online.rows[u1].pv.toolTip().startswith("Preview")
    assert page.prev is None                                                      # nem criou o player


def test_previa_atrasada_ou_cancelada_e_ignorada(prev):
    page, win, now, fetched, toggles, u1, u2, mp = prev
    page.preview_online(u1)
    page.preview_online(u2)                                                       # trocou de faixa antes de carregar
    page._preview_ready(fetched[0][0], u1, "/tmp/a.mp3", "")                      # resposta da primeira chega tarde
    assert page.prev is None and page._pv_uid == u2
    page.preview_online(u2)                                                       # cancela durante o carregamento
    page._preview_ready(fetched[1][0], u2, "/tmp/b.mp3", "")
    assert page.prev is None and toggles == []


def test_tocar_a_biblioteca_encerra_a_previa_sem_retomar(prev):
    page, win, now, fetched, toggles, u1, u2, mp = prev
    mp.setattr(now, "playing", True)
    page.preview_online(u1)
    page._preview_ready(fetched[0][0], u1, "/tmp/p.mp3", "")
    assert toggles == [1]
    win._on_state(True)                                                           # usuário apertou play na biblioteca
    assert page._pv_uid is None and toggles == [1]                                # não retoma (já está tocando por escolha dele)


def test_sair_da_tela_ou_nova_busca_para_a_previa(prev):
    from PySide6.QtGui import QHideEvent
    page, win, now, fetched, toggles, u1, u2, mp = prev
    mp.setattr(now, "playing", False)
    page.preview_online(u1)
    page._preview_ready(fetched[0][0], u1, "/tmp/p.mp3", "")
    page.hideEvent(QHideEvent())
    assert page._pv_uid is None
    page.preview_online(u2)
    page._preview_ready(fetched[1][0], u2, "/tmp/p.mp3", "")
    page._token = 2
    page._online_done(2, [_res(3)], [])                                           # resultados novos
    assert page._pv_uid is None


def test_previa_real_sem_ffmpeg_nem_ffprobe_no_path(monkeypatch, tmp_path):
    """regressões reais: o yt-dlp só achava o ffmpeg no PATH ('ffmpeg is not installed') e exigia o ffprobe
    ('unable to obtain file audio codec'). O app só traz o ffmpeg do imageio-ffmpeg, fora do PATH."""
    import functools, http.server, re, shutil, socketserver, subprocess, threading
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    from hexsound.importers import links
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    src = tmp_path / "srv"
    src.mkdir()
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=90", "-b:a", "128k", str(src / "t.mp3")], check=True)
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(src)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("PATH", str(tmp_path / "vazio"))
        assert shutil.which("ffmpeg") is None and shutil.which("ffprobe") is None
        entry = {"id": "t", "source": "local", "url": f"http://127.0.0.1:{srv.server_address[1]}/t.mp3"}
        out = links.download_preview(entry, tmp_path / "prev", 20, 30)
    finally:
        srv.shutdown()
        srv.server_close()
    info = subprocess.run([ff, "-i", out], capture_output=True, text=True).stderr
    h, m, sec = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
    assert abs(int(h) * 3600 + int(m) * 60 + float(sec) - 30) < 1.5      # trecho de ~30 s, não os 90 s do arquivo
    assert [f.name for f in (tmp_path / "prev").iterdir()] == ["preview_local_t.mp3"]
