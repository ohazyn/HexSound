import os
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QVariantAnimation, QEasingCurve, QObject, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QContextMenuEvent
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPlainTextEdit
from hexsound.ui import icons
from hexsound.ui.style import T, paint_sheet
from hexsound.ui.widgets import GlassButton

RED = "#ff453a"

class _Scrim(QWidget):
    def __init__(self, host):
        super().__init__(host)
        self._t = 0.0
        self.setGeometry(host.rect())
        self.show()
        self.raise_()
        if T.reduce:
            self._t = 1.0
        else:
            a = self._a = QVariantAnimation(self)
            a.setDuration(220)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.valueChanged.connect(self._set)
            a.start()
    def _set(self, v):
        self._t = float(v)
        self.update()
    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, int(115 * self._t)))

class GlassDialog(QDialog):
    PAD = 22
    def __init__(self, parent=None, icon="info", tone="accent"):
        host = parent.window() if parent is not None else None
        super().__init__(host, Qt.Dialog | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._icon, self._tone = icon, tone
        self._scrim = None
        self._anim = None
        self._host = host
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(self.PAD + 26, self.PAD + 24, self.PAD + 26, self.PAD + 22)
        self.body.setSpacing(12)
        self.setFixedWidth(470 + 2 * self.PAD)

    def header(self, title, text=""):
        row = QHBoxLayout()
        row.setSpacing(16)
        bub = QLabel()
        bub.setFixedSize(48, 48)
        self._bub = bub
        row.addWidget(bub, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet("font-size:19px;font-weight:700;")
        col.addWidget(t)
        if text:
            m = QLabel(text)
            m.setWordWrap(True)
            m.setObjectName("muted")
            m.setTextInteractionFlags(Qt.NoTextInteraction)
            col.addWidget(m)
            self.message = m
        row.addLayout(col, 1)
        self.body.addLayout(row)
        self._paint_bubble()
        return col
    def _paint_bubble(self):
        from PySide6.QtGui import QPixmap
        dpr = 2
        pm = QPixmap(48 * dpr, 48 * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor(RED if self._tone == "danger" else "#ffb020" if self._tone == "warn" else T.accent.name())
        g = QLinearGradient(0, 0, 48, 48)
        c1, c2 = QColor(base), QColor(base)
        c1.setAlphaF(0.32)
        c2.setAlphaF(0.12)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 0, 48, 48), 15, 15)
        icons.draw(p, self._icon, QRectF(13, 13, 22, 22), base.lighter(135).name() if T.dark else base.darker(115).name())
        p.end()
        self._bub.setPixmap(pm)
    def buttons(self, cancel="Cancel", ok="OK", danger=False, ok_icon=None):
        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 0)
        row.setSpacing(10)
        row.addStretch()
        self.cancel_btn = GlassButton(cancel, None, "glass", size=40) if cancel else None
        self.ok_btn = GlassButton(ok, ok_icon, "destructive" if danger else "accent", size=40)
        for b in (self.cancel_btn, self.ok_btn):
            if b:
                b.setMinimumWidth(104)
                row.addWidget(b)
        if self.cancel_btn:
            self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self.accept)
        self.body.addLayout(row)
        (self.cancel_btn if (danger and self.cancel_btn) else self.ok_btn).setFocus()  # ação destrutiva: Enter NÃO confirma
        return self.cancel_btn, self.ok_btn

    def paintEvent(self, _):
        p = QPainter(self)
        paint_sheet(p, QRectF(self.rect()).adjusted(self.PAD, self.PAD, -self.PAD, -self.PAD))

    def exec(self):
        if os.environ.get("HEXSOUND_NO_MODAL"):
            return QDialog.Rejected  # testes/CI: nunca trava esperando clique
        return super().exec()
    def showEvent(self, e):
        super().showEvent(e)
        self.adjustSize()
        h = self._host
        if h is not None:
            c = h.geometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
            if self._scrim is None:
                self._scrim = _Scrim(h)
        base = self.pos()
        if T.reduce:
            return
        self.setWindowOpacity(0.0)
        self.move(base + QPoint(0, 16))
        a = self._anim = QVariantAnimation(self)
        a.setDuration(300)
        a.setEasingCurve(QEasingCurve.OutBack)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(lambda t: (self.setWindowOpacity(max(0.0, min(1.0, float(t) * 1.4))), self.move(base + QPoint(0, int(16 * (1 - float(t)))))))
        a.start()
    def done(self, r):
        if self._scrim is not None:
            self._scrim.deleteLater()
            self._scrim = None
        super().done(r)

