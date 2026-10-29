"""Tela Albums: grade de discos com vinil e detalhe do álbum."""
from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFontMetrics, QLinearGradient, QRadialGradient, QPen
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QScrollArea, QFrame, QStyledItemDelegate, QStackedWidget)
from hexsound.ui import icons
from hexsound.ui.dialogs import GlassMenu
from hexsound.ui.home import CoverLabel, load_cover
from hexsound.ui.nowstate import now
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton, PlayFab
from hexsound.ui.pages.common import ROW_ROLE, _cover_rect, h1
from hexsound.ui.pages.rows import RowDelegate, RowList, show_track_menu

def draw_vinyl(p, c, rad, accent):
    p.save()
    p.setPen(Qt.NoPen)
    g = QRadialGradient(c, rad)
    g.setColorAt(0, QColor(38, 38, 44))
    g.setColorAt(1, QColor(10, 10, 14))
    p.setBrush(g)
    p.drawEllipse(c, rad, rad)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 14), 0.8))
    for k in (0.55, 0.68, 0.80, 0.92):
        p.drawEllipse(c, rad * k, rad * k)
    sh = QLinearGradient(c.x() - rad, c.y() - rad, c.x() + rad, c.y() + rad)
    sh.setColorAt(0.3, QColor(255, 255, 255, 0))
    sh.setColorAt(0.5, QColor(255, 255, 255, 30))
    sh.setColorAt(0.7, QColor(255, 255, 255, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(sh)
    p.drawEllipse(c, rad, rad)
    p.setBrush(accent)
    p.drawEllipse(c, rad * 0.30, rad * 0.30)
    p.setBrush(QColor(10, 10, 14))
    p.drawEllipse(c, rad * 0.06, rad * 0.06)
    p.restore()

class GroupDelegate(QStyledItemDelegate):
    """álbum = caixa de disco com vinil; artista = foto redonda"""
    S = 128
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
    def sizeHint(self, o, i):
        return QSize(204, self.S + 62)
    def paint(self, p, o, idx):
        view = o.widget
        h = view._hp.get(idx.row(), 0.0)
        name, n, cover = idx.data(Qt.UserRole), idx.data(Qt.UserRole + 2), idx.data(Qt.UserRole + 1)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        S = self.S
        L, T0 = o.rect.left() + 14, o.rect.top() + 10
        if self.kind == "album":
            sl = QRectF(L, T0, S, S)
            R = 14
            lift = 1.5 * h
            p.setPen(Qt.NoPen)
            for k in range(6, 0, -1):  # sombra suave, arredondada, atrás do vinil
                p.setBrush(QColor(0, 0, 0, 6 + int(2 * h)))
                p.drawRoundedRect(sl.adjusted(-k, -k + 5, k, k + 5), R + k, R + k)
            draw_vinyl(p, QPointF(L + S / 2 + S * (0.12 + 0.26 * h), T0 + S / 2), S * 0.48, T.accent)
            cv = sl.translated(-lift, -lift)
            _cover_rect(p, cv, cover, S, R)
            c = QPainterPath()
            c.addRoundedRect(cv, R, R)
            p.save()
            p.setClipPath(c)
            gl = QLinearGradient(cv.topLeft(), cv.bottomRight())
            gl.setColorAt(0, QColor(255, 255, 255, 38))
            gl.setColorAt(0.5, QColor(255, 255, 255, 0))
            p.fillRect(cv, gl)
            p.restore()
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 36 + int(50 * h)), 1))
            p.drawRoundedRect(cv.adjusted(.5, .5, -.5, -.5), R, R)
        else:
            sl = QRectF(L + 20, T0, S, S)
            c = QPainterPath()
            c.addEllipse(sl)
            p.save()
            p.setClipPath(c)
            sc = 1 + 0.05 * h
            pm = load_cover(cover, S)
            if pm:
                p.drawPixmap(QRectF(sl.center().x() - S * sc / 2, sl.center().y() - S * sc / 2, S * sc, S * sc).toRect(), pm)
            else:
                p.fillPath(c, T.ovc(0.10))
                icons.draw(p, "user", QRectF(sl.center().x() - 24, sl.center().y() - 24, 48, 48), T.fg.name(), opacity=0.45)
            p.restore()
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(T.accent if h > 0.5 else T.ovc(0.2), 1.5))
            p.drawEllipse(sl.adjusted(.75, .75, -.75, -.75))
        tx = L + (20 if self.kind == "artist" else 0)
        f = p.font()
        f.setPixelSize(13)
        f.setWeight(f.Weight.DemiBold)
        p.setFont(f)
        p.setPen(T.fg)
        al = Qt.AlignVCenter | (Qt.AlignHCenter if self.kind == "artist" else Qt.AlignLeft)
        p.drawText(QRectF(tx, T0 + S + 8, S, 18), al, QFontMetrics(f).elidedText(name, Qt.ElideRight, S))
        f.setPixelSize(12)
        f.setWeight(f.Weight.Normal)
        p.setFont(f)
        m = QColor(T.fg)
        m.setAlphaF(0.6)
        p.setPen(m)
        p.drawText(QRectF(tx, T0 + S + 27, S, 16), al, f"{n} track{'s' if n != 1 else ''}")
        p.restore()

