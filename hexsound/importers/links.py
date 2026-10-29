import os
import platform
import re
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HEX_DIR = Path.home() / ".hexsound"
BIN_DIR = HEX_DIR / "bin"

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_URL = re.compile(r"(?:https?://|spotify:(?:track|album|playlist):)[^\s<>\"'“”‘’]+", re.I)
_PLAYLIST_ID = re.compile(r"(PL|OLAK5uy_|UU|FL|RD)[\w-]{10,}")
YT_HOSTS = {"youtube.com", "music.youtube.com", "youtu.be", "youtube-nocookie.com"}


def _host(u) -> str:
    h = u.netloc.lower().split("@")[-1].split(":")[0]
    for p in ("www.", "m.", "mobile.", "gaming."):
        h = h.removeprefix(p)
    return h


def classify(text: str) -> str:
    t = text.strip()
    if _PLAYLIST_ID.fullmatch(t):
        return "youtube_playlist"
    if t.lower().startswith("spotify:"):
        return "spotify"
    u = urlparse(t)
    host = _host(u)
    if host in YT_HOSTS:
        if host == "youtu.be":
            return "youtube_video"
        q = parse_qs(u.query)
        if u.path.startswith(("/shorts/", "/live/", "/embed/", "/v/")) or "v" in q:
            return "youtube_video"
        if "list" in q or u.path.startswith(("/playlist", "/channel/", "/c/", "/@", "/user/")):
            return "youtube_playlist"
        return "youtube_video"
    if host == "soundcloud.com" or host.endswith(".soundcloud.com"):
        return "soundcloud"
    if host == "open.spotify.com" or host == "spotify.link":
        return "spotify"
    return "unknown"


def normalize(text: str, kind: str) -> str:
    t = text.strip()
    if kind == "youtube_playlist" and "/" not in t:
        return f"https://www.youtube.com/playlist?list={t}"
    return t


def extract_links(text: str) -> list:
    found = []
    for line in text.replace(",", " ").splitlines():
        urls = _URL.findall(line)
        if urls:
            found += [u.rstrip(").,;") for u in urls]
        else:
            found += [tok for tok in line.split() if _PLAYLIST_ID.fullmatch(tok)]
    seen, out = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def clean_error(e) -> str:
    msg = _ANSI.sub("", str(e)).strip()
    msg = re.sub(r"^(ERROR:\s*)+", "", msg)
    msg = re.sub(r"^\[[\w:+-]+\]\s*[\w-]*:?\s*", "", msg) if msg.startswith("[") and len(msg) > 80 else msg
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return ("O YouTube pediu confirmação de que você não é um robô. Faça login no YouTube em um navegador "
                "(Firefox, Edge ou Chrome) e tente de novo: o HexSound usa os cookies do navegador automaticamente. "
                f"[{msg.splitlines()[0][:120]}]")
    if "private video" in low or "video unavailable" in low or "this video is not available" in low:
        return "Vídeo privado, removido ou bloqueado na sua região."
    if "http error 403" in low or "forbidden" in low:
        return "403: o site bloqueou o download. Atualize o yt-dlp (pip install -U yt-dlp) e tente de novo."
    if "getaddrinfo" in low or "urlopen error" in low or "timed out" in low or "unable to download" in low and "network" in low:
        return f"Falha de conexão com a internet. ({msg.splitlines()[0][:120]})"
    return msg.splitlines()[0][:300] if msg else "erro desconhecido"


def _exe(name):
    return name + (".exe" if os.name == "nt" else "")


def find_js_runtime():
    local = BIN_DIR / _exe("deno")
    if local.exists():
        return "deno", str(local)
    for name in ("deno", "node"):
        p = shutil.which(name)
        if p:
            return name, p
    return None


def _deno_asset():
    m = platform.machine().lower()
    arm = m in ("arm64", "aarch64")
    if sys.platform.startswith("win"):
        return "deno-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return "deno-aarch64-apple-darwin.zip" if arm else "deno-x86_64-apple-darwin.zip"
    return "deno-aarch64-unknown-linux-gnu.zip" if arm else "deno-x86_64-unknown-linux-gnu.zip"


