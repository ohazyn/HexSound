import platform, sys, time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFontMetrics, QLinearGradient, QRadialGradient, QPen
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QLineEdit, QMenu, QAbstractItemView,
    QHeaderView, QApplication, QScrollArea, QFrame, QDialog, QComboBox, QCheckBox, QProgressBar, QPlainTextEdit, QStyledItemDelegate, QStyle, QStackedWidget)
from hexsound import __version__
from hexsound.app import backup
from hexsound.app.autostart import set_autostart
from hexsound.app.paths import DATA_DIR, resource
from hexsound.importers.worker import LinkWorker
from hexsound.metadata.tags import AUDIO_EXT, COVERS_DIR, save_cover_bytes
from hexsound.playlists import share
from hexsound.ui import icons
from hexsound.ui import dialogs
from hexsound.ui.dialogs import GlassMenu
from hexsound.ui.downloads import DownloadQueue
from hexsound.ui import pickers
from hexsound.ui.dialogs import NewPlaylistDialog
from hexsound.ui.home import CoverLabel, load_cover
from hexsound.ui.nowstate import now
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton, GlassCombo, PlayFab, SearchField, Segmented, _anim, _to

SORTS = [("Title", "title"), ("Artist", "artist"), ("Duration", "duration"),
         ("Date imported", "imported"), ("Last played", "played")]

def fmt(sec):
    s = int(sec or 0)
    return f"{s // 60}:{s % 60:02d}"

def h1(text):
    l = QLabel(text)
    l.setObjectName("h1")
    return l

def gbtn(text, icon=None, kind="glass", tip=""):
    return GlassButton(text, icon, kind, size=34, tooltip=tip)

def _cover_rect(p, rect, path, size, radius):
    clip = QPainterPath()
    clip.addRoundedRect(rect, radius, radius)
    p.save()
    p.setClipPath(clip)
    pm = load_cover(path, size)
    if pm:
        p.drawPixmap(rect.toRect(), pm)
    else:
        p.fillPath(clip, T.ovc(0.10))
        k = rect.width() * 0.40
        icons.draw(p, "music", QRectF(rect.center().x() - k / 2, rect.center().y() - k / 2, k, k), T.fg.name(), opacity=0.45)
    p.restore()

ROW_ROLE = Qt.UserRole + 5

def _row(o, idx):
    d = idx.data(ROW_ROLE)
    return d if d is not None else o.widget.rows[idx.row()]

def _plate(p, o, idx):
    """barra de seleção/hover contínua por linha"""
    v = o.widget
    cols = v.columnCount() if hasattr(v, "columnCount") else 1
    if cols > 1:
        x0 = v.columnViewportPosition(0)
        x1 = v.columnViewportPosition(cols - 1) + v.columnWidth(cols - 1)
        full = QRectF(x0, o.rect.top() + 2, x1 - x0, o.rect.height() - 4)
        hov = getattr(v, "_hover", -1) == idx.row()
    else:
        full = QRectF(o.rect).adjusted(0, 2, 0, -2)
        hov = bool(o.state & QStyle.State_MouseOver)
    sel = bool(o.state & QStyle.State_Selected)
    if not (sel or hov):
        return
    p.save()
    p.setClipRect(o.rect)
    p.setRenderHint(QPainter.Antialiasing)
    a = T.accent
    if sel:
        g = QLinearGradient(full.topLeft(), full.bottomLeft())
        g.setColorAt(0, QColor(a.red(), a.green(), a.blue(), 105))
        g.setColorAt(1, QColor(a.red(), a.green(), a.blue(), 70))
        p.setBrush(g)
        p.setPen(QPen(T.ovc(0.20), 1))
        p.drawRoundedRect(full.adjusted(.5, .5, -.5, -.5), 12, 12)
    else:
        p.setBrush(T.ovc(0.06))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(full, 12, 12)
    p.restore()

class CellDelegate(QStyledItemDelegate):
    def sizeHint(self, o, i):
        return QSize(60, 58)
    def paint(self, p, o, idx):
        t = _row(o, idx)
        _plate(p, o, idx)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if not t["available"]:
            p.setOpacity(0.45)
        f = p.font()
        f.setPixelSize(13)
        p.setFont(f)
        c = QColor(T.fg)
        c.setAlphaF(0.88)
        p.setPen(c)
        al = idx.data(Qt.TextAlignmentRole)
        al = Qt.AlignLeft | Qt.AlignVCenter if al is None else Qt.Alignment(al)
        r = QRectF(o.rect).adjusted(8, 0, -8, 0)
        p.drawText(r, int(al), QFontMetrics(f).elidedText(str(idx.data(Qt.DisplayRole) or ""), Qt.ElideRight, int(r.width())))
        if idx.column() == 2 and _hovered(o, idx):
            icons.draw(p, "more", QRectF(o.rect.left() + 8, o.rect.center().y() - 9, 18, 18), T.fg.name())
        p.restore()

