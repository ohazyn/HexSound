from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QAbstractButton, QStackedWidget, QMenu)
from hexsound.ui import icons
from hexsound.ui.pages import RowDelegate, ROW_ROLE
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassPanel, GlassButton, _anim, _to

W = 340

class TabText(QAbstractButton):
    def __init__(self, text):
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self._h = self._s = 0.0
        self._ha, self._sa = _anim(self, self._sh, ms=140), _anim(self, self._ss, ms=200)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(34)
        f = self.font()
        f.setPixelSize(14)
        f.setWeight(f.Weight.DemiBold)
        self.setFont(f)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(text) + 8)
    def _sh(self, v):
        self._h = float(v)
        self.update()
    def _ss(self, v):
        self._s = float(v)
        self.update()
    def set_on(self, on):
        self.setChecked(on)
        _to(self._sa, self._s, 1.0 if on else 0.0)
    def enterEvent(self, e):
        _to(self._ha, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._ha, self._h, 0.0)
        super().leaveEvent(e)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(T.fg)
        c.setAlphaF(0.58 + 0.42 * max(self._h, self._s))
        f = self.font()
        p.setFont(f)
        p.setPen(c)
        p.drawText(QRectF(4, 0, self.width() - 8, self.height() - 4), Qt.AlignCenter, self.text())
        if self._s > 0.01:
            bw = (self.width() - 8) * self._s
            bar = QColor(T.accent)
            p.setPen(Qt.NoPen)
            p.setBrush(bar)
            p.drawRoundedRect(QRectF(self.width() / 2 - bw / 2, self.height() - 4, bw, 2.5), 1.2, 1.2)

