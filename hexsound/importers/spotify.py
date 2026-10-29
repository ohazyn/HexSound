"""metadados públicos do Spotify; o áudio vem de outra fonte (ver matcher.py)"""
import json
import re
import urllib.request
from urllib.parse import urlparse

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Accept-Language": "en-US,en;q=0.8"}
_PATH = re.compile(r"/(?:intl-[a-z-]+/)?(?:embed/)?(track|album|playlist)/([A-Za-z0-9]{10,30})")
_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_META = r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"'


def parse_link(url: str):
    t = url.strip()
    m = re.fullmatch(r"spotify:(track|album|playlist):([A-Za-z0-9]{10,30})", t)
    if m:
        return m.group(1), m.group(2)
    m = _PATH.search(urlparse(t).path)
    return (m.group(1), m.group(2)) if m else None


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


def resolve_short(url: str) -> str:
    final, _ = _get(url)
    return final


def _best_image(imgs):
    imgs = [i for i in (imgs or []) if isinstance(i, dict) and i.get("url")]
    return max(imgs, key=lambda i: (i.get("width") or i.get("maxWidth") or 0))["url"] if imgs else None


def _artist_names(e):
    arts = e.get("artists")
    if isinstance(arts, list) and arts:
        return ", ".join(a.get("name", "") for a in arts if isinstance(a, dict) and a.get("name"))
    return (e.get("subtitle") or e.get("artist") or "").strip()


def _track_item(d, cover=None, album=""):
    uri = d.get("uri") or ""
    tid = uri.split(":")[-1] if uri.startswith("spotify:track:") else (d.get("id") or "")
    title = (d.get("title") or d.get("name") or "").strip()
    if not title or not tid:
        return None
    dur = d.get("duration") or d.get("duration_ms") or 0
    return {"id": tid, "title": title, "artist": _artist_names(d).replace("\xa0", " ") or "Unknown Artist", "album": album,
            "duration": float(dur) / 1000.0 if dur else 0.0, "cover_url": cover, "source": "spotify",
            "url": f"https://open.spotify.com/track/{tid}"}


def parse_embed(html: str, kind: str, sid: str):
    """lê o __NEXT_DATA__ da página /embed"""
    m = _NEXT.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    ent = None
    stack = [data]
    while stack:  # acha o dicionário "entity" mesmo se o caminho mudar
        x = stack.pop()
        if isinstance(x, dict):
            if isinstance(x.get("entity"), dict) and ("trackList" in x["entity"] or "title" in x["entity"] or "name" in x["entity"]):
                ent = x["entity"]
                break
            stack += list(x.values())
        elif isinstance(x, list):
            stack += x
    if not ent:
        return None
    cover = _best_image((ent.get("coverArt") or {}).get("sources")) or _best_image((ent.get("visualIdentity") or {}).get("image"))
    name = (ent.get("name") or ent.get("title") or "").strip()
    if kind == "track" and not ent.get("trackList"):
        it = _track_item(dict(ent, id=sid), cover, "")
        return (None, [it]) if it else None
    album = name if kind == "album" else ""
    items = [i for i in (_track_item(t, cover if kind == "album" else None, album) for t in ent.get("trackList") or []) if i]
    return (name or None, items) if items else None


def parse_og(html: str, kind: str, sid: str):
    """plano B: metatags og: da página normal"""
    def meta(k):
        mm = re.search(_META % re.escape(k), html)
        return re.sub(r"&amp;", "&", mm.group(1)).strip() if mm else ""
    title, desc, img = meta("og:title"), meta("og:description"), meta("og:image")
    if kind != "track" or not title:
        return None
    parts = [p.strip() for p in re.split(r"\s[·•]\s", desc)]
    artist = parts[0] if parts and parts[0] else "Unknown Artist"
    album = parts[1] if len(parts) > 2 else ""
    return None, [{"id": sid, "title": title, "artist": artist, "album": album, "duration": 0.0, "cover_url": img or None,
                   "source": "spotify", "url": f"https://open.spotify.com/track/{sid}"}]


def fetch(url: str):
    host = urlparse(url).netloc.lower()
    if host.endswith("spotify.link"):
        url = resolve_short(url)
    ref = parse_link(url)
    if not ref:
        raise RuntimeError("esse link do Spotify não é de música, álbum ou playlist (artistas e podcasts não são suportados)")
    kind, sid = ref
    res = None
    try:
        res = parse_embed(_get(f"https://open.spotify.com/embed/{kind}/{sid}")[1], kind, sid)
    except Exception:
        res = None
    if not res and kind == "track":
        try:
            res = parse_og(_get(f"https://open.spotify.com/track/{sid}")[1], kind, sid)
        except Exception:
            res = None
    if not res:
        raise RuntimeError("não consegui ler esse link do Spotify (playlist privada, removida ou sem internet)")
    return res
