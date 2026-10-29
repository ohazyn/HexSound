import time
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QTimer, QSize, QPropertyAnimation
from PySide6.QtGui import QShortcut, QKeySequence, QIcon, QPixmap
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                               QStackedWidget, QPushButton, QApplication, QLineEdit, QSystemTrayIcon, QMenu,
                               QGraphicsOpacityEffect, QSizePolicy)
from hexsound.app.paths import resource
from hexsound.importers.files import FileImportWorker
from hexsound.importers.links import classify
from hexsound.player.engine import Engine
from hexsound.player.queue import PlayQueue
from hexsound.ui.home import HomePage, CoverLabel
from hexsound.ui.now_playing import NowPlaying
from hexsound.ui.pages import (TrackPage, GroupPage, SearchPage, PlaylistsPage, ImportPage, CreditsPage, fmt)
from hexsound.ui.settings_page import SettingsPage
from hexsound.ui.titlebar import TitleBar
from hexsound.ui.queue_panel import QueuePanel
from hexsound.ui import icons
from hexsound.ui.dialogs import GlassMenu
from hexsound.ui.style import build_qss, T
from hexsound.ui.background import bg
from hexsound.ui.nowstate import now
from hexsound.ui.widgets import Backdrop, GlassPanel, GlassButton, GlassSlider, LogoButton, NavButton, PopupMenu, ambient

NAV_ICONS = {"Home": "house", "Search": "search", "Library": "library", "Albums": "disc",
             "Playlists": "list-music",
             "Import Music": "upload", "Settings": "settings", "Credits": "info"}
MENU = [("Import Music", "upload", "Import music", "Files, folders or links"),
        ("Settings", "settings", "Settings", "Playback, audio, appearance"),
        None,
        ("Credits", "info", "Credits", "About HexSound")]
NAV = ["Home", "Search", "Library", "Albums", "Playlists"]