def ensure_js_runtime(log=lambda m: None):
    """baixa o deno se não houver runtime JS"""
    found = find_js_runtime()
    if found:
        return found
    try:
        log("Baixando o Deno (necessário para o YouTube, só na primeira vez)…")
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/denoland/deno/releases/latest/download/{_deno_asset()}"
        zpath = BIN_DIR / "deno.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "HexSound"})
        with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
            shutil.copyfileobj(r, f)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(BIN_DIR)
        zpath.unlink(missing_ok=True)
        exe = BIN_DIR / _exe("deno")
        if exe.exists():
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
            log("Deno instalado.")
            return "deno", str(exe)
    except Exception as e:
        log(f"Não consegui baixar o Deno ({clean_error(e)}). Instale o Node.js ou o Deno manualmente se o YouTube falhar.")
    return None


def _base_opts(cookies_browser=None):
    opts = {
        "quiet": True, "no_warnings": True, "noprogress": True, "color": "no_color",
        "retries": 5, "fragment_retries": 5, "socket_timeout": 25,
        "remote_components": ["ejs:github"],
    }
    rt = find_js_runtime()
    if rt:
        opts["js_runtimes"] = {rt[0]: {"path": rt[1]}}
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts


def _needs_login(e) -> bool:
    low = str(e).lower()
    return "sign in to confirm" in low or "not a bot" in low or "cookies" in low and "youtube" in low


def _run(fn, cookies_browser=None):
    """tenta de novo com cookies do navegador se pedir login"""
    try:
        return fn(_base_opts(cookies_browser))
    except Exception as e:
        if cookies_browser or not _needs_login(e):
            raise
        last = e
        for b in ("firefox", "edge", "chrome", "brave"):
            try:
                return fn(_base_opts(b))
            except Exception as e2:
                last = e2 if not _needs_login(e2) else last
                continue
        raise last


def _flatten(info):
    if info.get("entries") is not None:
        for e in info["entries"]:
            if e:
                yield from _flatten(e)
    else:
        yield info


def _entry(e, source):
    vid = str(e.get("id"))
    url = e.get("webpage_url") or e.get("url") or ""
    if source == "youtube" and not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={vid}"
    return {"id": vid, "title": e.get("title") or "Unknown",
            "artist": e.get("artist") or e.get("creator") or e.get("uploader") or e.get("channel") or "Unknown Artist",
            "album": e.get("album") or e.get("playlist_title") or "", "duration": float(e.get("duration") or 0),
            "url": url, "source": source, "thumb": e.get("thumbnail")}


def fetch_entries(url: str, source: str):
    import yt_dlp

    def go(opts):
        opts.update({"extract_flat": "in_playlist", "skip_download": True})
        with yt_dlp.YoutubeDL(opts) as y:
            return y.extract_info(url, download=False)

    info = _run(go)
    if not info:
        raise RuntimeError("o link não retornou nenhum conteúdo")
    out = []
    list_title = info.get("title") if info.get("entries") is not None else None
    for e in _flatten(info):
        title = (e.get("title") or "")
        if title in ("[Private video]", "[Deleted video]") or not e.get("id"):
            continue
        it = _entry(e, source)
        if list_title:
            it["list_title"] = list_title
        out.append(it)
    if not out:
        raise RuntimeError("nenhuma faixa encontrada nesse link")
    return out


def _client_attempts():
    """tenta os clientes alternativos no 403"""
    return [None, ["tv"], ["android_vr"], ["web_safari"], ["mweb"]]


def _with_client(opts, clients):
    if clients:
        opts["extractor_args"] = {"youtube": {"player_client": clients}}
    return opts


def _blocked(e) -> bool:
    low = str(e).lower()
    return any(k in low for k in ("403", "forbidden", "unable to download", "requested format is not available", "sabr", "po token", "nsig"))