G_NUM = 40

def draw_eq(p, cx, cy, phase, color, h=15):
    """barrinhas animadas da faixa atual"""
    import math
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    w, gap = 3.0, 2.2
    x = cx - (3 * w + 2 * gap) / 2
    for i in range(3):
        k = 0.30 + 0.70 * abs(math.sin(phase * 0.42 + i * 1.7))
        bh = h * k
        p.drawRoundedRect(QRectF(x + i * (w + gap), cy + h / 2 - bh, w, bh), 1.2, 1.2)
    p.restore()

def _is_current(t):
    try:
        return now.track_id is not None and t["id"] == now.track_id
    except (KeyError, IndexError, TypeError):
        return False

def _hovered(o, idx):
    v = o.widget
    return getattr(v, "_hover", -1) == idx.row() if hasattr(v, "columnCount") else bool(o.state & QStyle.State_MouseOver)

class RowDelegate(QStyledItemDelegate):
    """linha da tabela de faixas; extra = álbum, tempo e menu"""
    def __init__(self, heart=True, accent=False, num=False, extra=False):
        super().__init__()
        self.heart, self.accent, self.num, self.extra = heart, accent, num, extra
    def sizeHint(self, o, i):
        return QSize(100, 58)
    def paint(self, p, o, idx):
        t = _row(o, idx)
        _plate(p, o, idx)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(o.rect).adjusted(0, 2, 0, -2)
        hov = _hovered(o, idx)
        G = G_NUM if self.num else 0
        cur = _is_current(t)
        acc = T.accent.lighter(130) if T.dark else T.accent
        if self.num:  # nº → equalizador (tocando) / nº colorido (pausada); no hover vira play/pause
            cx, cy = r.left() + G / 2 - 2, r.center().y()
            if hov:
                icons.draw(p, "pause" if (cur and now.playing) else "play", QRectF(cx - 8, cy - 8, 16, 16), acc.name() if cur else T.fg.name(), True)
            elif cur and now.playing:
                draw_eq(p, cx, cy, now.phase, acc)
            else:
                f0 = p.font()
                f0.setPixelSize(13)
                f0.setWeight(f0.Weight.DemiBold if cur else f0.Weight.Normal)
                p.setFont(f0)
                m0 = QColor(acc) if cur else QColor(T.fg)
                m0.setAlphaF(1.0 if cur else 0.55)
                p.setPen(m0)
                p.drawText(QRectF(r.left(), r.top(), G, r.height()), Qt.AlignCenter, str(idx.row() + 1))
        if not t["available"]:
            p.setOpacity(0.45)
        _cover_rect(p, QRectF(r.left() + 6 + G, r.top() + 5, 44, 44), t["cover"], 44, 9)
        fav = bool(t["favorite"]) and self.heart
        tx = r.left() + 62 + G
        w = r.width() - 62 - G - 8
        if self.extra:
            w = min(w, r.width() * 0.50 - G - 40)
        f = p.font()
        f.setPixelSize(14)
        f.setWeight(f.Weight.DemiBold)
        p.setFont(f)
        p.setPen(acc if (self.accent or cur) else T.fg)
        title_txt = QFontMetrics(f).elidedText(t["title"] or "Unknown", Qt.ElideRight, int(w - (22 if fav else 0)))  # sobra espaço para o coração
        p.drawText(QRectF(tx, r.top() + 7, w, 20), Qt.AlignVCenter, title_txt)
        f.setPixelSize(12)
        f.setWeight(f.Weight.Normal)
        p.setFont(f)
        m = QColor(T.fg)
        m.setAlphaF(0.6)
        p.setPen(m)
        p.drawText(QRectF(tx, r.top() + 27, w, 18), Qt.AlignVCenter, QFontMetrics(f).elidedText(t["artist"] or "Unknown Artist", Qt.ElideRight, int(w)))
        if fav:
            f.setPixelSize(14)
            f.setWeight(f.Weight.DemiBold)
            tw = QFontMetrics(f).horizontalAdvance(title_txt)
            hx = tx + tw + 8
            icons.draw(p, "heart", QRectF(hx, r.top() + 10, 13, 13), T.accent.lighter(120).name(), True)
        if self.extra:
            f.setPixelSize(13)
            f.setWeight(f.Weight.Normal)
            p.setFont(f)
            ax = r.left() + r.width() * 0.55
            aw = r.width() * 0.45 - 130
            p.drawText(QRectF(ax, r.top(), aw, r.height()), Qt.AlignVCenter, QFontMetrics(f).elidedText(t["album"] or "", Qt.ElideRight, int(aw)))
            p.drawText(QRectF(r.right() - 84, r.top(), 56, r.height()), Qt.AlignVCenter | Qt.AlignRight, fmt(t["duration"]))
            if hov:
                icons.draw(p, "more", QRectF(r.right() - 24, r.center().y() - 9, 18, 18), T.fg.name())
        p.restore()

