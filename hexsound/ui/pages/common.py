"""Utilitários e peças de desenho compartilhados pelas telas (formatação, capa arredondada, placa de seleção, equalizador)."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QLabel, QStyle
from hexsound.ui import icons
from hexsound.ui.home import load_cover
from hexsound.ui.nowstate import now
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton

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
