"""Tela Import Music: arquivos, pastas e links (YouTube/Spotify/SoundCloud) com fila de downloads."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QPlainTextEdit
from hexsound.importers.worker import LinkWorker
from hexsound.metadata.tags import AUDIO_EXT
from hexsound.ui import icons, pickers
from hexsound.ui.downloads import DownloadQueue
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassCombo, SearchField
from hexsound.ui.pages.common import gbtn, h1

class ImportPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.worker, self.target = win, None, None
        self._newpid = None
        self._meta = None
        self._tids = []
        self._pending = {}
        self._retry_wait = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(h1("Import Music"))
        self.status = QLabel("Paste a link below, drop audio files anywhere in the window, press Ctrl+V after copying files, or use the buttons.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        for text, ic, fn in [("Add files", "file-plus", self.files), ("Add folder", "folder-plus", self.folder)]:
            b = gbtn(text, ic)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        row = QHBoxLayout()
        self.link = SearchField("Paste a Spotify / YouTube / SoundCloud link")
        self.link.actions()[0].setIcon(icons.icon("link", T.fg.name(), 16))
        self.dest = GlassCombo()
        self.go = gbtn("Download", "download", "accent")
        self.stop = gbtn("Cancel", "x")
        self.stop.hide()
        self.go.clicked.connect(lambda: self.start_links(self.link.text()))
        self.link.returnPressed.connect(self.go.click)
        self.stop.clicked.connect(self.cancel)
        row.addWidget(self.link, 1)
        row.addWidget(QLabel("Add to"))
        row.addWidget(self.dest)
        row.addWidget(self.go)
        row.addWidget(self.stop)
        lay.addLayout(row)
        srow = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        self.play_all = gbtn("Play", "play", "glass")
        self.play_all.hide()
        self.retry = gbtn("Retry failed", "refresh", "glass")
        self.retry.hide()
        self.retry.clicked.connect(self.retry_failed)
        self.play_all.clicked.connect(self.play_imported)
        srow.addWidget(self.summary, 1)
        srow.addWidget(self.retry)
        srow.addWidget(self.play_all)
        lay.addLayout(srow)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)
        self.queue = DownloadQueue()
        self.queue.play.connect(self.play_one)
        self.queue.retry.connect(lambda i: self.retry_rows([i]))
        lay.addWidget(self.queue, 1)
        self.logbox = QPlainTextEdit(readOnly=True)
        self.logbox.setMaximumHeight(64)
        lay.addWidget(self.logbox)
    def refresh(self):
        cur = self.dest.currentData()
        self.dest.clear()
        self.dest.addItem("Library only", None)
        self.dest.addItem("New playlist from link", "__new__")
        for p in self.win.lib.playlists():
            self.dest.addItem(p["name"], p["id"])
        i = self.dest.findData(cur)
        self.dest.setCurrentIndex(max(i, 0))
    def files(self):
        fs = pickers.pick_files(self, "Add audio files", sorted(AUDIO_EXT))
        if fs:
            self.win.import_paths(fs)
    def folder(self):
        d = pickers.pick_dir(self, "Add a folder of music")
        if d:
            self.win.import_paths([d])
    @property
    def busy(self):
        return bool(self.worker and self.worker.isRunning())
    def start_links(self, text, pid=None, keep=False):
        if not text.strip() or self.busy:
            return
        self.target = pid or self.dest.currentData()
        self._newpid = None if not keep else self._newpid
        self._meta = None
        self._tids = [] if not keep else self._tids
        base = 0
        if keep:
            base = max(self.queue.rows, default=-1) + 1
            self.logbox.appendPlainText("— Retrying —")
        else:
            self.logbox.clear()
            self.queue.clear()
            self._pending = {}
        self.play_all.hide()
        self.retry.hide()
        self.summary.setText("Reading link…")
        self.bar.setRange(0, 0)
        self.go.setEnabled(False)
        self.stop.show()
        self.stop.setEnabled(True)
        lib = self.win.lib
        rows = lib.tracks()
        known = {(r["source"], r["source_id"]) for r in rows}
        songs = [(r["id"], r["title"], r["artist"] or "", float(r["duration"] or 0)) for r in rows]
        w = self.worker = LinkWorker(text, known, self.win.settings["download_dir"], songs, idx_base=base)
        w.log.connect(self.on_log)
        w.meta.connect(self.on_meta)
        w.queue.connect(self.on_queue)
        w.state.connect(self.queue.set_state)
        w.progress.connect(self.on_progress)
        w.track.connect(self.add_downloaded)
        w.known.connect(self.on_known)
        w.done.connect(self.on_done)
        w.start()
    def cancel(self):
        if self.busy:
            self.worker.cancel()
            self.stop.setEnabled(False)
            self.summary.setText("Cancelling…")
    def on_meta(self, name):
        self._meta = name
    def on_queue(self, entries):
        self.queue.add_entries(entries)
        self._pending.update({e["idx"]: e for e in entries})
        self.bar.setRange(0, max(len(entries), 1))
        self.bar.setValue(0)
        if not entries:
            self.queue.reset_hint()
    def _counts(self):
        st = [r.state for r in self.queue.rows.values()]
        return st.count("done"), st.count("failed") + st.count("cancelled"), st.count("skipped"), len(st)
    def _bar_to(self, v):
        if T.reduce:
            self.bar.setValue(v)
            return
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        a = getattr(self, "_bar_anim", None)
        if a is None:
            a = self._bar_anim = QPropertyAnimation(self.bar, b"value", self)
            a.setDuration(380)
            a.setEasingCurve(QEasingCurve.OutCubic)
        a.stop()
        a.setStartValue(self.bar.value())
        a.setEndValue(v)
        a.start()
    def on_progress(self, i, n):
        ok, bad, skip, total = self._counts()
        fin = ok + bad + skip
        self.bar.setRange(0, max(total, 1))
        self._bar_to(min(fin, total))
        self.summary.setText(f"{fin} of {total} finished" if total else "")
    def on_done(self, ok, bad, skipped):
        ok, bad, skipped, total = self._counts()
        parts = [f"{ok} added"] + ([f"{skipped} already in library"] if skipped else []) + ([f"{bad} failed"] if bad else [])
        self.summary.setText("Done: " + ", ".join(parts) + ".")
        self.logbox.appendPlainText(f"Done: {ok} imported, {skipped} duplicate(s) skipped, {bad} failed.")
        self.go.setEnabled(True)
        self.stop.hide()
        self.bar.setRange(0, 1)
        self._bar_to(1 if (ok or skipped) else 0)
        self.play_all.setVisible(bool(self._tids))
        self.win.refresh_all()
        self.refresh_playlists_keep()
        self.retry.setVisible(bad > 0)
        if self._retry_wait:
            wait, self._retry_wait = self._retry_wait, []
            self._do_retry(wait)
    def retry_rows(self, idxs):
        """refaz as faixas que falharam ou foram canceladas"""
        idxs = [i for i in idxs if i in self.queue.rows and self.queue.rows[i].retryable and self._pending.get(i, {}).get("url")]
        if not idxs:
            return
        if self.busy:  # já tem download rodando: entra na vez, a linha mostra "Waiting"
            for i in idxs:
                if i not in self._retry_wait:
                    self._retry_wait.append(i)
                    self.queue.rows[i].set_state("queued")
            return
        self._do_retry(idxs)
    def _do_retry(self, idxs):
        idxs = [i for i in idxs if i in self.queue.rows and self._pending.get(i, {}).get("url")]
        if not idxs or self.busy:
            return
        text = "\n".join(self._pending[i]["url"] for i in idxs)
        for i in idxs:
            self.queue.remove(i)
            self._pending.pop(i, None)
        self.start_links(text, self._newpid or self.target, keep=True)
    def retry_failed(self):
        self.retry_rows([i for i, r in self.queue.rows.items() if r.retryable])
    def refresh_playlists_keep(self):
        cur = self.dest.currentData()
        self.refresh()
        if cur and cur != "__new__":
            self.dest.setCurrentIndex(max(self.dest.findData(cur), 0))
    def on_log(self, m):
        self.logbox.appendPlainText(m)
        if m.startswith(("Failed", "Could not")):
            self.win.log_error(m)
    def _playlist(self):
        if self.target == "__new__":
            if not self._newpid:
                self._newpid = self.win.lib.create_playlist(self._meta or "Imported playlist")
            return self._newpid
        return self.target
    def _add_to_target(self, tid):
        if tid is None:
            return
        pid = self._playlist()
        if pid:
            self.win.lib.add_to_playlist(pid, tid)
    def on_known(self, it):
        tid = it.get("track_id")
        if tid is None and it.get("source"):
            r = self.win.lib.find_source(it["source"], it["id"])
            tid = r["id"] if r else None
        self._add_to_target(tid)
        if tid is not None and tid not in self._tids:
            self._tids.append(tid)
    def add_downloaded(self, it, path):
        tid, _ = self.win.lib.add_track(it["title"], it["artist"], it.get("album", ""), it["duration"], path=path,
                                        source=it["source"], source_id=it["id"], cover=it.get("cover"))
        if it.get("cover"):
            self.win.lib.set_cover(tid, it["cover"])
        self._add_to_target(tid)
        self._tids.append(tid)
        row = self.queue.rows.get(it.get("idx"))
        if row is not None:
            row.title, row.artist = it["title"], it["artist"]
            row.set_done(tid, it.get("cover"))
    def play_one(self, tid):
        t = self.win.lib.get_track(tid)
        if t:
            self.win.play_list([t], 0)
    def play_imported(self):
        rows = [r for r in (self.win.lib.get_track(t) for t in self._tids) if r]
        if rows:
            self.win.play_list(rows, 0)
