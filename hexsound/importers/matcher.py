"""acha o áudio de uma faixa em fontes que dá pra baixar"""
import re
import unicodedata

_NOISE = re.compile(r"[\(\[\{][^\)\]\}]*(official|video|audio|lyrics?|lyric video|visuali[sz]er|hd|hq|4k|remaster(ed)?|"
                    r"clipe|legendado|tradu[cç][aã]o|mv|m/v|live)[^\)\]\}]*[\)\]\}]", re.I)
_FEAT = re.compile(r"\s*[\(\[]?\s*(feat\.?|ft\.?|featuring|com|with)\s+[^\)\]]*[\)\]]?", re.I)
_BAD = re.compile(r"\b(cover|karaoke|instrumental|8d|slowed|reverb|sped up|nightcore|remix|tribute|reaction|loop|1 hour|10 hours)\b", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def clean_title(title: str, artist: str = "") -> str:
    t = _NOISE.sub(" ", title or "")
    t = _FEAT.sub(" ", t)
    a = norm(artist)
    if " - " in t:  # "Artista - Música"
        left, right = t.split(" - ", 1)
        if a and (norm(left) in a or a in norm(left)):
            t = right
    return norm(t)


def dup_key(title: str, artist: str):
    return clean_title(title, artist), norm(artist.split(",")[0]) if artist and artist != "Unknown Artist" else ""


def is_same_song(t1, a1, d1, t2, a2, d2) -> bool:
    c1, c2 = clean_title(t1, a1), clean_title(t2, a2)
    if not c1 or not c2:
        return False
    if d1 and d2 and abs(d1 - d2) > 4:
        return False
    if c1 == c2:
        return True
    return min(len(c1), len(c2)) >= 5 and (c1 in c2 or c2 in c1) and bool(d1 and d2)


def score(cand: dict, title: str, artist: str, duration: float) -> float:
    """nota de 0 a 1"""
    ct = norm(cand.get("title", ""))
    chan = norm(cand.get("artist", "") + " " + (cand.get("channel") or ""))
    want_t, want_a = clean_title(title, artist), norm(artist.split(",")[0])
    s = 0.0
    if want_t and want_t in clean_title(cand.get("title", ""), artist) or want_t and want_t in ct:
        s += 0.5
    else:
        tw = set(want_t.split())
        cw = set(ct.split())
        s += 0.5 * (len(tw & cw) / len(tw)) if tw else 0
    if want_a and (want_a in ct or want_a in chan or any(w in chan for w in want_a.split() if len(w) > 3)):
        s += 0.2
    d = cand.get("duration") or 0
    if duration and d:
        diff = abs(d - duration)
        s += 0.3 if diff <= 3 else 0.22 if diff <= 8 else 0.08 if diff <= 15 else -0.3
    else:
        s += 0.1
    if "topic" in chan or "provided to youtube" in (cand.get("description") or "").lower():
        s += 0.08  # canal "Artista - Topic" = áudio oficial
    if _BAD.search(cand.get("title", "")) and not _BAD.search(title):
        s -= 0.35
    return max(0.0, min(1.0, s))


MIN_SCORE = 0.62


def pick(cands, title, artist, duration):
    ranked = sorted(((score(c, title, artist, duration), c) for c in cands), key=lambda x: -x[0])
    return ranked[0][1] if ranked and ranked[0][0] >= MIN_SCORE else None


def search_all(title: str, artist: str, duration: float, searcher, limit=4):
    q = f"{artist} {title}" if artist and artist != "Unknown Artist" else title
    out = []
    for prefix, source in (("ytsearch6", "youtube"), ("scsearch6", "soundcloud")):
        try:
            cands = searcher(prefix, q)
        except Exception:
            continue
        for c in cands:
            c["source"] = source
        ranked = sorted(((score(c, title, artist, duration), c) for c in cands), key=lambda x: -x[0])
        out += [c for sc, c in ranked if sc >= MIN_SCORE][:2]
    return out[:limit]


def search(title: str, artist: str, duration: float, searcher):
    q = f"{artist} {title}" if artist and artist != "Unknown Artist" else title
    for prefix, source in (("ytsearch6", "youtube"), ("scsearch6", "soundcloud")):
        try:
            cands = searcher(prefix, q)
        except Exception:
            continue
        for c in cands:
            c["source"] = source
        best = pick(cands, title, artist, duration)
        if best:
            return best
    return None
