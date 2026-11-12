"""Resultados da busca online (YouTube / SoundCloud) na tela Search."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QFontMetrics
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea, QFrame, QSizePolicy
from hexsound.ui import icons
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton
from hexsound.ui.pages.common import gbtn, fmt

NAMES = {"youtube": "YouTube", "soundcloud": "SoundCloud"}
THUMB = 48
# estado -> (texto do botão, ícone, habilitado)
BUTTON = {"idle": ("Add", "plus", True), "waiting": ("Waiting", "clock", False), "downloading": ("0%", "download", False),
          "converting": ("Converting", "refresh", False), "done": ("Play", "play", True), "failed": ("Retry", "refresh", True)}


class _Elided(QLabel):
    """texto que se corta com “…” em vez de alargar a linha"""
    def __init__(self, text="", name=""):
        super().__init__()
        self._full = text
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self._fit()
    def _fit(self):
        QLabel.setText(self, QFontMetrics(self.font()).elidedText(self._full, Qt.ElideRight, max(self.width(), 20)))
    def set_full(self, text):
        self._full = text
        self.setToolTip(text)
        self._fit()
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


def _rounded(pm, size=THUMB, radius=8):
    pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    pm = pm.copy((pm.width() - size) // 2, (pm.height() - size) // 2, size, size)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def _placeholder(size=THUMB, radius=8):
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.fillPath(path, T.ovc(0.10))
    ic = icons.icon("music", T.fg.name(), 22).pixmap(22, 22)
    p.setOpacity(0.5)
    p.drawPixmap((size - 22) // 2, (size - 22) // 2, ic)
    p.end()
    return out


PREVIEW = {"idle": ("play", "Preview (30 s)"), "loading": ("clock", "Loading preview… (click to cancel)"), "playing": ("pause", "Stop preview")}


class OnlineRow(QWidget):
    add = Signal(int)
    play = Signal(int)
    preview = Signal(int)

    def __init__(self, uid, r):
        super().__init__()
        self.uid, self.state = uid, "idle"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(12)
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB, THUMB)
        self.thumb.setPixmap(_placeholder())
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = _Elided()
        self.title.set_full(r["title"])
        self.meta = _Elided(name="muted")
        dur = fmt(r["duration"]) if r.get("duration") else ""
        parts = [r["artist"], dur, r.get("label") or NAMES.get(r["source"], r["source"])] + (["In library"] if r.get("in_library") else [])
        self.meta.set_full("  ·  ".join(x for x in parts if x))
        col.addWidget(self.title)
        col.addWidget(self.meta)
        lay.addLayout(col, 1)
        self.pv = GlassButton("", "play", "ghost", size=34, tooltip=PREVIEW["idle"][1])
        self.pv.clicked.connect(lambda: self.preview.emit(self.uid))
        lay.addWidget(self.pv)
        self.btn = gbtn("Add", "plus")
        self.btn.setMinimumWidth(104)
        self.btn.clicked.connect(self._click)
        lay.addWidget(self.btn)
    def set_thumb(self, data):
        pm = QPixmap()
        if pm.loadFromData(data) and not pm.isNull():
            self.thumb.setPixmap(_rounded(pm))
    def set_preview(self, state):
        ic, tip = PREVIEW[state]
        self.pv.set_icon(ic)
        self.pv.setToolTip(tip)
        self.pv.update()
    def set_state(self, state, pct=0.0, msg=""):
        self.state = state
        text, ic, enabled = BUTTON[state]
        if state == "downloading":
            text = f"{pct:.0f}%"
        self.btn.setText(text)
        self.btn.set_icon(ic)
        self.btn.setEnabled(enabled)
        self.btn.setToolTip(msg if state == "failed" else "")
        self.btn.update()
    def _click(self):
        if self.state == "done":
            self.play.emit(self.uid)
        elif self.state in ("idle", "failed"):
            self.add.emit(self.uid)


class OnlineResults(QWidget):
    add = Signal(int)
    play = Signal(int)
    preview = Signal(int)

    def __init__(self):
        super().__init__()
        self.active, self.rows = False, {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(QLabel("Online results", objectName="h2"))
        self.status = QLabel("", objectName="muted")
        self.status.setWordWrap(True)
        head.addWidget(self.status, 1)
        lay.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setMinimumHeight(150)
        self.box = QWidget()
        self.col = QVBoxLayout(self.box)
        self.col.setContentsMargins(0, 0, 8, 0)
        self.col.setSpacing(2)
        self.col.addStretch()
        self.scroll.setWidget(self.box)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.box.setStyleSheet("background:transparent;")
        lay.addWidget(self.scroll, 1)
        self.hide()

    def _clear(self):
        for r in self.rows.values():
            r.setParent(None)
            r.deleteLater()
        self.rows = {}

    def reset(self):
        self._clear()
        self.active = False
        self.hide()

    def show_loading(self, text):
        self._clear()
        self.active = True
        self.status.setText(text)
        self.show()

    def set_status(self, text):
        self.status.setText(text)

    def set_results(self, items, status):
        """items: [(uid, resultado, estado, pct, msg)]"""
        self._clear()
        self.active = True
        self.status.setText(status)
        for uid, r, state, pct, msg in items:
            row = OnlineRow(uid, r)
            row.add.connect(self.add)
            row.play.connect(self.play)
            row.preview.connect(self.preview)
            row.set_state(state, pct, msg)
            self.col.insertWidget(self.col.count() - 1, row)
            self.rows[uid] = row
        self.scroll.verticalScrollBar().setValue(0)
        self.show()
