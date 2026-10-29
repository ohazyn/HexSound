import json, re
from pathlib import Path

FORMAT, ID_RE = "hexplaylist", re.compile(r"^[A-Z0-9]{6,32}$")

def _url(t):
    return f"https://www.youtube.com/watch?v={t['source_id']}" if t["source"] == "youtube" else None

def export_playlist(lib, pid, path):
    p = lib.playlist(pid)
    doc = {"format": FORMAT, "version": 1, "id": p["id"], "name": p["name"], "description": p["description"],
           "tracks": [{"title": t["title"], "artist": t["artist"], "album": t["album"], "duration": t["duration"],
                       "source": t["source"], "source_id": t["source_id"] if t["source"] != "local" else None,
                       "url": _url(t)} for t in lib.playlist_tracks(pid)]}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")

def _find(lib, t):
    if t.get("source") not in (None, "local") and t.get("source_id"):
        r = lib.conn.execute("SELECT id FROM tracks WHERE source=? AND source_id=? AND available=1",
                             (t["source"], t["source_id"])).fetchone()
        if r:
            return r["id"]
    r = lib.conn.execute("SELECT id FROM tracks WHERE lower(title)=lower(?) AND lower(artist)=lower(?) AND available=1",
                         (str(t.get("title", "")), str(t.get("artist", "")))).fetchone()
    return r["id"] if r else None

def import_playlist(lib, path):
    try:
        doc = json.loads(Path(path).read_text("utf-8"))
    except Exception:
        raise ValueError("Not a valid .hexplaylist file.")
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("tracks"), list) \
       or not isinstance(doc.get("name"), str) or len(doc["tracks"]) > 20000:
        raise ValueError("Not a valid .hexplaylist file.")
    pid = doc.get("id")
    pid = pid if isinstance(pid, str) and ID_RE.match(pid) and not lib.playlist(pid) else None
    pid = lib.create_playlist(doc["name"][:200], str(doc.get("description") or "")[:2000], pid)
    added, missing = 0, []
    for t in doc["tracks"]:
        if not isinstance(t, dict):
            continue
        tid = _find(lib, t)
        if tid:
            lib.add_to_playlist(pid, tid)
            added += 1
        else:
            missing.append(t)
    return {"id": pid, "name": doc["name"], "added": added, "missing": missing}

def find_playlist_file(pid, shared_dir):
    pid = pid.strip().upper()
    if not ID_RE.match(pid):
        return None
    f = Path(shared_dir) / f"{pid}.hexplaylist"
    return f if f.exists() else None
