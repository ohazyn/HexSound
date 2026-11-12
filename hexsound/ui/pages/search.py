"""Tela Search: busca de faixas e playlists."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget
import time
from hexsound.app.paths import DATA_DIR
from hexsound.importers.online import OnlineSearch, ThumbFetch, PreviewFetch
from hexsound.importers.worker import LinkWorker
from hexsound.ui import icons
from hexsound.ui.style import T
from hexsound.ui.widgets import SearchField, GlassCombo
from hexsound.ui.pages.rows import TrackTable, show_track_menu
from hexsound.ui.pages.common import h1, gbtn
from hexsound.ui.pages.online import OnlineResults, BUTTON

BUTTON_STATES = set(BUTTON)

def _dim_icon(name, size, alpha=0.4):
    from PySide6.QtGui import QPixmap
    src = icons.icon(name, T.fg.name(), size).pixmap(size, size)
    out = QPixmap(src.size())
    out.fill(Qt.transparent)
    q = QPainter(out)
    q.setOpacity(alpha)
    q.drawPixmap(0, 0, src)
    q.end()
    return out

class SearchPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(h1("Search"))
        self.q = SearchField("Songs, artists, albums and playlists")
        self._deb = QTimer(self, singleShot=True, interval=180, timeout=self.refresh)  # espera parar de digitar
        self.q.textChanged.connect(lambda _t: self._deb.start())
        self.src = GlassCombo()
        for name, mode in (("Songs", "songs"), ("YouTube Music", "ytmusic"), ("SoundCloud", "soundcloud"), ("All videos", "all")):
            self.src.addItem(name, mode)
        self.src.setToolTip("Songs: YouTube Music + SoundCloud (no lessons or long videos).\nAll videos: everything YouTube and SoundCloud return.")
        self.go = gbtn("Search online", "search", "accent", tip="Search online (Enter)")
        top = QHBoxLayout()
        top.addWidget(self.q, 1)
        top.addStretch(1)  # a caixa daqui fica escondida (a de cima manda): empurra seletor e botão para a direita
        self.src.setMinimumWidth(150)
        top.addWidget(self.src)
        top.addWidget(self.go)
        lay.addLayout(top)
        self.q.returnPressed.connect(self.search_online)
        self.go.clicked.connect(self.search_online)
        self._svc, self._thumbs = OnlineSearch(self), ThumbFetch(self)
        self._pf = PreviewFetch(self)
        self._pf.ready.connect(self._preview_ready)
        self.prev, self._pv_uid, self._pv_token, self._pv_resume, self._pv_t0 = None, None, 0, False, 0.0  # player à parte só para as prévias
        self._svc.results.connect(self._online_done)
        self._thumbs.loaded.connect(self._thumb_loaded)
        self._token, self._next_uid = 0, 0
        self._uids, self._items, self._st, self._tids = {}, {}, {}, {}  # uid por (fonte, id); resultado; (estado, %, msg); id na biblioteca
        self._queue, self._cur, self._dl, self._workers = [], None, None, []
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignCenter)
        el.setSpacing(10)
        self.hint_ic = QLabel()
        self.hint_ic.setAlignment(Qt.AlignCenter)
        self.hint_ic.setPixmap(_dim_icon("search", 44))
        self.hint = QLabel("", objectName="muted")
        self.hint.setAlignment(Qt.AlignCenter)
        el.addWidget(self.hint_ic)
        el.addWidget(self.hint)
        lay.addWidget(self.empty, 1)
        self.table = TrackTable()
        lay.addWidget(self.table, 3)
        self.online = OnlineResults()
        self.online.add.connect(self.add_online)
        self.online.play.connect(self.play_online)
        self.online.preview.connect(self.preview_online)
        lay.addWidget(self.online, 4)
        self.pl_title = QLabel("Playlists", objectName="h2")
        lay.addWidget(self.pl_title)
        self.pl = QListWidget()
        lay.addWidget(self.pl)
        self.table.cellDoubleClicked.connect(lambda r, _c: win.play_list(self.table.rows, r))
        self.table.play_row.connect(lambda r: win.play_row(self.table.rows, r))
        self.table.customContextMenuRequested.connect(lambda p: show_track_menu(win, self.table, p))
        self.pl.itemDoubleClicked.connect(self.play_pl)
        self.pids = []
        self.refresh()
    def refresh(self, *_):
        q = self.q.text().strip()
        rows = self.win.lib.tracks(q) if q else []
        self.table.fill(rows)
        ps = [p for p in self.win.lib.playlists() if q and (q.lower() in p["name"].lower() or q.lower() in (p["description"] or "").lower())]
        self.pids = [p["id"] for p in ps]
        self.pl.clear()
        [self.pl.addItem(p["name"]) for p in ps]
        self.table.setVisible(bool(rows))
        self.pl_title.setVisible(bool(ps))
        self.pl.setVisible(bool(ps))
        self.pl.setMaximumHeight(130 if rows else 16777215)
        self.empty.setVisible(not rows and not ps and not self.online.active)
        self.hint.setText(f"No results for “{q}” in your library.\nPress Enter to search YouTube and SoundCloud." if q
                          else "Search your library, or press Enter to find songs on YouTube and SoundCloud")
        if not q and self.online.active and not self._busy():
            self.online.reset()  # campo vazio e nada baixando: some com os resultados online
        self.hint_ic.setPixmap(_dim_icon("search", 44))
    # ---- busca online -------------------------------------------------------------------------
    def _busy(self):
        return bool(self._queue) or self._dl is not None
    def search_online(self):
        q = self.q.text().strip()
        if not q:
            return
        self._token += 1
        self.online.show_loading("Searching…")
        self.empty.hide()
        self._svc.search(self._token, q, self.src.currentData())
    def _online_done(self, token, results, errors):
        if token != self._token:
            return  # chegou depois de uma busca mais nova
        lib, items, thumbs = self.win.lib, [], []
        for r in results:
            key = (r["source"], r["id"])
            uid = self._uids.get(key)
            if uid is None:
                uid = self._uids[key] = self._next_uid
                self._next_uid += 1
            self._items[uid] = r
            have = lib.find_source(*key)
            if have:
                self._tids[uid] = have["id"]
                r["in_library"] = True
                self._st[uid] = ("done", 100.0, "")
            st = self._st.get(uid, ("idle", 0.0, ""))
            items.append((uid, r, *st))
            if r.get("thumb"):
                thumbs.append((uid, r["thumb"]))
        if results:
            status = f"{len(results)} result{'s' if len(results) != 1 else ''} · press Add to download"
        elif errors:
            status = "Could not search: " + errors[0] + " — check your connection and try again."
        else:
            status = "Nothing found. Try other words."
        self.stop_preview()
        self.online.set_results(items, status)
        self.empty.hide()
        self._thumbs.fetch(thumbs)
    # ---- prévia (30 s, num player separado; a música da biblioteca pausa e volta no fim) --------------
    def preview_online(self, uid):
        if self._pv_uid == uid:
            self.stop_preview()  # segundo clique no mesmo botão: para
            return
        if uid not in self._items:
            return
        self.stop_preview()
        self._pv_uid, self._pv_token, self._pv_t0 = uid, self._pv_token + 1, time.monotonic()
        self._set_preview(uid, "loading")
        self._pf.fetch(self._pv_token, uid, self._items[uid], DATA_DIR / "previews")
    def _set_preview(self, uid, state):
        row = self.online.rows.get(uid)
        if row is not None:
            row.set_preview(state)
    def _preview_ready(self, token, uid, path, err):
        if token != self._pv_token or uid != self._pv_uid:
            return  # cancelada ou substituída por outra
        if err:
            self._pv_uid = None
            self._set_preview(uid, "idle")
            self.online.set_status(f"Preview failed: {err}")
            return
        from hexsound.player import engine as E
        from hexsound.ui.nowstate import now
        if self.prev is None:
            self.prev = E.Engine()
            self.prev.finished.connect(self.stop_preview)
        self._pv_resume = bool(now.playing)
        if self._pv_resume:
            self.win.engine.toggle()  # pausa a música que estava tocando
        self.prev.volume(self.win.vol.value())
        self.prev.load(path, autoplay=True)
        self._set_preview(uid, "playing")
        self.online.set_status(f"Playing a 30 s preview · loaded in {time.monotonic() - self._pv_t0:.0f} s")
    def stop_preview(self, resume=True):
        uid, self._pv_uid = self._pv_uid, None
        self._pv_token += 1
        if self.prev is not None:
            self.prev.stop()
        if uid is not None:
            self._set_preview(uid, "idle")
        if self._pv_resume:
            self._pv_resume = False
            from hexsound.ui.nowstate import now
            if resume and not now.playing:
                self.win.engine.toggle()  # a música volta de onde parou
    def hideEvent(self, e):
        super().hideEvent(e)
        self.stop_preview()  # saiu da tela Search
    def _thumb_loaded(self, uid, data):
        row = self.online.rows.get(uid)
        if row is not None:
            row.set_thumb(data)
    def _set_state(self, uid, state, pct=0.0, msg=""):
        self._st[uid] = (state, pct, msg)
        row = self.online.rows.get(uid)
        if row is not None:
            row.set_state(state, pct, msg)
    def add_online(self, uid):
        if uid in self._tids or uid in self._queue or uid == self._cur or uid not in self._items:
            return
        self._set_state(uid, "waiting")
        self._queue.append(uid)
        self._pump()
    def _pump(self):
        self._workers = [w for w in self._workers if not w.isFinished()]  # solta só os que já terminaram
        if self._dl is not None or not self._queue:
            return
        uid = self._cur = self._queue.pop(0)
        r = self._items[uid]
        lib = self.win.lib
        rows = lib.tracks()
        known = {(x["source"], x["source_id"]) for x in rows}
        songs = [(x["id"], x["title"], x["artist"] or "", float(x["duration"] or 0)) for x in rows]
        entry = {k: r.get(k) for k in ("id", "title", "artist", "album", "duration", "url", "source", "thumb")}
        w = self._dl = LinkWorker("", known, self.win.settings["download_dir"], songs, idx_base=uid, entries=[entry])
        self._workers.append(w)
        w.state.connect(self._dl_state)
        w.track.connect(self._dl_track)
        w.known.connect(self._dl_known)
        w.log.connect(self._dl_log)
        w.done.connect(self._dl_done)
        w.start()
    def _dl_state(self, uid, state, pct, msg):
        s = {"skipped": "done", "cancelled": "failed", "searching": "waiting", "queued": "waiting"}.get(state, state)
        if s not in BUTTON_STATES:
            return
        if s == "failed":
            self.online.set_status(f"Download failed: {msg or 'unknown error'}")
        self._set_state(uid, s, pct, msg)
    def _dl_track(self, it, path):
        lib = self.win.lib
        tid, _ = lib.add_track(it["title"], it["artist"], it.get("album", ""), it["duration"], path=path,
                               source=it["source"], source_id=it["id"], cover=it.get("cover"))
        if it.get("cover"):
            lib.set_cover(tid, it["cover"])
        self._tids[it["idx"]] = tid
    def _dl_known(self, it):  # a faixa já estava na biblioteca (mesmo link ou a mesma música)
        tid = it.get("track_id")
        if tid is None and it.get("source"):
            r = self.win.lib.find_source(it["source"], it["id"])
            tid = r["id"] if r else None
        if tid is not None and self._cur is not None:
            self._tids[self._cur] = tid
    def _dl_log(self, m):
        if m.startswith(("Failed", "Could not")):
            self.win.log_error(m)
    def _dl_done(self, ok, bad, skipped):
        uid, self._cur, self._dl = self._cur, None, None
        if uid is not None and uid not in self._tids and self._st.get(uid, ("",))[0] != "failed":
            self._set_state(uid, "failed", 0.0, "Download did not finish")  # o worker caiu sem avisar
        self.win.refresh_all()
        self._pump()
    def play_online(self, uid):
        tid = self._tids.get(uid)
        if tid is None and uid in self._items:
            r = self._items[uid]
            have = self.win.lib.find_source(r["source"], r["id"])
            tid = have["id"] if have else None
        t = self.win.lib.get_track(tid) if tid is not None else None
        if t:
            self.win.play_list([t], 0)
    def play_pl(self, it):
        pid = self.pids[self.pl.row(it)]
        rows = self.win.lib.playlist_tracks(pid)
        if rows:
            self.win.play_list(rows, 0, ctx=("playlist", pid))
