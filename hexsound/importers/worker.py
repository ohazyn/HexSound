import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from hexsound.metadata.tags import fetch_cover_url, write_mp3_tags
from hexsound.importers import links, matcher, spotify
from hexsound.importers.links import classify, normalize, extract_links, ensure_js_runtime, clean_error

WORKERS = 3


class Cancelled(Exception):
    pass


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]", "", s)[:40] or "track"


class LinkWorker(QThread):
    log = Signal(str)
    meta = Signal(str)  # nome da playlist/álbum de origem (para criar uma playlist com ele)
    queue = Signal(list)  # entradas lidas do link: [{idx, title, artist, cover_url, duration, ...}]
    state = Signal(int, str, float, str)  # idx, estado, % (0-100), mensagem
    progress = Signal(int, int)  # concluídas, total
    track = Signal(dict, str)  # faixa baixada (já com tags) + caminho do MP3
    known = Signal(dict)  # faixa que já estava na biblioteca: {"track_id": n} ou {"source","id"}
    done = Signal(int, int, int)  # baixadas, falhas, ignoradas (duplicadas)

    def __init__(self, text, known_ids, dest, library_songs=(), workers=WORKERS, idx_base=0):
        """known_ids: {(source, source_id)}"""
        super().__init__()
        self.text, self.known_ids, self.dest = text, set(known_ids), Path(dest)
        self.songs = list(library_songs)
        self.workers = workers
        self.idx_base = idx_base
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._finished = 0

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            self._run()
        except Exception as e:  # nunca deixa a thread morrer sem avisar a UI
            self.log.emit(f"Failed: erro inesperado — {clean_error(e)}")
            self.done.emit(0, 1, 0)

    def _read(self, line):
        kind = classify(line)
        if kind == "unknown":
            self.log.emit(f"Unrecognized link: {line}")
            return []
        self.log.emit(f"Reading link… {line}")
        if kind == "spotify":
            name, items = spotify.fetch(line)
            if name:
                self.meta.emit(name)
            self.log.emit(f"Spotify: {len(items)} track(s). Searching the same songs on YouTube/SoundCloud (audio never comes from Spotify).")
            return items
        found = links.fetch_entries(normalize(line, kind), "soundcloud" if kind == "soundcloud" else "youtube")
        if found and found[0].get("list_title") and len(found) > 1:
            self.meta.emit(found[0]["list_title"])
        return found

    def _run(self):
        lines = extract_links(self.text)
        if not lines:
            self.log.emit("Could not read link: não encontrei nenhum link do YouTube, SoundCloud ou Spotify no texto.")
            self.done.emit(0, 0, 0)
            return
        if any(classify(l).startswith("youtube") or classify(l) == "spotify" for l in lines):
            ensure_js_runtime(self.log.emit)
            age = links.ytdlp_age_days()
            if age is not None and age > 45:
                self.log.emit(f"Warning: yt-dlp is {age} days old. YouTube changes often; if downloads fail with 403, run: pip install -U yt-dlp")
        entries = []
        for line in lines:
            if self._cancel.is_set():
                break
            try:
                entries += self._read(line)
            except Exception as e:
                self.log.emit(f"Could not read link: {clean_error(e)}")
        for i, it in enumerate(entries):
            it["idx"] = self.idx_base + i
        self.queue.emit([dict(it) for it in entries])
        n = len(entries)
        self.progress.emit(0, n)
        self.counts = {"ok": 0, "fail": 0, "skip": 0}
        if entries:
            with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="hex-dl") as ex:
                for it in entries:
                    ex.submit(self._one, it, n)
        if self._cancel.is_set():
            self.log.emit("Cancelled.")
        self.done.emit(self.counts["ok"], self.counts["fail"], self.counts["skip"])

    def _bump(self, kind, n):
        with self._lock:
            self.counts[kind] += 1
            self._finished += 1
            self.progress.emit(self._finished, n)

    def _is_dup(self, it):
        """reserva a faixa; None = pode baixar"""
        with self._lock:
            if (it["source"], it["id"]) in self.known_ids:
                return {"source": it["source"], "id": it["id"]}
            for tid, t, a, d in self.songs:
                if matcher.is_same_song(it["title"], it["artist"], it["duration"], t, a, d):
                    return {"track_id": tid}
            self.known_ids.add((it["source"], it["id"]))
            self.songs.append((None, it["title"], it["artist"], it["duration"]))
            return None

    def _release(self, it):
        with self._lock:
            self.known_ids.discard((it["source"], it["id"]))
            self.songs[:] = [s for s in self.songs if not (s[0] is None and s[1] == it["title"] and s[2] == it["artist"])]

    def _one(self, it, n):
        idx, title = it["idx"], it["title"]
        last = [-1.0]

        def st(state, pct=0.0, msg=""):
            self.state.emit(idx, state, float(pct), msg)

        def prog(pct, stage="download"):
            if self._cancel.is_set():
                raise Cancelled()
            if stage == "convert":
                st("converting", 100)
                return
            if pct - last[0] >= 1.0 or pct >= 99:
                last[0] = pct
                st("downloading", pct)

        if self._cancel.is_set():
            st("cancelled")
            self._bump("fail", n)
            return
        dup = self._is_dup(it)
        if dup:
            self.log.emit(f"Skipped (already in your library): {title}")
            st("skipped", 100, "Already in your library")
            self.known.emit(dup)
            self._bump("skip", n)
            return
        reserved = it
        stem = f"{it['source']}_{_safe(it['id'])}"
        try:
            src = dict(it)
            if it["source"] == "spotify":
                st("searching", 0, "Finding the audio…")
                cands = matcher.search_all(title, it["artist"], it["duration"], links.search_candidates)
                if not cands:
                    raise RuntimeError("não achei esse áudio no YouTube nem no SoundCloud")
                path, err = None, None
                for found in cands:  # tenta cada correspondência até uma baixar
                    if self._cancel.is_set():
                        raise Cancelled()
                    if (found["source"], found["id"]) in self.known_ids:
                        self._release(it)
                        st("skipped", 100, "Already in your library")
                        self.known.emit({"source": found["source"], "id": found["id"]})
                        self._bump("skip", n)
                        return
                    src = dict(it)
                    src.update({"url": found["url"], "source": found["source"], "id": found["id"], "thumb": found.get("thumb")})
                    if not src.get("duration"):
                        src["duration"] = found.get("duration") or 0
                    st("downloading", 0)
                    last[0] = -1.0
                    try:
                        path = links.download_audio(src, self.dest, prog, stem=stem)
                        break
                    except Cancelled:
                        raise
                    except Exception as e:
                        err = e
                        self.log.emit(f"Retrying {title}: {found['source']} failed ({clean_error(e)[:90]}); trying another source…")
                if path is None:
                    raise err or RuntimeError("nenhuma fonte conseguiu baixar")
            else:
                st("downloading", 0)
                path = links.download_audio(src, self.dest, prog, stem=stem)
            out = dict(it)
            if it["source"] == "spotify":  # metadados do Spotify; guarda também o id do Spotify
                out.update(duration=src["duration"], audio_source=src["source"])
            else:
                out.update(title=src["title"], artist=src["artist"], album=src.get("album", ""), duration=src["duration"], thumb=src.get("thumb"))
            out["cover"] = fetch_cover_url(out.get("cover_url") or src.get("thumb") or out.get("thumb"))
            try:
                write_mp3_tags(path, out["title"], out["artist"], out.get("album", ""), out["cover"])
            except Exception as e:
                self.log.emit(f"Tags not written for {out['title']}: {e}")
            self.track.emit(out, path)
            st("done", 100)
            self._bump("ok", n)
            self.log.emit(f"Imported: {out['artist']} — {out['title']}")
        except Cancelled:
            self._release(reserved)
            self._cleanup(stem)
            st("cancelled")
            self._bump("fail", n)
        except Exception as e:
            self._release(reserved)
            self._cleanup(stem)
            msg = clean_error(e)
            st("failed", 0, msg)
            self.log.emit(f"Failed: {title} — {msg}")
            self._bump("fail", n)

    def _cleanup(self, stem):
        try:
            for f in self.dest.glob(f"{stem}.*"):
                f.unlink(missing_ok=True)
        except OSError:
            pass
