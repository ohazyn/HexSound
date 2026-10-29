"""Tela Playlists: grade, detalhe, edição, exportar/importar."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPainterPath, QColor
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QLineEdit,
    QAbstractItemView, QApplication, QScrollArea, QFrame, QDialog, QStackedWidget)
from hexsound.metadata.tags import save_cover_bytes
from hexsound.playlists import share
from hexsound.ui import icons, dialogs, pickers
from hexsound.ui.dialogs import GlassMenu, NewPlaylistDialog
from hexsound.ui.home import CoverLabel
from hexsound.ui.nowstate import now
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton, PlayFab, SearchField, _anim, _to
from hexsound.ui.pages.common import ROW_ROLE, gbtn, h1
from hexsound.ui.pages.rows import RowDelegate, RowList, TrackGrid

class CoverEdit(CoverLabel):
    def __init__(self, size, radius):
        super().__init__(size, radius)
        self._h = 0.0
        self._a = _anim(self, self._set)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Change cover")
    def _set(self, v):
        self._h = float(v)
        self.update()
    def enterEvent(self, e):
        _to(self._a, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._a, self._h, 0.0)
        super().leaveEvent(e)
    def paintEvent(self, e):
        super().paintEvent(e)
        if self._h > 0.01:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            c = QPainterPath()
            c.addRoundedRect(QRectF(self.rect()), self.r, self.r)
            p.fillPath(c, QColor(0, 0, 0, int(140 * self._h)))
            k = 30
            icons.draw(p, "image", QRectF((self.s - k) / 2, (self.s - k) / 2, k, k), "#ffffff", False, opacity=self._h)

class AddList(QListWidget):
    add = Signal(int)
    def __init__(self):
        super().__init__()
        self.setItemDelegate(RowDelegate(heart=False))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.itemDoubleClicked.connect(lambda it: self.add.emit(it.data(Qt.UserRole)))
    def mousePressEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        if it and e.button() == Qt.LeftButton and e.position().x() > self.viewport().width() - 56:
            self.add.emit(it.data(Qt.UserRole))
            return
        super().mousePressEvent(e)
    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        hov = self.itemAt(self.viewport().mapFromGlobal(self.cursor().pos()))
        for i in range(self.count()):
            r = self.visualItemRect(self.item(i))
            if r.bottom() < 0 or r.top() > self.viewport().height():
                continue
            c = QPointF(r.right() - 26, r.center().y())
            on = self.item(i) is hov and self.viewport().mapFromGlobal(self.cursor().pos()).x() > self.viewport().width() - 56
            p.setPen(Qt.NoPen)
            p.setBrush(T.accent if on else T.ovc(0.14))
            p.drawEllipse(c, 13, 13)
            icons.draw(p, "plus", QRectF(c.x() - 7, c.y() - 7, 14, 14), "#ffffff" if on else T.fg.name())

class PlaylistsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.ids, self.rows, self._pid = win, [], [], None
        self._saved = ("", "")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        g = QWidget()
        gl = QVBoxLayout(g)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(h1("Playlists"))
        head.addStretch()
        imp = gbtn("Import", "download", "glass", "Import a playlist")
        imp.clicked.connect(lambda: self._import_menu(imp))
        head.addWidget(imp)
        nb = gbtn("New playlist", "plus", "accent")
        nb.clicked.connect(lambda _=False: self.new())
        head.addWidget(nb)
        gl.addLayout(head)
        self.grid = TrackGrid()
        gl.addWidget(self.grid)
        self.stack.addWidget(g)
        self.grid.itemClicked.connect(lambda it: self.new() if self.grid.row(it) == 0 else self.open(self.ids[self.grid.row(it) - 1]))
        self.grid.customContextMenuRequested.connect(self._grid_menu)
        d = QWidget()
        dl = QVBoxLayout(d)
        dl.setContentsMargins(0, 0, 10, 12)
        dl.setSpacing(14)
        top = QHBoxLayout()
        top.setSpacing(18)
        self.back = GlassButton("", "arrow-left", "glass", size=36, tooltip="Back to Playlists")
        self.back.clicked.connect(self.close_detail)
        top.addWidget(self.back, 0, Qt.AlignTop)
        self.cover = CoverEdit(150, 12)
        self.cover.clicked.connect(self.set_cover)
        top.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addStretch()
        info.addWidget(QLabel("PLAYLIST", objectName="sectionTitle"))
        self.name = QLineEdit()
        self.name.setObjectName("plName")
        self.name.setPlaceholderText("Playlist title")
        self.name.textChanged.connect(self._mark)
        self.name.returnPressed.connect(lambda: self.save())
        self.name.setStyleSheet("QLineEdit#plName{font-size:34px;font-weight:700;background:transparent;border:1px solid transparent;border-radius:10px;padding:0 6px;}"
                                f"QLineEdit#plName:hover{{background:{T.rgba(0.07)};}} QLineEdit#plName:focus{{background:{T.rgba(0.10)};border:1px solid {T.rgba(0.28)};}}")
        self.desc = QLineEdit()
        self.desc.setObjectName("plDesc")
        self.desc.setPlaceholderText("Add a subtitle")
        self.desc.textChanged.connect(self._mark)
        self.desc.returnPressed.connect(lambda: self.save())
        self.desc.setStyleSheet("QLineEdit#plDesc{background:transparent;border:1px solid transparent;border-radius:10px;padding:2px 6px;}"
                                f"QLineEdit#plDesc:hover{{background:{T.rgba(0.07)};}} QLineEdit#plDesc:focus{{background:{T.rgba(0.10)};border:1px solid {T.rgba(0.28)};}}")
        self.meta = QLabel("", objectName="muted")
        self.meta.setContentsMargins(6, 0, 0, 0)
        info.addWidget(self.name)
        info.addWidget(self.desc)
        info.addWidget(self.meta)
        info.addStretch()
        top.addLayout(info, 1)
        dl.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)
        self.play_big = PlayFab(56, "Play")
        self.play_big.truth = lambda: now.ctx_playing(self.ctx())
        self.play_big.clicked.connect(lambda _=False: self.toggle_play())
        row.addWidget(self.play_big)
        now.changed.connect(self._sync_play)
        shuf = GlassButton("", "shuffle", "ghost", size=42, tooltip="Shuffle play", icon_size=22)
        shuf.clicked.connect(lambda _=False: self.play_from(0, True))
        row.addWidget(shuf)
        more = GlassButton("", "more", "ghost", size=42, tooltip="More options", icon_size=22)
        more.clicked.connect(lambda: self._more_menu(more))
        row.addWidget(more)
        dele = GlassButton("", "trash", "danger", size=42, tooltip="Delete this playlist", icon_size=21)
        dele.clicked.connect(lambda _=False: self.delete())
        row.addWidget(dele)
        self.save_btn = gbtn("Save", "check", "primary", "Save title and subtitle (Enter)")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(lambda _=False: self.save())
        row.addWidget(self.save_btn)
        self.status = QLabel("", objectName="muted")
        self.status.setContentsMargins(6, 0, 0, 0)
        row.addWidget(self.status)
        row.addStretch()
        dl.addLayout(row)
        self.tl = RowList()
        self.tl.setItemDelegate(RowDelegate(num=True, extra=True))
        self.tl.play_row.connect(self.row_play)
        self.tl.setMouseTracking(True)
        self.tl.setFocusPolicy(Qt.NoFocus)
        self.tl.setDragDropMode(QAbstractItemView.InternalMove)
        self.tl.setDefaultDropAction(Qt.MoveAction)
        self.tl.model().rowsMoved.connect(lambda *a: QTimer.singleShot(0, self.on_moved))
        self.tl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tl.customContextMenuRequested.connect(self._track_menu)
        self.tl.itemDoubleClicked.connect(lambda it: self.play_from(self.tl.row(it), self.win.queue.shuffle))
        self.empty = QLabel("This playlist is empty. Add songs below.", objectName="muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.tl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        dl.addWidget(self.tl)
        dl.addWidget(self.empty)
        dl.addStretch(1)  # empurra o botão para o fim da página
        self.build_btn = gbtn("Let’s build your playlist", "plus", "glass")
        self.build_btn.setCheckable(True)
        self.build_btn.toggled.connect(self._toggle_build)
        dl.addWidget(self.build_btn, 0, Qt.AlignLeft)
        self.build = QWidget()
        bl = QVBoxLayout(self.build)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        self.q = SearchField("Search songs to add")
        self.q.textChanged.connect(self.refresh_add)
        bl.addWidget(self.q)
        self.addl = AddList()
        self.addl.add.connect(self.add_track)
        self.addl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bl.addWidget(self.addl)
        self.build.hide()
        dl.addWidget(self.build)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(d)
        self.stack.addWidget(sc)

    @property
    def pid(self):
        return self._pid
    def _toggle_build(self, on):
        self.build.setVisible(on)
        self.build_btn.set_icon("chevron-down" if on else "plus")
        if on:
            self.refresh_add()
            self.q.setFocus()

    def refresh(self):
        pls = self.win.lib.playlists()
        self.ids = [p["id"] for p in pls]
        rows = [{"new": True, "title": "New playlist", "artist": "Create an empty one", "cover": None, "available": 1, "favorite": 0}]
        for p in pls:
            tr = self.win.lib.playlist_tracks(p["id"])
            cnt = f"{len(tr)} track{'s' if len(tr) != 1 else ''}"
            sub = (p["description"] or "").strip()
            rows.append({"title": p["name"], "artist": f"{sub} · {cnt}" if sub else cnt, "cover": p["cover"] or next((t["cover"] for t in tr if t["cover"]), None), "available": 1, "favorite": 0})
        self.grid.rows = rows
        self.grid.clear()
        [self.grid.addItem(QListWidgetItem(r["title"])) for r in rows]
        if self._pid in self.ids:
            self.show_tracks()
            self.refresh_add()
        else:
            self.close_detail()
    def open(self, pid):
        if self._pid and self._pid != pid and self.dirty():
            self.save(silent=True)
        self._pid = pid
        self.stack.setCurrentIndex(1)
        self._load_fields(force=True)
        self.show_tracks()
        self.q.clear()
        self.build_btn.setChecked(not self.rows)
        self.refresh_add()
    def close_detail(self):
        if self.dirty():
            self.save(silent=True)  # sair da tela nunca perde o que você digitou
        self._pid = None
        self.stack.setCurrentIndex(0)
    def hideEvent(self, e):
        if self.dirty():
            self.save(silent=True)
        super().hideEvent(e)

    def _fields(self):
        return (self.name.text().strip(), self.desc.text().strip())
    def dirty(self):
        try:
            return bool(self._pid) and self._fields() != self._saved
        except RuntimeError:
            return False
    def _mark(self, *_):
        d = self.dirty()
        self.save_btn.setEnabled(d)
        self.status.setText("Unsaved changes" if d else ("All changes saved" if self._pid else ""))
    def _load_fields(self, force=False):
        p = self.win.lib.playlist(self._pid) if self._pid else None
        if not p:
            return
        was_clean = self._fields() == self._saved
        new = (p["name"], (p["description"] or "").strip())
        self._saved = new
        if force or was_clean:  # não pisa no que você está digitando
            for w, v in ((self.name, new[0]), (self.desc, new[1])):
                w.blockSignals(True)
                w.setText(v)
                w.blockSignals(False)
        self._mark()
    def save(self, silent=False):
        if not self._pid or not self.win.lib.playlist(self._pid):
            return False
        name, desc = self._fields()
        empty = not name
        if empty:
            name = self._saved[0]
            self.name.blockSignals(True)
            self.name.setText(name)
            self.name.blockSignals(False)
        self.win.lib.rename_playlist(self._pid, name)
        self.win.lib.update_playlist(self._pid, description=desc)
        self._saved = (name, desc)
        self._mark()
        if empty and not silent:
            self.status.setText("A playlist needs a title — kept the old one")
        return True

    def show_tracks(self, *_):
        pid = self._pid
        self.tl.clear()
        if not pid:
            self.rows = []
            return
        p = self.win.lib.playlist(pid)
        self.rows = self.win.lib.playlist_tracks(pid)
        for t in self.rows:
            it = QListWidgetItem(t["title"])
            it.setData(Qt.UserRole, t["id"])
            it.setData(ROW_ROLE, t)
            self.tl.addItem(it)
        self.empty.setVisible(not self.rows)
        self.tl.setVisible(bool(self.rows))
        self.tl.setFixedHeight(len(self.rows) * 58 + 6)
        self.cover.set_cover(p["cover"] or next((t["cover"] for t in self.rows if t["cover"]), None))
        self._load_fields()
        self._sync_play()
        mins = int(sum(t["duration"] or 0 for t in self.rows) // 60)
        self.meta.setText(f"{len(self.rows)} track{'s' if len(self.rows) != 1 else ''}  ·  {mins} min")
    def refresh_add(self, *_):
        pid = self._pid
        self.addl.clear()
        if not pid:
            return
        have = {t["id"] for t in self.rows}
        q = self.q.text().strip()
        rows = self.win.lib.tracks(q, order="title") if q else self.win.lib.tracks(order="imported")
        for t in [t for t in rows if t["id"] not in have][:40]:
            it = QListWidgetItem(t["title"])
            it.setData(Qt.UserRole, t["id"])
            it.setData(ROW_ROLE, t)
            self.addl.addItem(it)
        self.addl.setFixedHeight(max(1, min(self.addl.count(), 6)) * 58 + 6)
    def add_track(self, tid):
        if self._pid:
            self.win.lib.add_to_playlist(self._pid, tid)
            self.show_tracks()
            self.refresh_add()

    def new(self, name=None, desc=""):
        """sem name abre o diálogo; com name cria direto (testes/atalhos)"""
        if name is None:
            dlg = NewPlaylistDialog(self)
            if dlg.exec() != QDialog.Accepted:
                return None
            name, desc = dlg.values()
        pid = self.win.lib.create_playlist(name.strip() or "My playlist", desc.strip())
        self.refresh()
        self.open(pid)
        return pid
    def rename(self):
        self.name.setFocus()
        self.name.selectAll()
    def dup(self):
        if self._pid:
            self.open(self.win.lib.duplicate_playlist(self._pid))
    def delete(self, pid=None):
        pid = pid or self._pid
        p = self.win.lib.playlist(pid) if pid else None
        if not p:
            return
        if not dialogs.confirm(self, "Delete playlist", f"Delete “{p['name']}”?\nThe songs stay in your library.", ok="Delete", danger=True):
            return
        self.win.lib.delete_playlist(pid)
        if pid == self._pid:
            self._pid = None
            self._saved = ("", "")
        self.refresh()
    def copy_id(self):
        if self._pid:
            QApplication.clipboard().setText(self._pid)
    def set_cover(self):
        if not self._pid:
            return
        f = pickers.pick_file(self, "Choose a cover image", (".png", ".jpg", ".jpeg", ".webp"), label="Images")
        if f:
            self.win.lib.update_playlist(self._pid, cover=save_cover_bytes(Path(f).read_bytes()))
            self.show_tracks()
    def remove(self, tid=None):
        it = self.tl.currentItem()
        tid = tid or (it.data(Qt.UserRole) if it else None)
        if self._pid and tid:
            self.win.lib.remove_from_playlist(self._pid, tid)
            self.show_tracks()
            self.refresh_add()
    def on_moved(self):
        if self._pid:
            self.win.lib.set_playlist_order(self._pid, [self.tl.item(i).data(Qt.UserRole) for i in range(self.tl.count())])
            self.show_tracks()
    def ctx(self):
        return ("playlist", self._pid) if self._pid else None
    def _sync_play(self, *_):
        try:
            self.play_big.set_playing(now.ctx_playing(self.ctx()))
        except RuntimeError:
            pass  # widget já destruído
    def toggle_play(self):
        if self.rows or now.is_ctx(self.ctx()):
            self.win.toggle_context(self.ctx(), self.rows)
    def play_from(self, start, shuffle):
        if self.rows:
            self.win.set_shuffle(shuffle)
            self.win.play_list(self.rows, start, ctx=self.ctx())
    def row_play(self, r):
        if 0 <= r < len(self.rows):
            self.win.play_row(self.rows, r, self.ctx(), shuffle=self.win.queue.shuffle)

    def _more_menu(self, btn):
        m = GlassMenu(self)
        for t, ic, fn in (("Duplicate", "copy", self.dup), ("Copy ID", "link", self.copy_id), ("Export", "upload", self.export)):
            m.addAction(icons.icon(ic, T.fg.name(), 16), t, fn)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
    def _grid_menu(self, pos):
        it = self.grid.itemAt(pos)
        if not it or self.grid.row(it) == 0:
            return
        pid = self.ids[self.grid.row(it) - 1]
        m = GlassMenu(self.grid)
        m.addAction(icons.icon("play", T.fg.name(), 16), "Play", lambda: self._play_pid(pid))
        m.addAction(icons.icon("list-music", T.fg.name(), 16), "Open", lambda: self.open(pid))
        m.addAction(icons.icon("pencil", T.fg.name(), 16), "Rename", lambda: (self.open(pid), self.rename()))
        m.addAction(icons.icon("copy", T.fg.name(), 16), "Duplicate", lambda: (self.win.lib.duplicate_playlist(pid), self.refresh()))
        m.addSeparator()
        m.act("trash", "Delete", lambda: self.delete(pid), danger=True)
        m.exec(self.grid.viewport().mapToGlobal(pos))
    def _play_pid(self, pid):
        self.win.toggle_context(("playlist", pid), self.win.lib.playlist_tracks(pid))
    def _import_menu(self, btn):
        m = GlassMenu(self)
        m.addAction(icons.icon("file-plus", T.fg.name(), 16), "Import file…", self.import_dialog)
        m.addAction(icons.icon("link", T.fg.name(), 16), "Import by ID…", self.import_id)
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
    def _track_menu(self, pos):
        it = self.tl.itemAt(pos)
        if not it:
            return
        tid = it.data(Qt.UserRole)
        m = GlassMenu(self.tl)
        m.act("skip-forward", "Play next", lambda: self.win.queue.play_next(tid))
        m.act("list-music", "Add to queue", lambda: self.win.queue.add_end(tid))
        m.addSeparator()
        m.act("x", "Remove from playlist", lambda: self.remove(tid))
        m.exec(self.tl.viewport().mapToGlobal(pos))

    def export(self):
        if not self._pid:
            return
        pid = self._pid
        name = self.win.lib.playlist(pid)["name"]
        f = pickers.save_file(self, "Export playlist", f"{name}.hexplaylist", ".hexplaylist", label="HexSound playlist")
        if not f:
            return
        share.export_playlist(self.win.lib, pid, f)
        share.export_playlist(self.win.lib, pid, Path(self.win.settings["shared_dir"]) / f"{pid}.hexplaylist")
        dialogs.notify(self, "Playlist exported", f"Saved to:\n{f}\n\nA copy named {pid}.hexplaylist was also placed in your shared "
                       f"folder ({self.win.settings['shared_dir']}). Anyone who can read that folder (e.g. via a synced "
                       "Drive/Dropbox folder) can import this playlist by its ID.", "success")
    def import_dialog(self):
        f = pickers.pick_file(self, "Import playlist", (".hexplaylist",), label="HexSound playlist")
        if f:
            self.import_file(f)
    def import_id(self):
        t = dialogs.ask_text(self, "Import by ID", "Paste the playlist ID you received.", ok="Import", placeholder="e.g. 3F9A1C7B20D4", icon="link")
        if not t:
            return
        f = share.find_playlist_file(t, self.win.settings["shared_dir"])
        if f:
            self.import_file(str(f))
        else:
            dialogs.notify(self, "Playlist not found", f"No playlist with that ID in the shared folder:\n{self.win.settings['shared_dir']}\n\n"
                             "Ask the owner for the .hexplaylist file, or point Settings → Shared playlists folder to a synced folder.", "warn")
    def import_file(self, path):
        try:
            res = share.import_playlist(self.win.lib, path)
        except ValueError as e:
            return dialogs.notify(self, "Import failed", str(e), "error")
        self._pid = None
        self.refresh()
        miss = res["missing"]
        msg = f"Imported “{res['name']}”: {res['added']} track(s) added."
        urls = [t["url"] for t in miss if t.get("url")]
        if miss:
            msg += f"\n{len(miss)} track(s) are not in your library:\n" + "\n".join(f"• {t.get('title')} — {t.get('artist')}" for t in miss[:10])
        if urls and dialogs.confirm(self, "Playlist imported", msg + f"\n\nDownload {len(urls)} missing track(s) from YouTube now?", ok="Download", cancel="Not now", icon="download"):
            self.win.go_page("Import Music")
            self.win.page["Import Music"].start_links("\n".join(urls), res["id"])
        elif not urls:
            dialogs.notify(self, "Playlist imported", msg, "success")
