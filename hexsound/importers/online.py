"""Busca online para a tela Search: músicas do YouTube Music e do SoundCloud (ou tudo, se o usuário quiser).

Tudo roda em threads daemon: uma busca lenta ou uma rede travada nunca impede o app de fechar."""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from hexsound.importers import links

PREFIX = {"youtube": "ytsearch", "soundcloud": "scsearch"}
LIMIT = 8
MODES = ("songs", "ytmusic", "soundcloud", "all")  # songs = YouTube Music + SoundCloud
MUSIC_URL = "https://music.youtube.com/search?q={q}#songs"  # seção "Songs": só músicas, sem aulas nem vídeos longos
OEMBED = "https://www.youtube.com/oembed?format=json&url="
UA = {"User-Agent": "Mozilla/5.0"}
FALLBACK_MIN, FALLBACK_MAX = 60, 15 * 60  # se o YouTube Music falhar: só vídeos de 1 a 15 min
SOUNDCLOUD_MAX = 20 * 60  # corta sets e podcasts longos
PREVIEW_SECONDS = 30
PREVIEW_KEEP = 24 * 3600  # prévias antigas são apagadas


def _thumb(c, source):
    if c.get("thumb"):
        return c["thumb"]
    if source == "youtube":
        return f"https://i.ytimg.com/vi/{c['id']}/mqdefault.jpg"  # toda miniatura do YouTube tem esse endereço
    return None


def ytmusic(query, limit=LIMIT):
    """músicas do YouTube Music. A lista só traz id e título: artista e capa vêm de enrich_artists,
    e os dados completos (duração, álbum) são lidos no download."""
    import yt_dlp

    def go(opts):
        opts.update({"extract_flat": True, "skip_download": True, "playlistend": limit})
        with yt_dlp.YoutubeDL(opts) as y:
            return y.extract_info(MUSIC_URL.format(q=urllib.parse.quote_plus(query)), download=False)

    info = links._run(go) or {}
    out = []
    for e in info.get("entries") or []:
        vid = str((e or {}).get("id") or "")
        if not re.fullmatch(r"[\w-]{11}", vid):
            continue  # álbum, playlist ou artista: não é uma faixa
        out.append({"id": vid, "title": e.get("title") or "Unknown", "artist": "", "album": "", "duration": 0.0,
                    "url": f"https://www.youtube.com/watch?v={vid}", "source": "youtube", "label": "YouTube Music",
                    "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"})
    return out


def enrich_artists(items, timeout=5):
    """preenche o artista (nome do canal) de cada faixa com o oEmbed do YouTube; falhou, fica sem artista"""
    def one(r):
        try:
            u = OEMBED + urllib.parse.quote(f"https://www.youtube.com/watch?v={r['id']}", safe="")
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            a = re.sub(r"\s*-\s*Topic$", "", d.get("author_name") or "").strip()
            if a:
                r["artist"] = a
        except Exception:
            pass
        return r
    with ThreadPoolExecutor(max_workers=6) as ex:
        return list(ex.map(one, items))


def _plain(fetch, source, query, limit, lo=0, hi=None):
    """busca comum (ytsearch/scsearch); lo/hi limitam a duração em segundos"""
    out = []
    for c in fetch(f"{PREFIX[source]}{limit}", query):
        d = float(c.get("duration") or 0)
        if source == "youtube" and not d:
            continue  # transmissão ao vivo ou estreia: não dá para baixar
        if d and (d < lo or (hi and d > hi)):
            continue
        out.append({"id": c["id"], "title": c.get("title") or "Unknown",
                    "artist": c.get("artist") or c.get("channel") or "Unknown Artist", "album": "",
                    "duration": d, "url": c["url"], "source": source, "thumb": _thumb(c, source)})
    return out


