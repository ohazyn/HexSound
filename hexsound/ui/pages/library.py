"""Tela Library: filtros (All/Favorites/Recent/Downloads) e alternância lista/grade."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from hexsound.ui.widgets import GlassButton, GlassCombo, SearchField, Segmented
from hexsound.ui.pages.common import SORTS, h1
from hexsound.ui.pages.rows import TrackGrid, TrackTable, show_track_menu

FILTERS = {"All": {}, "Favorites": {"favorites": True}, "Recent": {"recent": True}, "Downloads": {"downloaded": True}}

class TrackPage(QWidget):
    def __init__(self, win, title, **flt):
        super().__init__()
        self.win, self.flt = win, flt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(h1(title))
        self.chips = Segmented(list(FILTERS), "All")
        self.chips.changed.connect(lambda _: self.refresh())
        top = QHBoxLayout()
        top.addWidget(self.chips)
        top.addStretch()
        self.vbtn = {}
        for k, ic in (("list", "list"), ("grid", "layout-grid")):
            b = GlassButton("", ic, "ghost", size=34, tooltip=f"{k.capitalize()} view")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=k: self.set_view(k))
            self.vbtn[k] = b
            top.addWidget(b)
        lay.addLayout(top)
        row = QHBoxLayout()
        self.search = SearchField("Search title, artist or album")
        self.sort = GlassCombo()
        for n, k in SORTS:
            self.sort.addItem(n, k)
        row.setSpacing(10)
        row.addWidget(self.search, 1)
        row.addWidget(QLabel("Sort by", objectName="muted"))
        row.addWidget(self.sort)
        lay.addLayout(row)
        self._deb = QTimer(self, singleShot=True, interval=180, timeout=self.refresh)  # espera parar de digitar
        self.search.textChanged.connect(lambda _t: self._deb.start())
        self.sort.currentIndexChanged.connect(self.refresh)
        self.table, self.grid = TrackTable(), TrackGrid()
        self.views = {"list": self.table, "grid": self.grid}
        for v in self.views.values():
            lay.addWidget(v)
            v.customContextMenuRequested.connect(lambda p, v=v: show_track_menu(win, v, p))
        self.table.cellDoubleClicked.connect(lambda r, _c: win.play_list(self.table.rows, r))
        self.table.play_row.connect(lambda r: win.play_row(self.table.rows, r))
        self.grid.itemDoubleClicked.connect(lambda it: win.play_list(self.grid.rows, self.grid.row(it)))
        self.set_view(win.settings["library_view"] if win.settings["library_view"] in self.views else "list", save=False)
    def set_view(self, k, save=True):
        self.view = k
        for n, v in self.views.items():
            v.setVisible(n == k)
            self.vbtn[n].setChecked(n == k)
        if save:
            self.win.settings.set("library_view", k)
        self.refresh()
    def refresh(self, *_):
        rows = self.win.lib.tracks(self.search.text(), order=self.sort.currentData(), **FILTERS[self.chips.current], **self.flt)
        self.table.fill(rows)
        self.grid.fill(rows)
