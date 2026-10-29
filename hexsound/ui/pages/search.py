"""Tela Search: busca de faixas e playlists."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget
from hexsound.ui import icons
from hexsound.ui.style import T
from hexsound.ui.widgets import SearchField
from hexsound.ui.pages.rows import TrackTable, show_track_menu
from hexsound.ui.pages.common import h1

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
        self.q.textChanged.connect(self.refresh)
        lay.addWidget(self.q)
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
        self.empty.setVisible(not rows and not ps)
        self.hint.setText(f"No results for “{q}”" if q else "Search songs, artists, albums and playlists")
        self.hint_ic.setPixmap(_dim_icon("search", 44))
    def play_pl(self, it):
        pid = self.pids[self.pl.row(it)]
        rows = self.win.lib.playlist_tracks(pid)
        if rows:
            self.win.play_list(rows, 0, ctx=("playlist", pid))