def ytdlp_age_days():
    try:
        import datetime, yt_dlp
        y, m, d = (int(x) for x in yt_dlp.version.__version__.split(".")[:3])
        return (datetime.date.today() - datetime.date(y, m, d)).days
    except Exception:
        return None


def ffmpeg_path():
    local = BIN_DIR / _exe("ffmpeg")
    if local.exists():
        return str(local)
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def search_candidates(prefix: str, query: str):
    import yt_dlp

    def go(opts):
        opts.update({"extract_flat": True, "skip_download": True})
        with yt_dlp.YoutubeDL(opts) as y:
            return y.extract_info(f"{prefix}:{query}", download=False)

    info = _run(go) or {}
    out = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        out.append({"id": str(e["id"]), "title": e.get("title") or "", "artist": e.get("uploader") or e.get("channel") or "",
                    "channel": e.get("channel") or "", "duration": float(e.get("duration") or 0),
                    "url": e.get("webpage_url") or e.get("url") or "", "thumb": e.get("thumbnail"),
                    "description": e.get("description") or ""})
    return [c for c in out if c["url"].startswith("http")]


_TITLE_NOISE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|audio|lyrics?|visuali[sz]er|clipe|hd|hq|4k)[^\)\]]*[\)\]]\s*", re.I)


def smart_meta(info: dict, fallback: dict):
    title = info.get("track") or ""
    artist = info.get("artist") or info.get("creator") or ""
    raw = info.get("title") or fallback.get("title") or ""
    if not title:
        title = _TITLE_NOISE.sub(" ", raw).strip()
        if not artist and " - " in title:
            a, t = title.split(" - ", 1)
            if 0 < len(a) <= 60 and t.strip():
                artist, title = a.strip(), t.strip()
    if not artist:
        artist = (info.get("uploader") or info.get("channel") or fallback.get("artist") or "Unknown Artist")
        artist = re.sub(r"\s*-\s*Topic$", "", artist).strip()
    return title.strip() or raw or "Unknown", artist


def download_audio(entry: dict, dest: Path, progress=lambda pct, stage="download": None, stem=None) -> str:
    """baixa e converte pra mp3 192k; retorna o caminho"""
    import yt_dlp
    dest.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg não encontrado (pip install imageio-ffmpeg, ou instale o ffmpeg) — preciso dele para gerar o MP3")
    stem = stem or f"{entry['source']}_{entry['id']}"

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress(min(99.0, d.get("downloaded_bytes", 0) * 100.0 / total), "download")
        elif d.get("status") == "finished":
            progress(100.0, "convert")

    def go(opts):
        opts.update({"format": "bestaudio/best", "noplaylist": True, "ffmpeg_location": ff,
                     "outtmpl": str(dest / f"{stem}.%(ext)s"), "progress_hooks": [hook], "http_chunk_size": 10 * 1024 * 1024,
                     "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
        with yt_dlp.YoutubeDL(opts) as y:
            return y.extract_info(entry["url"], download=True)

    info = None
    last = None
    for clients in (_client_attempts() if entry.get("source") == "youtube" or "youtu" in entry.get("url", "") else [None]):
        try:
            info = _run(lambda o, c=clients: go(_with_client(o, c)))
            last = None
            break
        except Exception as e:
            last = e
            if not _blocked(e):
                break
            for f in dest.glob(f"{stem}.*"):  # sobras do .part da tentativa anterior
                f.unlink(missing_ok=True)
    if last is not None:
        raise last
    path = dest / f"{stem}.mp3"
    if not path.exists():
        raise RuntimeError("o download terminou mas o MP3 não foi gerado")
    if entry["source"] != "spotify":  # Spotify já traz título/artista/capa certos; o resto vem do próprio site
        entry["title"], entry["artist"] = smart_meta(info or {}, entry)
        entry["album"] = (info or {}).get("album") or entry.get("album") or ""
        entry["thumb"] = (info or {}).get("thumbnail") or entry.get("thumb")
    entry["duration"] = float((info or {}).get("duration") or entry.get("duration") or 0)
    return str(path)