class MainWindow(QMainWindow):
    def __init__(self, lib, settings):
        super().__init__()
        self.lib, self.settings = lib, settings
        self.error_log, self._quitting, self._pos, self._imp = [], False, 0, None
        T.configure(name=settings["theme"], accent=settings["accent"], glass=settings["glass"], reduce=settings["reduce_effects"], custom=settings["accent_custom"])
        ambient.color = T.accent
        bg.configure(mode=settings["bg_mode"], color=settings["bg_color"], path=settings["bg_image"], blur=settings["bg_blur"], dim=settings["bg_dim"], animate=settings["bg_animate"])
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
        self.setWindowTitle("HexSound")
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon(str(resource("assets/icon.png"))))
        self.setStyleSheet(build_qss())
        self.engine, self.queue, self.cur = Engine(), PlayQueue(), None
        now.reset()
        root = self.root = Backdrop()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 0, 14, 14)
        outer.setSpacing(8)
        self.tbar = TitleBar(self)
        outer.addWidget(self.tbar)
        self._hist, self._hi = [], -1
        root.setMouseTracking(True)
        root.mouseMoveEvent = self._edge_hover
        root.mousePressEvent = self._edge_press
        body = QHBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body, 1)
        side = GlassPanel(26, "sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 16, 14, 14)
        sl.setSpacing(8)
        self.logo = LogoButton(resource("assets/logo.png"))
        self.logo.clicked.connect(self.open_menu)
        sl.addWidget(self.logo)
        sl.addSpacing(4)
        self.menu = PopupMenu(self, MENU)
        self.menu.chosen.connect(self.go_page)
        self.page = {"Home": HomePage(self), "Search": SearchPage(self), "Library": TrackPage(self, "Library"),
                     "Albums": GroupPage(self, "album", "Albums"),
                     "Playlists": PlaylistsPage(self), "Import Music": ImportPage(self),
                     "Settings": SettingsPage(self), "Credits": CreditsPage()}
        self.nav = {}
        for name in NAV:
            b = self.nav[name] = NavButton(name, NAV_ICONS[name])
            b.clicked.connect(lambda _=False, n=name: self.go_page(n))
            sl.addWidget(b)
        sl.addStretch()
        body.addWidget(side)
        content = GlassPanel(26, "content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(22, 20, 14, 14)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack)
        for p in self.page.values():
            self.stack.addWidget(p)
        body.addWidget(content, 1)
        self.qpanel = QueuePanel(self)
        body.addWidget(self.qpanel)
        self._vsave = QTimer(self, singleShot=True, interval=600, timeout=self.settings.save)
        self._build_player(outer)
        self.np = NowPlaying(self)
        self._wire()
        self._wire_titlebar()
        self._build_tray()
        self.page["Settings"].attach()
        from hexsound.ui.dialogs import EditMenuFilter
        self._editf = EditMenuFilter(self)
        QApplication.instance().installEventFilter(self._editf)
        self._set_playable(False)
        self.lib.check_availability()
        self.go_page("Home")
        self.restore_session()

    def open_menu(self):
        if time.monotonic() - self.menu.closed_at < 0.25:
            return  # o clique que fechou o popup não reabre
        self.menu.popup_below(self.logo)
    def _build_player(self, outer):
        bar = self.bar = GlassPanel(28, "player")
        bar.setFixedHeight(100)
        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 10, 18, 10)
        h.setSpacing(16)
        mk = lambda ic, tip, kind="ghost", size=38, **kw: GlassButton("", ic, kind, size=size, tooltip=tip, **kw)
        # esquerda: capa, título, favorito
        left = QWidget()
        lh = QHBoxLayout(left)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(12)
        self.bar_cover = CoverLabel(66, 14)
        lh.addWidget(self.bar_cover)
        info = QVBoxLayout()
        info.setSpacing(1)
        info.addStretch()
        self.title = QPushButton("Nothing playing")
        self.title.setObjectName("titlebtn")
        self.title.setCursor(Qt.PointingHandCursor)
        self.title.setStyleSheet("QPushButton{background:transparent;border:none;text-align:left;font-weight:600;font-size:14px;padding:0;}"
                                 "QPushButton:hover{text-decoration:underline;}")
        self.artist = QLabel("", objectName="muted")
        info.addWidget(self.title)
        info.addWidget(self.artist)
        info.addStretch()
        lh.addLayout(info, 0)
        self.btn = {}
        self.btn["fav"] = mk("heart", "Add to favorites")
        self.btn["fav"].setCheckable(True)
        lh.addWidget(self.btn["fav"])
        lh.addStretch()
        left.setMinimumWidth(290)
        h.addWidget(left, 1)
        # centro: controles + progresso
        mid = QVBoxLayout()
        mid.setSpacing(2)
        ctl = QHBoxLayout()
        ctl.setSpacing(10)
        ctl.addStretch()
        self.btn["shuf"] = mk("shuffle", "Shuffle (Ctrl+S)")
        self.btn["shuf"].setCheckable(True)
        self.btn["prev"] = mk("skip-back", "Previous (Ctrl+Left)", icon_size=20)
        self.btn["prev"].set_fill(True)
        self.btn["play"] = mk("play", "Play (Space)", "primary", 46, icon_size=20)
        self.btn["play"].set_fill(True)
        self.btn["next"] = mk("skip-forward", "Next (Ctrl+Right)", icon_size=20)
        self.btn["next"].set_fill(True)
        self.btn["rep"] = mk("repeat", "Repeat: off (Ctrl+R)")
        self.btn["rep"].setCheckable(True)
        for k in ("shuf", "prev", "play", "next", "rep"):
            ctl.addWidget(self.btn[k])
        ctl.addStretch()
        mid.addLayout(ctl)
        prog = QHBoxLayout()
        prog.setSpacing(8)
        self.t_cur = QLabel("0:00", objectName="time")
        self.t_tot = QLabel("0:00", objectName="time")
        self.t_cur.setFixedWidth(40)
        self.t_cur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.t_tot.setFixedWidth(40)
        self.seek = GlassSlider()
        prog.addWidget(self.t_cur)
        prog.addWidget(self.seek, 1)
        prog.addWidget(self.t_tot)
        mid.addLayout(prog)
        mw = QWidget()
        mw.setLayout(mid)
        mw.setMaximumWidth(640)
        # mw cresce até 640px e fica no meio da coluna central
        center = QWidget()
        ch = QHBoxLayout(center)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.addStretch(1)
        ch.addWidget(mw, 100)
        ch.addStretch(1)
        h.addWidget(center, 2)
        # direita: fila e volume
        right = QHBoxLayout()
        right.setSpacing(6)
        right.addStretch()
        self.btn["queue"] = mk("list-music", "Queue")
        self.btn["vol"] = mk("volume-2", "Mute")
        self.vol = GlassSlider()
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(110)
        self._pre_mute = 70
        right.addWidget(self.btn["queue"])
        right.addWidget(self.btn["vol"])
        right.addWidget(self.vol)
        rw = QWidget()
        rw.setLayout(right)
        rw.setMinimumWidth(290)  # mesma largura mínima da esquerda: o centro fica no meio da janela
        h.addWidget(rw, 1)
        outer.addWidget(bar)

    def _wire(self):
        b, e = self.btn, self.engine
        b["play"].clicked.connect(self._on_play_click)
        b["next"].clicked.connect(lambda: self.go(self.queue.next()))
        b["prev"].clicked.connect(lambda: self.go(self.queue.previous()))
        b["shuf"].toggled.connect(self.set_shuffle)
        b["rep"].clicked.connect(self.cycle_repeat)
        for w in (self.bar_cover, self.title):
            w.clicked.connect(self.show_np)
        b["queue"].setCheckable(True)
        b["queue"].clicked.connect(lambda: self.qpanel.toggle() if b["queue"].isChecked() != self.qpanel._open else None)
        b["fav"].clicked.connect(self.toggle_fav)
        b["vol"].clicked.connect(self.toggle_mute)
        self.vol.valueChanged.connect(self._on_volume)
        self.vol.setValue(int(self.settings["volume"]))
        self._on_volume(self.vol.value())
        self.seek.sliderMoved.connect(e.seek)
        e.set_device(self.settings["audio_device"])
        e.position.connect(self._on_pos)
        e.duration.connect(lambda ms: (self.seek.setRange(0, ms), self.t_tot.setText(fmt(ms / 1000))))
        e.state.connect(self._on_state)
        e.finished.connect(lambda: self.go(self.queue.next(auto=True)))
        e.error.connect(lambda m: (self.title.setText(f"Playback error: {m}"), self.log_error(m)))
        sc = lambda keys, fn: [QShortcut(QKeySequence(k), self, activated=fn) for k in keys]
        sc([Qt.Key_Space, Qt.Key_MediaTogglePlayPause, Qt.Key_MediaPlay], e.toggle)
        sc(["Ctrl+Right", Qt.Key_MediaNext], b["next"].click)
        sc(["Ctrl+Left", Qt.Key_MediaPrevious], b["prev"].click)
        sc(["Ctrl+Up"], lambda: self.vol.setValue(min(100, self.vol.value() + 5)))
        sc(["Ctrl+Down"], lambda: self.vol.setValue(max(0, self.vol.value() - 5)))
        sc(["Ctrl+S"], b["shuf"].click)
        sc(["Ctrl+R"], b["rep"].click)
        sc(["Ctrl+F"], self.focus_search)
        sc(["Ctrl+V"], self.paste)
        sc(["Ctrl+Q"], self.quit_app)

    def _set_playable(self, on):
        for k in ("play", "prev", "next", "fav"):
            self.btn[k].setEnabled(on)
        self.seek.setEnabled(on)
    def _on_play_click(self):
        was = self.btn["play"]._icon == "pause"
        self.btn["play"].set_icon("play" if was else "pause")  # vira na hora; o estado real confirma
        self.engine.toggle()
        QTimer.singleShot(700, self._sync_play_icon)
    def _sync_play_icon(self):
        self.btn["play"].set_icon("pause" if now.playing else "play")
    def _on_state(self, playing):
        self.btn["play"].set_icon("pause" if playing else "play")
        self.btn["play"].setToolTip("Pause (Space)" if playing else "Play (Space)")
        now.set_playing(playing)
    def _on_volume(self, v):
        self.engine.volume(v)
        self.settings.data["volume"] = v
        self._vsave.start()
        self.btn["vol"].set_icon("volume-x" if v == 0 else "volume-1" if v < 50 else "volume-2")
        self.btn["vol"].setToolTip("Unmute" if v == 0 else "Mute")
    def toggle_mute(self):
        if self.vol.value() > 0:
            self._pre_mute = self.vol.value()
            self.vol.setValue(0)
        else:
            self.vol.setValue(self._pre_mute or 70)
    def _update_repeat(self):
        r = self.queue.repeat
        b = self.btn["rep"]
        b.set_icon("repeat-1" if r == "one" else "repeat")
        b.setChecked(r != "off")
        b.setToolTip({"off": "Repeat: off", "all": "Repeat: all", "one": "Repeat: current track"}[r] + " (Ctrl+R)")
    def _update_fav(self):
        on = bool(self.cur and self.cur["favorite"])
        b = self.btn["fav"]
        b.setChecked(on)
        b.set_fill(on)
        b.setToolTip("Remove from favorites" if on else "Add to favorites")
    def go_page(self, name, hist=True):
        if hist and not (self._hist and self._hist[self._hi] == name):
            self._hist = self._hist[:self._hi + 1] + [name]
            self._hi = len(self._hist) - 1
        self.tbar.back.setEnabled(self._hi > 0)
        self.tbar.fwd.setEnabled(self._hi < len(self._hist) - 1)
        self.stack.setCurrentWidget(self.page[name])
        self.refresh_all()
        w = self.stack.currentWidget()
        for n, b in self.nav.items():
            b.set_active(n == name)
        self.logo.set_active(name not in self.nav)
        if T.reduce:
            return
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", w)
        a.setDuration(220)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.finished.connect(lambda w=w: w.setGraphicsEffect(None))
        a.start()
        self._fade = a

    def apply_background(self, persist=True, **kw):
        if persist:
            for k, v in kw.items():
                self.settings.data[k] = v
            self.settings.save()
        bg.configure(mode=kw.get("bg_mode"), color=kw.get("bg_color"), path=kw.get("bg_image"), blur=kw.get("bg_blur"), dim=kw.get("bg_dim"), animate=kw.get("bg_animate"))
    def apply_look(self, accent=None, glass=None, reduce=None, persist=True, custom=None):
        T.configure(accent=accent, glass=glass, reduce=reduce, custom=custom)
        if persist:
            for k, v in (("accent", accent), ("glass", glass), ("reduce_effects", reduce)):
                if v is not None:
                    self.settings.data[k] = v
            self.settings.save()
        self.setStyleSheet(build_qss())
        self._dark_titlebar()
        ambient.set_from_cover(self.cur["cover"]) if self.cur else ambient.glide(T.accent)
        for w in self.findChildren(QWidget):
            w.update()
        self.np.update()
    def _dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            v = ctypes.c_int(1 if T.dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)  # cantos arredondados (Win 11)
        except Exception:
            pass
    def showEvent(self, e):
        super().showEvent(e)
        self._dark_titlebar()
        bg.set_paused(self.isMinimized())
    def hideEvent(self, e):
        super().hideEvent(e)
        bg.set_paused(True)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self._tray_menu = GlassMenu()
        for ic, t, fn in [("house", "Show HexSound", self.show_window), ("play", "Play / Pause", self.engine.toggle),
                          ("skip-forward", "Next", self.btn["next"].click), ("skip-back", "Previous", self.btn["prev"].click), ("x", "Quit", self.quit_app)]:
            self._tray_menu.act(ic, t, fn)
        self.tray.setContextMenu(self._tray_menu)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.Trigger else None)
        self.update_tray()

    def update_tray(self):
        self.tray.show() if self.settings["tray"] and QSystemTrayIcon.isSystemTrayAvailable() else self.tray.hide()
    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
    def quit_app(self):
        self._quitting = True
        self.close()
    def closeEvent(self, e):
        self.save_session()
        if self.settings["tray"] and self.tray.isVisible() and not self._quitting:
            e.ignore()
            self.hide()
            return
        self.settings.save()
        e.accept()
        QApplication.quit()
    def apply_theme(self, name):
        self.settings.set("theme", name)
        T.configure(name=name)
        self.apply_look(persist=False)
    def log_error(self, msg):
        self.error_log = (self.error_log + [f"{time.strftime('%H:%M:%S')} {msg}"])[-100:]
    def focus_search(self):
        self.tbar.search.setFocus()
        self.tbar.search.selectAll()
    def step(self, d):
        i = self._hi + d
        if 0 <= i < len(self._hist):
            self._hi = i
            self.go_page(self._hist[i], hist=False)
    def _wire_titlebar(self):
        t = self.tbar
        t.back.clicked.connect(lambda: self.step(-1))
        t.fwd.clicked.connect(lambda: self.step(1))
        self.page["Search"].q.hide()
        t.search.textChanged.connect(self._global_search)
        t.search.returnPressed.connect(lambda: self.go_page("Search"))
        QShortcut(QKeySequence("Alt+Left"), self, activated=t.back.click)
        QShortcut(QKeySequence("Alt+Right"), self, activated=t.fwd.click)
    def _global_search(self, text):
        self.page["Search"].q.setText(text)
        if text.strip() and self.stack.currentWidget() is not self.page["Search"]:
            self.go_page("Search")

    def _edges(self, pos):
        if self.isMaximized():
            return Qt.Edges()
        m, e = 7, Qt.Edges()
        w, h = self.root.width(), self.root.height()
        if pos.x() < m:
            e |= Qt.LeftEdge
        if pos.x() > w - m:
            e |= Qt.RightEdge
        if pos.y() < m:
            e |= Qt.TopEdge
        if pos.y() > h - m:
            e |= Qt.BottomEdge
        return e
    def _edge_hover(self, ev):
        e = self._edges(ev.position().toPoint())
        L, R, T_, B = Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge
        c = (Qt.SizeFDiagCursor if e in (L | T_, R | B) else Qt.SizeBDiagCursor if e in (R | T_, L | B)
             else Qt.SizeHorCursor if e in (L, R) else Qt.SizeVerCursor if e in (T_, B) else Qt.ArrowCursor)
        self.root.setCursor(c)
    def _edge_press(self, ev):
        e = self._edges(ev.position().toPoint())
        if ev.button() == Qt.LeftButton and e and self.windowHandle():
            self.windowHandle().startSystemResize(e)
    def changeEvent(self, ev):
        if ev.type() == ev.Type.WindowStateChange:
            self.tbar.set_maximized(self.isMaximized())
            bg.set_paused(self.isMinimized())
        super().changeEvent(ev)

    def save_session(self):
        q = self.queue
        self.settings.set("session", {"items": q.items, "order": q.order, "pos": q.pos, "shuffle": q.shuffle,
                                      "repeat": q.repeat, "position": self._pos})
    def restore_session(self):
        s, q = self.settings["session"], self.queue
        try:
            if not s or not self.settings["resume"] or not s["items"]:
                return
            n = len(s["items"])
            if sorted(s["order"]) != list(range(n)) or not (0 <= s["pos"] < n) or not all(isinstance(i, int) for i in s["items"]):
                return
            q.items, q.order, q.pos, q.shuffle, q.repeat = s["items"], s["order"], s["pos"], bool(s["shuffle"]), s["repeat"]
            self.set_shuffle(q.shuffle)
            self._update_repeat()
            t = self.lib.get_track(q.current)
            if t and t["path"] and Path(t["path"]).exists():
                self.go(q.current, autoplay=False, start=int(s.get("position", 0)), count=False)
        except Exception as ex:
            self.log_error(f"Could not restore session: {ex}")

    def _on_pos(self, ms):
        self._pos = ms
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self.t_cur.setText(fmt(ms / 1000))
    def play_list(self, rows, start, ctx=None):
        """ctx = de onde veio, ex. ("playlist", id)"""
        now.set_ctx(ctx)
        self.queue.set_tracks([r["id"] for r in rows], start)
        self.go(self.queue.current)
    def play_row(self, rows, i, ctx=None, shuffle=None):
        if not (0 <= i < len(rows)):
            return
        if self.cur and rows[i]["id"] == now.track_id:
            self.engine.toggle()
            return
        if shuffle is not None:
            self.set_shuffle(shuffle)
        self.play_list(rows, i, ctx)
    def toggle_context(self, ctx, rows, shuffle=False):
        if self.cur and now.is_ctx(ctx):
            self.engine.toggle()
            return
        if rows:
            self.set_shuffle(shuffle)
            self.play_list(rows, 0, ctx)
    def jump(self, qpos):
        self.go(self.queue.jump(qpos))
    def go(self, tid, autoplay=True, start=0, count=True):
        if tid is None:
            return
        t = self.lib.get_track(tid)
        if not t or not t["path"] or not Path(t["path"]).exists():
            self.title.setText("File unavailable — skipping")
            self.log_error(f"Missing file: {t['path'] if t else tid}")
            self.lib.check_availability()
            return self.go(self.queue.next()) if self.queue.upcoming() else None
        self.cur = t
        now.set_track(tid)
        self.engine.load(t["path"], autoplay, start)
        if count:
            self.lib.mark_played(tid)
        self.title.setText(t["title"])
        self.artist.setText(t["artist"])
        self._update_fav()
        self.bar_cover.set_cover(t["cover"])
        ambient.set_from_cover(t["cover"])
        self._set_playable(True)
        if self.np.isVisible():
            self.np.refresh()
        if autoplay and self.settings["notify"] and self.tray.isVisible() and not self.isActiveWindow():
            self.tray.showMessage(t["title"], t["artist"], self.windowIcon(), 3000)
    def show_np(self):
        self.np.open_sheet()
    def set_shuffle(self, on):
        self.queue.set_shuffle(on)
        self.btn["shuf"].blockSignals(True)
        self.btn["shuf"].setChecked(on)
        self.btn["shuf"].blockSignals(False)
        self.btn["shuf"].setToolTip(f"Shuffle: {'on' if on else 'off'} (Ctrl+S)")
    def cycle_repeat(self):
        q = self.queue
        q.repeat = {"off": "all", "all": "one", "one": "off"}[q.repeat]
        self._update_repeat()
    def toggle_fav(self):
        if self.cur:
            self.lib.set_favorite(self.cur["id"], not self.cur["favorite"])
            self.cur = self.lib.get_track(self.cur["id"])
            self._update_fav()
            self.refresh_all()

    def refresh_all(self):
        w = self.stack.currentWidget()
        if hasattr(w, "refresh"):
            w.refresh()
    def import_paths(self, paths):
        pls = [p for p in paths if p.lower().endswith(".hexplaylist")]
        for p in pls:
            self.page["Playlists"].import_file(p)
        rest = [p for p in paths if p not in pls]
        if not rest or (self._imp and self._imp.isRunning()):
            return
        self._added = self._seen = 0
        w = self._imp = FileImportWorker(rest)
        w.found.connect(self._on_found)
        w.done.connect(self._on_import_done)
        w.start()
        self.page["Import Music"].status.setText("Reading files…")
    def _on_found(self, f, tags, cover):
        tid, new = self.lib.add_track(path=f, **tags)
        self._added += new
        self._seen += 1
        if cover:
            self.lib.set_cover(tid, cover)
        self.page["Import Music"].status.setText(f"Importing… {self._seen} file(s) read, {self._added} new.")
    def _on_import_done(self, total):
        self.page["Import Music"].status.setText(f"Imported {self._added} new track(s); {total - self._added} already in the library.")
        self.refresh_all()
    def paste(self):
        if isinstance(QApplication.focusWidget(), QLineEdit):
            return
        md = QApplication.clipboard().mimeData()
        if md.hasUrls():
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if paths:
                return self.import_paths(paths)
        if md.hasText() and classify(md.text().strip()) != "unknown":
            self.go_page("Import Music")
            self.page["Import Music"].link.setText(md.text().strip())
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
    def dropEvent(self, e):
        self.import_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