class QueuePanel(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._open = False
        self._sig = None
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 0, 0)
        self.setMaximumWidth(0)
        self.setMinimumWidth(0)
        self.hide()
        self.panel = GlassPanel(26, "queue")
        self.panel.setFixedWidth(W)
        h.addWidget(self.panel)
        h.setAlignment(self.panel, Qt.AlignLeft)
        v = QVBoxLayout(self.panel)
        v.setContentsMargins(16, 12, 12, 12)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(14)
        self.tabs = [TabText("Queue"), TabText("Recently played")]
        for i, t in enumerate(self.tabs):
            t.clicked.connect(lambda _=False, i=i: self.set_tab(i))
            top.addWidget(t)
        top.addStretch()
        x = GlassButton("", "x", "ghost", size=32, tooltip="Close")
        x.clicked.connect(self.close_panel)
        top.addWidget(x)
        v.addLayout(top)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        q = QWidget()
        ql = QVBoxLayout(q)
        ql.setContentsMargins(0, 4, 0, 0)
        ql.setSpacing(4)
        ql.addWidget(QLabel("Now playing", objectName="h2"))
        self.now = self._list(True)
        self.now.setFixedHeight(62)
        ql.addWidget(self.now)
        row = QHBoxLayout()
        self.nextl = QLabel("Next", objectName="h2")
        row.addWidget(self.nextl)
        row.addStretch()
        self.clear_b = GlassButton("Clear", None, "ghost", size=28)
        self.clear_b.clicked.connect(self.clear)
        row.addWidget(self.clear_b)
        ql.addLayout(row)
        self.up = self._list()
        ql.addWidget(self.up, 1)
        self.empty = QLabel("The queue is empty.\nPlay a song or add one from a track’s menu.", objectName="muted")
        self.empty.setAlignment(Qt.AlignCenter)
        ql.addWidget(self.empty)
        self.stack.addWidget(q)
        hl = QWidget()
        hv = QVBoxLayout(hl)
        hv.setContentsMargins(0, 4, 0, 0)
        self.hist = self._list()
        hv.addWidget(self.hist)
        self.hempty = QLabel("Nothing played yet.", objectName="muted")
        self.hempty.setAlignment(Qt.AlignCenter)
        hv.addWidget(self.hempty)
        self.stack.addWidget(hl)
        self.up.itemDoubleClicked.connect(lambda it: (win.jump(it.data(Qt.UserRole)), self.refresh()))
        self.up.setContextMenuPolicy(Qt.CustomContextMenu)
        self.up.customContextMenuRequested.connect(self._menu)
        self.hist.itemDoubleClicked.connect(self.replay)
        self.now.itemDoubleClicked.connect(lambda it: win.engine.toggle())
        self._anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._done)
        self._poll = QTimer(self, interval=400, timeout=self._check)
        self.set_tab(0)

    def _list(self, accent=False):
        l = QListWidget()
        l.setItemDelegate(RowDelegate(heart=False, accent=accent))
        l.setMouseTracking(True)
        l.setFocusPolicy(Qt.NoFocus)
        return l

    def toggle(self):
        self.close_panel() if self._open else self.open_panel()
    def open_panel(self):
        self._open = True
        self.refresh()
        self.show()
        self._poll.start()
        self.win.btn["queue"].setChecked(True)
        self._run(self.maximumWidth(), W + 12)
    def close_panel(self):
        self._open = False
        self._poll.stop()
        self.win.btn["queue"].setChecked(False)
        self._run(self.maximumWidth(), 0)
    def _run(self, a, b):
        self._anim.stop()
        if T.reduce:
            self.setMaximumWidth(b)
            self._done()
            return
        self._anim.setStartValue(a)
        self._anim.setEndValue(b)
        self._anim.start()
    def _done(self):
        if not self._open:
            self.hide()

    def set_tab(self, i):
        self.stack.setCurrentIndex(i)
        for k, t in enumerate(self.tabs):
            t.set_on(k == i)
        self.refresh()
    def _check(self):
        q = self.win.queue
        sig = (tuple(q.items), tuple(q.order), q.pos, self.win.cur["id"] if self.win.cur else None)
        if sig != self._sig:
            self.refresh()
    def _item(self, r, qpos=None):
        it = QListWidgetItem(r["title"])
        it.setData(ROW_ROLE, r)
        it.setData(Qt.UserRole, r["id"] if qpos is None else qpos)
        return it
    def refresh(self):
        w, q = self.win, self.win.queue
        self._sig = (tuple(q.items), tuple(q.order), q.pos, w.cur["id"] if w.cur else None)
        self.now.clear()
        self.up.clear()
        self.hist.clear()
        if w.cur:
            self.now.addItem(self._item(w.cur))
        up = [(q.pos + 1 + i, w.lib.get_track(t)) for i, t in enumerate(q.upcoming())]
        for pos, r in up:
            if r:
                self.up.addItem(self._item(r, pos))
        self.up.setVisible(self.up.count() > 0)
        self.empty.setVisible(self.up.count() == 0)
        self.clear_b.setVisible(self.up.count() > 0)
        self.now.setVisible(bool(w.cur))
        self.nextl.setText(f"Next  ·  {self.up.count()}" if self.up.count() else "Next")
        for r in w.lib.history(50):
            self.hist.addItem(self._item(r))
        self.hist.setVisible(self.hist.count() > 0)
        self.hempty.setVisible(self.hist.count() == 0)

    def clear(self):
        q = self.win.queue
        while q.upcoming():
            q.remove(q.pos + 1)
        self.refresh()
    def replay(self, it):
        self.win.queue.play_next(it.data(Qt.UserRole))
        self.win.go(self.win.queue.next())
        self.refresh()
    def _menu(self, pos):
        it = self.up.itemAt(pos)
        if not it:
            return
        from hexsound.ui.dialogs import GlassMenu
        m = GlassMenu(self.up)
        m.act("x", "Remove from queue", lambda: (self.win.queue.remove(it.data(Qt.UserRole)), self.refresh()))
        m.exec(self.up.viewport().mapToGlobal(pos))
