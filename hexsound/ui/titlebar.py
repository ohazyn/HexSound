from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QAbstractButton, QSizePolicy
from hexsound.ui import icons
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton, SearchField, _anim, _to

class WinButton(QAbstractButton):
    def __init__(self, icon_name, danger=False, tip=""):
        super().__init__()
        self._icon, self.danger, self._h = icon_name, danger, 0.0
        self._a = _anim(self, self._set, ms=140)
        self.setFixedSize(44, 32)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tip)
    def _set(self, v):
        self._h = float(v)
        self.update()
    def set_icon(self, name):
        self._icon = name
        self.update()
    def enterEvent(self, e):
        _to(self._a, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._a, self._h, 0.0)
        super().leaveEvent(e)
    def paintEvent(self, _):
        if not self.underMouse() and self._a.state() != self._a.State.Running:
            self._h = 0.0  # nunca fica vermelho fora do hover
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self._h
        r = QRectF(self.rect()).adjusted(3, 2, -3, -2)
        bg = QColor(232, 17, 35) if self.danger else QColor(T.ov)
        bg.setAlphaF(h * (0.95 if self.danger else (0.14 if T.dark else 0.10)))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 10, 10)
        col = "#ffffff" if (self.danger and h > 0.3) else T.fg.name()
        k = 14 + 1.5 * h
        icons.draw(p, self._icon, QRectF(self.width() / 2 - k / 2, self.height() / 2 - k / 2, k, k), col, False, opacity=0.7 + 0.3 * h)

class TitleBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(46)
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 4, 0, 0)
        h.setSpacing(0)
        left = QWidget()
        lh = QHBoxLayout(left)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(6)
        self.back = GlassButton("", "arrow-left", "glass", size=34, tooltip="Back (Alt+Left)")
        self.fwd = GlassButton("", "arrow-right", "glass", size=34, tooltip="Forward (Alt+Right)")
        lh.addWidget(self.back)
        lh.addWidget(self.fwd)
        lh.addStretch()
        left.setFixedWidth(150)
        self.search = SearchField("What do you want to hear?")
        self.search.setMinimumHeight(36)
        self.search.setMaximumWidth(460)
        self.search.setMinimumWidth(240)
        self.search.setClearButtonEnabled(True)
        right = QWidget()
        rh = QHBoxLayout(right)
        rh.setContentsMargins(0, 0, 8, 0)
        rh.setSpacing(0)
        rh.addStretch()
        self.bmin = WinButton("minus", tip="Minimize")
        self.bmax = WinButton("square", tip="Maximize")
        self.bclose = WinButton("x", True, "Close")
        for b in (self.bmin, self.bmax, self.bclose):
            rh.addWidget(b)
        right.setFixedWidth(150)
        h.addWidget(left)
        h.addStretch(1)
        h.addWidget(self.search, 4)
        h.addStretch(1)
        h.addWidget(right)
        self.bmin.clicked.connect(win.showMinimized)
        self.bclose.clicked.connect(win.close)
        self.bmax.clicked.connect(self.toggle_max)
    def toggle_max(self):
        self.win.showNormal() if self.win.isMaximized() else self.win.showMaximized()
    def set_maximized(self, on):
        self.bmax.set_icon("copy" if on else "square")
        self.bmax.setToolTip("Restore" if on else "Maximize")
    def mousePressEvent(self, e):
        wh = self.win.windowHandle()
        if e.button() != Qt.LeftButton or not wh:
            return
        edge = self.win._edges(self.mapTo(self.win.root, e.position().toPoint()))
        wh.startSystemResize(edge) if edge else wh.startSystemMove()
    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.toggle_max()