class GroupGrid(QListWidget):
    """hover interpolado por timer"""
    def __init__(self, kind):
        super().__init__()
        self.kind, self._hp, self._tg, self._hov = kind, {}, {}, None
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSpacing(4)
        self.setItemDelegate(GroupDelegate(kind))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._t = QTimer(self, interval=16, timeout=self._tick)
    def _target(self, row):
        if row == self._hov:
            return
        if self._hov is not None:
            self._tg[self._hov] = 0.0
        self._hov = row
        if row is not None:
            self._tg[row] = 1.0
        self._t.start()
    def mouseMoveEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        self._target(self.row(it) if it else None)
        super().mouseMoveEvent(e)
    def leaveEvent(self, e):
        self._target(None)
        super().leaveEvent(e)
    def _tick(self):
        busy = False
        for r, t in list(self._tg.items()):
            v = self._hp.get(r, 0.0)
            v += (t - v) * 0.28
            if abs(t - v) < 0.01:
                v = t
            else:
                busy = True
            self._hp[r] = v
            if v == 0.0 and t == 0.0:
                self._hp.pop(r)
                self._tg.pop(r)
        self.viewport().update()
        if not busy:
            self._t.stop()
    def fill(self, groups, covers):
        self.clear()
        self._hp.clear()
        self._tg.clear()
        self._hov = None
        for g in groups:
            it = QListWidgetItem(g["name"])
            it.setData(Qt.UserRole, g["name"])
            it.setData(Qt.UserRole + 1, covers.get(g["name"]))
            it.setData(Qt.UserRole + 2, g["n"])
            self.addItem(it)