def search(query, mode="songs", limit=LIMIT, fetch=None, music=None, enrich=None):
    """-> (resultados intercalados entre as fontes, lista de erros). Uma fonte falhar não derruba a outra.
    mode: songs (YouTube Music + SoundCloud) | ytmusic | soundcloud | all (tudo, sem filtro)"""
    fetch, music, enrich = fetch or links.search_candidates, music or ytmusic, enrich or enrich_artists
    only_music = mode != "all"
    per, errors = {}, []
    if mode in ("songs", "ytmusic", "all"):
        got = []
        if only_music:
            try:
                got = enrich(music(query, limit))
            except Exception as e:
                errors.append(f"YouTube Music: {links.clean_error(e)}")
        if not got:  # YouTube Music indisponível ou vazio: busca comum, mas só com cara de música
            try:
                got = _plain(fetch, "youtube", query, limit, *((FALLBACK_MIN, FALLBACK_MAX) if only_music else ()))
            except Exception as e:
                errors.append(f"youtube: {links.clean_error(e)}")
        per["youtube"] = got
    if mode in ("songs", "soundcloud", "all"):
        try:
            per["soundcloud"] = _plain(fetch, "soundcloud", query, limit, 0, SOUNDCLOUD_MAX if only_music else None)
        except Exception as e:
            errors.append(f"soundcloud: {links.clean_error(e)}")
    merged, seen = [], set()
    for i in range(limit):
        for s in ("youtube", "soundcloud"):
            lst = per.get(s) or []
            if i < len(lst) and (s, lst[i]["id"]) not in seen:
                seen.add((s, lst[i]["id"]))
                merged.append(lst[i])
    return merged, errors


class OnlineSearch(QObject):
    results = Signal(int, list, list)  # token, resultados, erros

    def search(self, token, query, mode):
        threading.Thread(target=self._run, args=(token, query, mode), daemon=True).start()

    def _run(self, token, query, mode):
        try:
            res, errs = search(query, mode)
        except Exception as e:
            res, errs = [], [links.clean_error(e)]
        try:
            self.results.emit(token, res, errs)
        except RuntimeError:  # app já fechou
            pass


class ThumbFetch(QObject):
    loaded = Signal(int, bytes)  # uid, imagem

    def fetch(self, items):
        """items: [(uid, url)]"""
        if items:
            threading.Thread(target=self._run, args=(list(items),), daemon=True).start()

    def _run(self, items):
        with ThreadPoolExecutor(max_workers=4) as ex:
            for uid, url in items:
                ex.submit(self._one, uid, url)

    def _one(self, uid, url):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=6) as r:
                data = r.read(600_000)
            self.loaded.emit(uid, data)
        except Exception:
            pass  # sem miniatura: a linha fica com o ícone padrão


def preview_start(duration):
    """onde começa a prévia: pula a introdução sem passar do fim; duração desconhecida (YouTube Music) = 20 s"""
    if not duration:
        return 20.0
    return 0.0 if duration < 75 else min(45.0, duration * 0.25)


def make_preview(entry, dest, seconds=PREVIEW_SECONDS):
    """-> caminho do mp3 com ~30 s da faixa (reaproveita se já foi baixada)"""
    dest = Path(dest)
    stem = f"preview_{entry['source']}_{entry['id']}"
    now = time.time()
    if dest.is_dir():
        for f in dest.glob("preview_*"):
            try:
                if now - f.stat().st_mtime > PREVIEW_KEEP and f.stem != stem:
                    f.unlink()
            except OSError:
                pass
    cached = dest / f"{stem}.mp3"
    if cached.exists() and cached.stat().st_size > 2000:
        return str(cached)
    if entry.get("source") == "youtube":
        links.ensure_js_runtime()
    start = preview_start(entry.get("duration") or 0)
    try:
        return links.download_preview(entry, dest, start, seconds, stem)
    except Exception as e:
        if start == 0 or links._blocked(e):
            raise
        return links.download_preview(entry, dest, 0.0, seconds, stem)  # faixa curta demais para o ponto escolhido: do começo


class PreviewFetch(QObject):
    ready = Signal(int, int, str, str)  # token, uid, caminho, erro

    def fetch(self, token, uid, entry, dest):
        threading.Thread(target=self._run, args=(token, uid, dict(entry), dest), daemon=True).start()

    def _run(self, token, uid, entry, dest):
        try:
            path, err = make_preview(entry, dest), ""
        except Exception as e:
            path, err = "", links.clean_error(e)
        try:
            self.ready.emit(token, uid, path, err)
        except RuntimeError:  # app já fechou
            pass
