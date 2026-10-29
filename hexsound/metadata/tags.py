from pathlib import Path
import mutagen

AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma"}

def read_tags(path: str) -> dict:
    p = Path(path)
    info = {"title": p.stem, "artist": "Unknown Artist", "album": "Unknown Album", "duration": 0.0}
    try:
        f = mutagen.File(path, easy=True)
        if f is not None:
            info["duration"] = float(getattr(f.info, "length", 0) or 0)
            for k in ("title", "artist", "album"):
                v = f.tags.get(k) if f.tags else None
                if v:
                    info[k] = str(v[0])
    except Exception:
        pass
    return info

def scan_folder(folder: str):
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix.lower() in AUDIO_EXT:
            yield str(p)


import hashlib, urllib.request
from mutagen.id3 import ID3

COVERS_DIR = Path.home() / ".hexsound" / "covers"

def save_cover_bytes(data: bytes, covers_dir: Path = COVERS_DIR) -> str:
    ext = ".png" if data[:4] == b"\x89PNG" else ".webp" if data[8:12] == b"WEBP" else ".jpg"
    covers_dir.mkdir(parents=True, exist_ok=True)
    out = covers_dir / (hashlib.sha1(data).hexdigest()[:16] + ext)
    if not out.exists():
        out.write_bytes(data)
    return str(out)

def extract_cover(path: str, covers_dir: Path = COVERS_DIR):
    """caminho da capa ou None"""
    data = None
    try:
        if Path(path).suffix.lower() == ".mp3":
            for fr in ID3(path).getall("APIC"):
                data = fr.data
                break
        else:
            f = mutagen.File(path)
            if f is not None:
                pics = getattr(f, "pictures", None)
                if pics:
                    data = pics[0].data
                elif f.tags and "covr" in f.tags:
                    data = bytes(f.tags["covr"][0])
    except Exception:
        return None
    return save_cover_bytes(data, covers_dir) if data else None

def fetch_cover_url(url, covers_dir: Path = COVERS_DIR):
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return save_cover_bytes(urllib.request.urlopen(req, timeout=10).read(), covers_dir)
    except Exception:
        return None


def write_mp3_tags(path: str, title: str, artist: str, album: str = "", cover_path=None):
    """grava tags ID3 e a capa dentro do mp3"""
    from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, APIC
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.delall("TALB")
        tags.add(TALB(encoding=3, text=album))
    if cover_path and Path(cover_path).exists():
        data = Path(cover_path).read_bytes()
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime="image/png" if data[:4] == b"\x89PNG" else "image/jpeg", type=3, desc="Cover", data=data))
    tags.save(path, v2_version=3)