class CollectionDetail(QWidget):
    """detalhe de álbum/artista, igual ao da playlist"""
    def __init__(self, win, kicker, round_cover=False):
        super().__init__()
        self.win, self._ctx, self.rows = win, None, []
        d = QWidget()
        dl = QVBoxLayout(d)
        dl.setContentsMargins(0, 0, 10, 12)
        dl.setSpacing(14)
        top = QHBoxLayout()
        top.setSpacing(18)
        self.back = GlassButton("", "arrow-left", "glass", size=36, tooltip="Back")
        top.addWidget(self.back, 0, Qt.AlignTop)
        self.cover = CoverLabel(150, 75 if round_cover else 12)
        top.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addStretch()
        self.kicker = QLabel(kicker, objectName="sectionTitle")
        info.addWidget(self.kicker)
        self.name = QLabel("")
        self.name.setObjectName("colTitle")
        self.name.setIndent(0)
        self.name.setStyleSheet("QLabel#colTitle{font-size:34px;font-weight:700;padding:0 6px;}")
        self.sub = QLabel("")
        self.sub.setObjectName("colSub")
        self.sub.setIndent(0)
        self.sub.setStyleSheet("QLabel#colSub{padding:2px 6px;}")
        self.meta = QLabel("", objectName="muted")
        self.meta.setContentsMargins(6, 0, 0, 0)
        for w in (self.name, self.sub, self.meta):
            info.addWidget(w)
        info.addStretch()
        top.addLayout(info, 1)
        dl.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)
        self.play_big = PlayFab(56, "Play")
        self.play_big.truth = lambda: now.ctx_playing(self._ctx)
        self.play_big.clicked.connect(lambda _=False: self.toggle_play())
        row.addWidget(self.play_big)
        shuf = GlassButton("", "shuffle", "ghost", size=42, tooltip="Shuffle play", icon_size=22)
        shuf.clicked.connect(lambda _=False: self.play_from(0, True))
        row.addWidget(shuf)
        more = GlassButton("", "more", "ghost", size=42, tooltip="More options", icon_size=22)
        more.clicked.connect(lambda: self._more(more))
        row.addWidget(more)
        row.addStretch()
        dl.addLayout(row)
        self.rl = RowList()
        self.rl.setItemDelegate(RowDelegate(num=True, extra=True))
        self.rl.setMouseTracking(True)
        self.rl.setFocusPolicy(Qt.NoFocus)
        self.rl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rl.rows = []
        self.rl.play_row.connect(self.row_play)
        self.rl.itemDoubleClicked.connect(lambda it: self.play_from(self.rl.row(it), self.win.queue.shuffle))
        self.rl.customContextMenuRequested.connect(lambda p: show_track_menu(win, self.rl, p))
        dl.addWidget(self.rl)
        dl.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(d)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(sc)
        now.changed.connect(self._sync)
    def load(self, title, sub, rows, cover, ctx):
        self._ctx, self.rows = ctx, list(rows)
        self.rl.rows = self.rows
        self.rl.clear()
        for t in self.rows:
            it = QListWidgetItem(t["title"])
            it.setData(Qt.UserRole, t["id"])
            it.setData(ROW_ROLE, t)
            self.rl.addItem(it)
        self.rl.setFixedHeight(len(self.rows) * 58 + 6)
        self.name.setText(title)
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        mins = int(sum(r["duration"] or 0 for r in self.rows) // 60)
        self.meta.setText(f"{len(self.rows)} track{'s' if len(self.rows) != 1 else ''}  ·  {mins} min")
        self.cover.set_cover(cover)
        self._sync()
    def _sync(self, *_):
        try:
            self.play_big.set_playing(now.ctx_playing(self._ctx))
        except RuntimeError:
            pass
    def toggle_play(self):
        if self.rows or now.is_ctx(self._ctx):
            self.win.toggle_context(self._ctx, self.rows)
    def play_from(self, start, shuffle):
        if self.rows:
            self.win.set_shuffle(shuffle)
            self.win.play_list(self.rows, start, ctx=self._ctx)
    def row_play(self, r):
        if 0 <= r < len(self.rows):
            self.win.play_row(self.rows, r, self._ctx, shuffle=self.win.queue.shuffle)
    def _more(self, btn):
        m = GlassMenu(self)
        q = self.win.queue
        ids = [t["id"] for t in self.rows]
        m.addAction(icons.icon("skip-forward", T.fg.name(), 16), "Play next", lambda: [q.play_next(i) for i in reversed(ids)])
        m.addAction(icons.icon("list-music", T.fg.name(), 16), "Add to queue", lambda: [q.add_end(i) for i in ids])
        m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

class GroupPage(QWidget):
    def __init__(self, win, field, title):
        super().__init__()
        self.win, self.field, self.title, self.cur = win, field, title, None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        g = QWidget()
        gl = QVBoxLayout(g)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(12)
        gl.addWidget(h1(title))
        self.empty = QLabel("Nothing here yet. Import some music.", objectName="muted")
        gl.addWidget(self.empty)
        self.grid = GroupGrid("album" if field == "album" else "artist")
        gl.addWidget(self.grid)
        self.stack.addWidget(g)
        self.grid.itemClicked.connect(lambda it: self.open(it.data(Qt.UserRole)))
        self.detail = CollectionDetail(win, title[:-1].upper(), round_cover=(field != "album"))
        self.detail.back.setToolTip(f"Back to {title}")
        self.detail.back.clicked.connect(self.close_detail)
        self.stack.addWidget(self.detail)
        self.back, self.name, self.table = self.detail.back, self.detail.name, self.detail.rl
    def ctx(self):
        return (self.field, self.cur) if self.cur else None
    def refresh(self):
        gs = self.win.lib.groups(self.field)
        self.names = [g["name"] for g in gs]
        self.grid.fill(gs, self.win.lib.group_covers(self.field))
        self.empty.setVisible(not gs)
        self.grid.setVisible(bool(gs))
        if self.cur in self.names:
            self.open(self.cur)
        else:
            self.close_detail()
    def open(self, name):
        self.cur = name
        rows = self.win.lib.tracks_by(self.field, name)
        other = "artist" if self.field == "album" else "album"
        subs = []
        for r in rows:
            v = (r[other] or "").strip()
            if v and v not in subs:
                subs.append(v)
        sub = ", ".join(subs[:3]) + (" …" if len(subs) > 3 else "")
        self.detail.load(name, sub, rows, next((r["cover"] for r in rows if r["cover"]), None), self.ctx())
        self.stack.setCurrentIndex(1)
    def close_detail(self):
        self.cur = None
        self.stack.setCurrentIndex(0)
