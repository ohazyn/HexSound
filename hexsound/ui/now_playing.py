from PySide6.QtCore import Qt, QEvent, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QTabWidget, QListWidget, QListWidgetItem, QGraphicsOpacityEffect)
from hexsound.ui.style import paint_sheet
from hexsound.ui.home import CoverLabel
from hexsound.ui.pages import RowDelegate, ROW_ROLE
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton

def fmt(sec):
    s = int(sec or 0)
    return f"{s // 60}:{s % 60:02d}"

class NowPlaying(QWidget):
    PAD = 22
    def __init__(self, win):
        super().__init__(win.root)
        self.win = win
        self._fade = None
        self.setFocusPolicy(Qt.StrongFocus)
        win.root.installEventFilter(self)
        win.installEventFilter(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(self.PAD + 22, self.PAD + 16, self.PAD + 22, self.PAD + 20)
        lay.setSpacing(10)
        self.sheet_margin = (self.PAD + 22, self.PAD + 16)
        top = QHBoxLayout()
        t = QLabel("Now playing")
        t.setStyleSheet("font-size:19px;font-weight:700;")
        top.addWidget(t)
        top.addStretch()
        x = GlassButton("", "x", "ghost", size=34, tooltip="Close (Esc)")
        x.clicked.connect(self.close_sheet)
        top.addWidget(x)
        lay.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(14)
        lay.addLayout(body, 1)
        left = QFrame()
        left.setObjectName("group")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(20, 20, 20, 18)
        lv.setSpacing(8)
        self.cover = CoverLabel(250, 22)
        lv.addWidget(self.cover, 0, Qt.AlignHCenter)
        self.title = QLabel("Nothing playing")
        self.title.setStyleSheet("font-size:24px;font-weight:700;")
        self.title.setWordWrap(True)
        self.meta = QLabel("")
        self.meta.setObjectName("muted")
        self.meta.setWordWrap(True)
        lv.addWidget(self.title)
        lv.addWidget(self.meta)
        lv.addStretch()
        left.setFixedWidth(300)
        body.addWidget(left)
        right = QFrame()
        right.setObjectName("group")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(14, 12, 14, 12)
        self.tabs = QTabWidget()
        self.up, self.hist = QListWidget(), QListWidget()
        for l in (self.up, self.hist):
            l.setItemDelegate(RowDelegate(heart=False))
            l.setMouseTracking(True)
            l.setFocusPolicy(Qt.NoFocus)
        self.tabs.addTab(self.up, "Up next")
        self.tabs.addTab(self.hist, "History")
        rv.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        for text, ic, fn in (("Remove selected", "x", self.remove), ("Clear queue", "trash", self.clear)):
            b = GlassButton(text, ic, "glass", size=34)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        row.addStretch()
        rv.addLayout(row)
        body.addWidget(right, 1)
        self.up.itemDoubleClicked.connect(lambda it: (self.win.jump(it.data(Qt.UserRole)), self.refresh()))
        self.hist.itemDoubleClicked.connect(self.replay)
        self.hide()

    def _sheet_rect(self):
        w, h = min(920, self.width() - 40), min(580, self.height() - 40)
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
    def _fit(self):
        self.setGeometry(self.win.root.rect())
        r = self._sheet_rect()
        m = self.layout()
        m.setContentsMargins(int(r.left()) + 22, int(r.top()) + 16, int(self.width() - r.right()) + 22, int(self.height() - r.bottom()) + 18)
    def eventFilter(self, o, e):
        if o is self.win.root and e.type() == QEvent.Resize and self.isVisible():
            self._fit()
        elif o is self.win and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape and self.isVisible():
            self.close_sheet()
            return True
        return False
    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        paint_sheet(p, self._sheet_rect())
    def mousePressEvent(self, e):
        if not self._sheet_rect().contains(e.position()):
            self.close_sheet()
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_sheet()
        else:
            super().keyPressEvent(e)

    def open_sheet(self):
        self.refresh()
        self._fit()
        self.raise_()
        self.show()
        self.setFocus()
        if T.reduce:
            return
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        a = self._fade = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(180)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.finished.connect(lambda: self.setGraphicsEffect(None))
        a.start()
    def close_sheet(self):
        self.hide()

    def refresh(self):
        w, t = self.win, self.win.cur
        self.cover.set_cover(t["cover"] if t else None)
        self.title.setText(t["title"] if t else "Nothing playing")
        self.meta.setText(f"{t['artist']}\n{t['album']}\n{fmt(t['duration'])} · {t['source']}" if t else "")
        self.up.clear()
        q = w.queue
        for i, tid in enumerate(q.upcoming()):
            r = w.lib.get_track(tid)
            if r:
                it = QListWidgetItem(r["title"])
                it.setData(Qt.UserRole, q.pos + 1 + i)
                it.setData(ROW_ROLE, r)
                self.up.addItem(it)
        self.hist.clear()
        for r in w.lib.history(50):
            it = QListWidgetItem(r["title"])
            it.setData(Qt.UserRole, r["id"])
            it.setData(ROW_ROLE, r)
            self.hist.addItem(it)
    def remove(self):
        it = self.up.currentItem()
        if it:
            self.win.queue.remove(it.data(Qt.UserRole))
            self.refresh()
    def clear(self):
        q = self.win.queue
        while q.upcoming():
            q.remove(q.pos + 1)
        self.refresh()
    def replay(self, it):
        self.win.queue.play_next(it.data(Qt.UserRole))
        self.win.go(self.win.queue.next())
        self.refresh()