class TileDelegate(QStyledItemDelegate):
    S = 148
    def sizeHint(self, o, i):
        return QSize(self.S + 24, self.S + 70)
    def paint(self, p, o, idx):
        t = _row(o, idx)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(o.rect).adjusted(2, 2, -2, -2)
        if o.state & QStyle.State_Selected:
            p.setBrush(QColor(T.accent.red(), T.accent.green(), T.accent.blue(), 85))
            p.setPen(QPen(T.ovc(0.20), 1))
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 16, 16)
        elif o.state & QStyle.State_MouseOver:
            p.setBrush(T.ovc(0.07))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 16, 16)
        if not t["available"]:
            p.setOpacity(0.45)
        box = QRectF(r.left() + 10, r.top() + 10, self.S, self.S)
        if isinstance(t, dict) and t.get("new"):  # cartão "Nova playlist"
            p.setBrush(T.ovc(0.06))
            p.setPen(QPen(T.ovc(0.30), 1.5, Qt.DashLine))
            p.drawRoundedRect(box.adjusted(.75, .75, -.75, -.75), 16, 16)
            k = 44 + 6 * (1 if o.state & QStyle.State_MouseOver else 0)
            icons.draw(p, "plus", QRectF(box.center().x() - k / 2, box.center().y() - k / 2, k, k), T.accent.lighter(125).name())
        else:
            _cover_rect(p, box, t["cover"], self.S, 16)
        f = p.font()
        f.setPixelSize(13)
        f.setWeight(f.Weight.DemiBold)
        p.setFont(f)
        p.setPen(T.fg)
        w = self.S
        p.drawText(QRectF(r.left() + 10, r.top() + self.S + 18, w, 18), Qt.AlignVCenter, QFontMetrics(f).elidedText(t["title"] or "Unknown", Qt.ElideRight, w))
        f.setPixelSize(12)
        f.setWeight(f.Weight.Normal)
        p.setFont(f)
        m = QColor(T.fg)
        m.setAlphaF(0.6)
        p.setPen(m)
        p.drawText(QRectF(r.left() + 10, r.top() + self.S + 37, w, 16), Qt.AlignVCenter, QFontMetrics(f).elidedText(t["artist"] or "Unknown Artist", Qt.ElideRight, w))
        p.restore()

