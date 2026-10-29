"""Linhas, cartões e tabelas de faixas (delegates) e o menu de contexto de uma faixa."""
from PySide6.QtCore import Qt, QSize, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QFontMetrics, QPen
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QStyledItemDelegate, QStyle)
from hexsound.ui import icons
from hexsound.ui.dialogs import GlassMenu
from hexsound.ui.nowstate import now
from hexsound.ui.style import T
from hexsound.ui.pages.common import G_NUM, _cover_rect, _hovered, _is_current, _plate, _row, draw_eq, fmt

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