def confirm(parent, title, text, ok="OK", cancel="Cancel", danger=False, icon=None):
    d = GlassDialog(parent, icon or ("trash" if danger else "check"), "danger" if danger else "accent")
    d.header(title, text)
    d.buttons(cancel, ok, danger)
    return d.exec() == QDialog.Accepted

def notify(parent, title, text, kind="info", ok="OK"):
    """kind: info | success | warn | error"""
    icon, tone = {"info": ("info", "accent"), "success": ("check", "accent"), "warn": ("alert-triangle", "warn"), "error": ("alert-triangle", "danger")}.get(kind, ("info", "accent"))
    d = GlassDialog(parent, icon, tone)
    d.header(title, text)
    d.buttons(None, ok)
    d.exec()

def ask_text(parent, title, label="", default="", ok="OK", placeholder="", icon="pencil"):
    d = GlassDialog(parent, icon)
    d.header(title, label)
    e = QLineEdit(default)
    e.setPlaceholderText(placeholder)
    d.body.addWidget(e)
    _, okb = d.buttons("Cancel", ok)
    e.returnPressed.connect(d.accept)
    e.setFocus()
    e.selectAll()
    return e.text().strip() if d.exec() == QDialog.Accepted else None

class NewPlaylistDialog(GlassDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "plus")
        self.setWindowTitle("New playlist")
        self.header("New playlist", "Give it a title. The subtitle is optional.")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Title")
        self.sub = QLineEdit()
        self.sub.setPlaceholderText("Subtitle (optional)")
        self.body.addWidget(self.title)
        self.body.addWidget(self.sub)
        self.cancel_btn, self.ok = self.buttons("Cancel", "Create", ok_icon="check")
        self.ok.setEnabled(False)
        self.title.textChanged.connect(lambda t: self.ok.setEnabled(bool(t.strip())))
        self.title.returnPressed.connect(self._go)
        self.sub.returnPressed.connect(self._go)
        self.title.setFocus()
    def _go(self):
        if self.ok.isEnabled():
            self.accept()
    def values(self):
        return self.title.text().strip(), self.sub.text().strip()

from PySide6.QtWidgets import QMenu
from PySide6.QtCore import QSize

class GlassMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("glassmenu")
    def act(self, icon, text, fn=None, danger=False):
        a = self.addAction(icons.icon(icon, RED if danger else T.fg.name(), 18), text)
        if fn:
            a.triggered.connect(lambda _=False, fn=fn: fn())
        return a
    def sub(self, icon, text):
        m = GlassMenu(self)
        m.setTitle(text)
        m.setIcon(icons.icon(icon, T.fg.name(), 18))
        self.addMenu(m)
        return m
    def paintEvent(self, e):
        p = QPainter(self)
        paint_sheet(p, QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, shadow=False)
        p.end()
        super().paintEvent(e)


_EDIT_ICONS = {"undo": "undo", "redo": "redo", "cut": "scissors", "copy": "copy", "paste": "paste", "delete": "trash", "select all": "scan"}

def edit_menu(w, global_pos):
    std = w.createStandardContextMenu()
    gm = GlassMenu(w)
    for a in std.actions():
        if a.isSeparator():
            gm.addSeparator()
            continue
        key = a.text().split("\t")[0].replace("&", "").strip().lower()
        ic = next((v for k, v in _EDIT_ICONS.items() if key.startswith(k)), None)
        a.setText(a.text().replace("&", ""))
        if ic:
            a.setIcon(icons.icon(ic, T.fg.name(), 18))
        gm.addAction(a)
    gm.exec(global_pos)
    std.deleteLater()

class EditMenuFilter(QObject):
    def eventFilter(self, o, e):
        if e.type() == QEvent.ContextMenu and isinstance(o, (QLineEdit, QTextEdit, QPlainTextEdit)):
            edit_menu(o, e.globalPos())
            return True
        return False