class TrackTable(QTableWidget):
    play_row = Signal(int)
    def __init__(self):
        super().__init__(0, 3)
        self.setHorizontalHeaderLabels(["TITLE", "ALBUM", "TIME"])
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.horizontalHeaderItem(2).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setMouseTracking(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        self.setColumnWidth(2, 104)
        self.rows = []
        self.setFocusPolicy(Qt.NoFocus)
        self.verticalHeader().setDefaultSectionSize(58)
        self._hover = -1
        self.setItemDelegateForColumn(0, RowDelegate(num=True))
        self.setItemDelegateForColumn(1, CellDelegate())
        self.setItemDelegateForColumn(2, CellDelegate())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        now.changed.connect(self.viewport().update)
        now.tick.connect(self.viewport().update)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            pos = e.position().toPoint()
            i = self.indexAt(pos)
            if i.isValid() and i.column() == 0 and pos.x() - self.columnViewportPosition(0) < G_NUM:
                self.play_row.emit(i.row())
                return
            if i.isValid() and i.column() == 2 and pos.x() - self.columnViewportPosition(2) < 34:
                self.setCurrentCell(i.row(), 0)
                self.customContextMenuRequested.emit(pos)
                return
        super().mousePressEvent(e)
    def mouseMoveEvent(self, e):
        r = self.rowAt(int(e.position().y()))
        if r != self._hover:
            self._hover = r
            self.viewport().update()
        super().mouseMoveEvent(e)
    def leaveEvent(self, e):
        self._hover = -1
        self.viewport().update()
        super().leaveEvent(e)
    def fill(self, rows):
        self._hover = -1
        self.rows = list(rows)
        self.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, v in enumerate([r["title"], r["album"], fmt(r["duration"])]):
                it = QTableWidgetItem(v if c else "")
                if c == 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c and not r["available"]:
                    it.setForeground(Qt.gray)
                self.setItem(i, c, it)

class TrackGrid(QListWidget):
    """mesma interface da TrackTable, em grade"""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setItemDelegate(TileDelegate())
        self.setSpacing(2)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    def fill(self, rows):
        self.rows = list(rows)
        self.clear()
        for r in rows:
            self.addItem(QListWidgetItem(r["title"]))

class RowList(QListWidget):
    play_row = Signal(int)
    def __init__(self):
        super().__init__()
        now.changed.connect(self.viewport().update)
        now.tick.connect(self.viewport().update)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            pos = e.position().toPoint()
            it = self.itemAt(pos)
            if it and pos.x() < G_NUM:
                self.play_row.emit(self.row(it))
                return
            if it and pos.x() > self.viewport().width() - 40:
                self.setCurrentItem(it)
                self.customContextMenuRequested.emit(pos)
                return
        super().mousePressEvent(e)

def show_track_menu(win, table, pos):
    row = table.currentRow()
    if row < 0 or row >= len(table.rows):
        return
    t = table.rows[row]
    m = GlassMenu(table)
    m.act("skip-forward", "Play next", lambda: win.queue.play_next(t["id"]))
    m.act("list-music", "Add to queue", lambda: win.queue.add_end(t["id"]))
    m.act("heart", "Remove favorite" if t["favorite"] else "Add to favorites",
          lambda: (win.lib.set_favorite(t["id"], not t["favorite"]), win.refresh_all()))
    m.addSeparator()
    sub = m.sub("plus", "Add to playlist")
    for p in win.lib.playlists():
        sub.act("list-music", p["name"], lambda pid=p["id"]: win.lib.add_to_playlist(pid, t["id"]))
    if not win.lib.playlists():
        sub.addAction("No playlists yet").setEnabled(False)
    m.addSeparator()
    m.act("trash", "Remove from library", lambda: (win.lib.delete_track(t["id"]), win.refresh_all()), danger=True)
    m.exec(table.viewport().mapToGlobal(pos))

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
        self.search.textChanged.connect(self.refresh)
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

class ImportPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.worker, self.target = win, None, None
        self._newpid = None
        self._meta = None
        self._tids = []
        self._pending = {}
        self._retry_wait = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(h1("Import Music"))
        self.status = QLabel("Paste a link below, drop audio files anywhere in the window, press Ctrl+V after copying files, or use the buttons.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        for text, ic, fn in [("Add files", "file-plus", self.files), ("Add folder", "folder-plus", self.folder)]:
            b = gbtn(text, ic)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        row = QHBoxLayout()
        self.link = SearchField("Paste a Spotify / YouTube / SoundCloud link")
        self.link.actions()[0].setIcon(icons.icon("link", T.fg.name(), 16))
        self.dest = GlassCombo()
        self.go = gbtn("Download", "download", "accent")
        self.stop = gbtn("Cancel", "x")
        self.stop.hide()
        self.go.clicked.connect(lambda: self.start_links(self.link.text()))
        self.link.returnPressed.connect(self.go.click)
        self.stop.clicked.connect(self.cancel)
        row.addWidget(self.link, 1)
        row.addWidget(QLabel("Add to"))
        row.addWidget(self.dest)
        row.addWidget(self.go)
        row.addWidget(self.stop)
        lay.addLayout(row)
        srow = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        self.play_all = gbtn("Play", "play", "glass")
        self.play_all.hide()
        self.retry = gbtn("Retry failed", "refresh", "glass")
        self.retry.hide()
        self.retry.clicked.connect(self.retry_failed)
        self.play_all.clicked.connect(self.play_imported)
        srow.addWidget(self.summary, 1)
        srow.addWidget(self.retry)
        srow.addWidget(self.play_all)
        lay.addLayout(srow)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)
        self.queue = DownloadQueue()
        self.queue.play.connect(self.play_one)
        self.queue.retry.connect(lambda i: self.retry_rows([i]))
        lay.addWidget(self.queue, 1)
        self.logbox = QPlainTextEdit(readOnly=True)
        self.logbox.setMaximumHeight(64)
        lay.addWidget(self.logbox)
    def refresh(self):
        cur = self.dest.currentData()
        self.dest.clear()
        self.dest.addItem("Library only", None)
        self.dest.addItem("New playlist from link", "__new__")
        for p in self.win.lib.playlists():
            self.dest.addItem(p["name"], p["id"])
        i = self.dest.findData(cur)
        self.dest.setCurrentIndex(max(i, 0))
    def files(self):
        fs = pickers.pick_files(self, "Add audio files", sorted(AUDIO_EXT))
        if fs:
            self.win.import_paths(fs)
    def folder(self):
        d = pickers.pick_dir(self, "Add a folder of music")
        if d:
            self.win.import_paths([d])
    @property
    def busy(self):
        return bool(self.worker and self.worker.isRunning())
    def start_links(self, text, pid=None, keep=False):
        if not text.strip() or self.busy:
            return
        self.target = pid or self.dest.currentData()
        self._newpid = None if not keep else self._newpid
        self._meta = None
        self._tids = [] if not keep else self._tids
        base = 0
        if keep:
            base = max(self.queue.rows, default=-1) + 1
            self.logbox.appendPlainText("— Retrying —")
        else:
            self.logbox.clear()
            self.queue.clear()
            self._pending = {}
        self.play_all.hide()
        self.retry.hide()
        self.summary.setText("Reading link…")
        self.bar.setRange(0, 0)
        self.go.setEnabled(False)
        self.stop.show()
        self.stop.setEnabled(True)
        lib = self.win.lib
        rows = lib.tracks()
        known = {(r["source"], r["source_id"]) for r in rows}
        songs = [(r["id"], r["title"], r["artist"] or "", float(r["duration"] or 0)) for r in rows]
        w = self.worker = LinkWorker(text, known, self.win.settings["download_dir"], songs, idx_base=base)
        w.log.connect(self.on_log)
        w.meta.connect(self.on_meta)
        w.queue.connect(self.on_queue)
        w.state.connect(self.queue.set_state)
        w.progress.connect(self.on_progress)
        w.track.connect(self.add_downloaded)
        w.known.connect(self.on_known)
        w.done.connect(self.on_done)
        w.start()
    def cancel(self):
        if self.busy:
            self.worker.cancel()
            self.stop.setEnabled(False)
            self.summary.setText("Cancelling…")
    def on_meta(self, name):
        self._meta = name
    def on_queue(self, entries):
        self.queue.add_entries(entries)
        self._pending.update({e["idx"]: e for e in entries})
        self.bar.setRange(0, max(len(entries), 1))
        self.bar.setValue(0)
        if not entries:
            self.queue.reset_hint()
    def _counts(self):
        st = [r.state for r in self.queue.rows.values()]
        return st.count("done"), st.count("failed") + st.count("cancelled"), st.count("skipped"), len(st)
    def _bar_to(self, v):
        if T.reduce:
            self.bar.setValue(v)
            return
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        a = getattr(self, "_bar_anim", None)
        if a is None:
            a = self._bar_anim = QPropertyAnimation(self.bar, b"value", self)
            a.setDuration(380)
            a.setEasingCurve(QEasingCurve.OutCubic)
        a.stop()
        a.setStartValue(self.bar.value())
        a.setEndValue(v)
        a.start()
    def on_progress(self, i, n):
        ok, bad, skip, total = self._counts()
        fin = ok + bad + skip
        self.bar.setRange(0, max(total, 1))
        self._bar_to(min(fin, total))
        self.summary.setText(f"{fin} of {total} finished" if total else "")
    def on_done(self, ok, bad, skipped):
        ok, bad, skipped, total = self._counts()
        parts = [f"{ok} added"] + ([f"{skipped} already in library"] if skipped else []) + ([f"{bad} failed"] if bad else [])
        self.summary.setText("Done: " + ", ".join(parts) + ".")
        self.logbox.appendPlainText(f"Done: {ok} imported, {skipped} duplicate(s) skipped, {bad} failed.")
        self.go.setEnabled(True)
        self.stop.hide()
        self.bar.setRange(0, 1)
        self._bar_to(1 if (ok or skipped) else 0)
        self.play_all.setVisible(bool(self._tids))
        self.win.refresh_all()
        self.refresh_playlists_keep()
        self.retry.setVisible(bad > 0)
        if self._retry_wait:
            wait, self._retry_wait = self._retry_wait, []
            self._do_retry(wait)
    def retry_rows(self, idxs):
        """refaz as faixas que falharam ou foram canceladas"""
        idxs = [i for i in idxs if i in self.queue.rows and self.queue.rows[i].retryable and self._pending.get(i, {}).get("url")]
        if not idxs:
            return
        if self.busy:  # já tem download rodando: entra na vez, a linha mostra "Waiting"
            for i in idxs:
                if i not in self._retry_wait:
                    self._retry_wait.append(i)
                    self.queue.rows[i].set_state("queued")
            return
        self._do_retry(idxs)
    def _do_retry(self, idxs):
        idxs = [i for i in idxs if i in self.queue.rows and self._pending.get(i, {}).get("url")]
        if not idxs or self.busy:
            return
        text = "\n".join(self._pending[i]["url"] for i in idxs)
        for i in idxs:
            self.queue.remove(i)
            self._pending.pop(i, None)
        self.start_links(text, self._newpid or self.target, keep=True)
    def retry_failed(self):
        self.retry_rows([i for i, r in self.queue.rows.items() if r.retryable])
    def refresh_playlists_keep(self):
        cur = self.dest.currentData()
        self.refresh()
        if cur and cur != "__new__":
            self.dest.setCurrentIndex(max(self.dest.findData(cur), 0))
    def on_log(self, m):
        self.logbox.appendPlainText(m)
        if m.startswith(("Failed", "Could not")):
            self.win.log_error(m)
    def _playlist(self):
        if self.target == "__new__":
            if not self._newpid:
                self._newpid = self.win.lib.create_playlist(self._meta or "Imported playlist")
            return self._newpid
        return self.target
    def _add_to_target(self, tid):
        if tid is None:
            return
        pid = self._playlist()
        if pid:
            self.win.lib.add_to_playlist(pid, tid)
    def on_known(self, it):
        tid = it.get("track_id")
        if tid is None and it.get("source"):
            r = self.win.lib.find_source(it["source"], it["id"])
            tid = r["id"] if r else None
        self._add_to_target(tid)
        if tid is not None and tid not in self._tids:
            self._tids.append(tid)
    def add_downloaded(self, it, path):
        tid, _ = self.win.lib.add_track(it["title"], it["artist"], it.get("album", ""), it["duration"], path=path,
                                        source=it["source"], source_id=it["id"], cover=it.get("cover"))
        if it.get("cover"):
            self.win.lib.set_cover(tid, it["cover"])
        self._add_to_target(tid)
        self._tids.append(tid)
        row = self.queue.rows.get(it.get("idx"))
        if row is not None:
            row.title, row.artist = it["title"], it["artist"]
            row.set_done(tid, it.get("cover"))
    def play_one(self, tid):
        t = self.win.lib.get_track(tid)
        if t:
            self.win.play_list([t], 0)
    def play_imported(self):
        rows = [r for r in (self.win.lib.get_track(t) for t in self._tids) if r]
        if rows:
            self.win.play_list(rows, 0)

class CreditsPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        c = CoverLabel(128, 28)
        c.set_cover(str(resource("assets/icon.png")))
        lay.addWidget(c, 0, Qt.AlignCenter)
        t = QLabel("HexSound")
        t.setObjectName("h1")
        t.setAlignment(Qt.AlignCenter)
        m = QLabel("Made by Hazyn")
        m.setAlignment(Qt.AlignCenter)
        v = QLabel(f"Version {__version__}\n\nTechnologies: Python (PSF License) · PySide6 / Qt (LGPLv3) · SQLite (public domain)\n"
                   "Libraries: Mutagen (GPLv2+) · yt-dlp (Unlicense) · PyInstaller (GPLv2 with exception)\n"
                   "Icons: Lucide (ISC License) · App icon artwork: provided by the author (original artist not credited)\n"
                   "License: personal use. Respect the terms of the services you import from.")
        v.setObjectName("muted")
        v.setAlignment(Qt.AlignCenter)
        v.setWordWrap(True)
        for w in (t, m, v):
            lay.addWidget(w)
