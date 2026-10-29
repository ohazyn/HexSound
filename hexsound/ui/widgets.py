import time
from PySide6.QtCore import (Qt, QObject, Signal, QRectF, QPointF, QVariantAnimation, QEasingCurve, QSize, Property, QPoint, QTimer)
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QLinearGradient, QRadialGradient, QPen, QImage, QFontMetrics, QPixmap)
from PySide6.QtWidgets import QWidget, QFrame, QAbstractButton, QSlider, QHBoxLayout, QVBoxLayout, QSizePolicy, QLineEdit, QComboBox, QListView, QStyledItemDelegate, QStyle
from hexsound.ui import icons
from hexsound.ui.style import T, paint_sheet
from hexsound.ui.background import bg

def _anim(owner, setter, start=0.0, ms=140):
    a = QVariantAnimation(owner)
    a.setDuration(ms)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.valueChanged.connect(setter)
    a.setStartValue(start)
    return a

def _to(a, cur, end):
    a.stop()
    a.setStartValue(cur)
    a.setEndValue(end)
    a.start()

class Ambient(QObject):
    changed = Signal()
    def __init__(self):
        super().__init__()
        self.color = QColor(T.accent)
        self._anim = None
        self._from = QColor(T.accent)
    def set_from_cover(self, path):
        target = QColor(T.accent)
        if path:
            img = QImage(path)
            if not img.isNull():
                c = img.scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixelColor(0, 0).toHsv()
                target = QColor.fromHsv(c.hue() if c.hue() >= 0 else 260, max(c.saturation(), 130), min(max(c.value(), 120), 210))
        self.glide(target)
    def glide(self, target):
        self._from = QColor(self.color)
        if T.reduce:
            self.color = QColor(target)
            self.changed.emit()
            return
        if self._anim:
            self._anim.stop()
        a = self._anim = QVariantAnimation(self)
        a.setDuration(700)
        a.setEasingCurve(QEasingCurve.InOutCubic)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(lambda t, f=QColor(self._from), g=QColor(target): self._mix(f, g, t))
        a.start()
    def _mix(self, f, g, t):
        self.color = QColor(int(f.red() + (g.red() - f.red()) * t), int(f.green() + (g.green() - f.green()) * t),
                            int(f.blue() + (g.blue() - f.blue()) * t))
        self.changed.emit()

ambient = Ambient()

class Backdrop(QWidget):
    def __init__(self):
        super().__init__()
        ambient.changed.connect(self.update)
        bg.changed.connect(self.update)
    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect())
        w, h = r.width(), r.height()
        if bg.has_image:  # imagem / GIF
            pm = bg.shown
            s = max(w / pm.width(), h / pm.height())
            sw, sh = w / s, h / s
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(r, pm, QRectF((pm.width() - sw) / 2, (pm.height() - sh) / 2, sw, sh))
            p.fillRect(self.rect(), QColor(0, 0, 0, int(2.55 * bg.dim)) if T.dark else QColor(255, 255, 255, int(2.55 * bg.dim)))
            p.setPen(QPen(T.ovc(0.14), 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
            return
        if bg.mode == "color":
            top = QColor(bg.color)
            bot = QColor(bg.color).darker(260 if T.dark else 100)
            if not T.dark:
                top = top.lighter(125)
        else:
            top, bot = T.base2, T.base
        g = QLinearGradient(0, 0, w * 0.4, h)
        g.setColorAt(0, top)
        g.setColorAt(1, bot)
        p.fillRect(self.rect(), g)
        p.setPen(QPen(T.ovc(0.14), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if T.reduce:
            return
        p.setRenderHint(QPainter.Antialiasing)
        k = (0.55 if T.dark else 0.38) * (0.45 if T.name == "black" else 1.0)
        orb = QColor(bg.color).lighter(170) if bg.mode == "color" else ambient.color  # modo cor: o brilho vem da própria cor
        for (cx, cy, rad, col, a) in ((0.12, 0.10, 0.70, orb, k), (0.92, 0.35, 0.60, orb if bg.mode == "color" else T.accent, k * 0.7),
                                      (0.55, 1.05, 0.75, orb.darker(140) if T.dark else orb, k * 0.8)):
            c = QColor(col)
            c.setAlphaF(a)
            e = QColor(col)
            e.setAlphaF(0)
            rg = QRadialGradient(QPointF(w * cx, h * cy), max(w, h) * rad)
            rg.setColorAt(0, c)
            rg.setColorAt(1, e)
            p.fillRect(self.rect(), rg)

class GlassPanel(QFrame):
    def __init__(self, radius=24, name=""):
        super().__init__()
        self.radius = radius
        if name:
            self.setObjectName(name)
        self.setAttribute(Qt.WA_StyledBackground, False)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        k = T.glass_k
        dark = T.dark
        wh = lambda a: QColor(255, 255, 255, int(255 * max(0.0, min(1.0, a))))
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0, wh(0.10 * k if dark else 0.55 * k))
        fill.setColorAt(1, wh(0.035 * k if dark else 0.30 * k))
        p.fillPath(path, fill)
        if not T.reduce:  # reflexo: faixa de luz no topo
            p.save()
            p.setClipPath(path)
            sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + min(rect.height(), 90)))
            sheen.setColorAt(0, wh(0.09 * k if dark else 0.45 * k))
            sheen.setColorAt(1, wh(0))
            p.fillRect(rect, sheen)
            p.restore()
        bd = QLinearGradient(rect.topLeft(), rect.bottomRight())
        bd.setColorAt(0, wh(0.30 * min(k, 1.3) if dark else 0.95))
        bd.setColorAt(0.5, wh(0.08) if dark else QColor(0, 0, 0, 22))
        bd.setColorAt(1, wh(0.16) if dark else QColor(255, 255, 255, 170))
        p.setPen(QPen(bd, 1))
        p.drawPath(path)

class GlassButton(QAbstractButton):
    """kind: glass | ghost | primary | accent | danger"""
    def __init__(self, text="", icon_name=None, kind="glass", size=None, tooltip="", icon_size=None):
        super().__init__()
        self.setText(text)
        self.kind, self._icon, self._fill = kind, icon_name, False
        self._h = self._p = 0.0
        self._m = 1.0 if icon_name == "pause" else 0.0  # play <-> pause
        self._size = size
        self._isz = icon_size
        self._ha = _anim(self, self._set_h)
        self._pa = _anim(self, self._set_p, ms=90)
        self._ma = _anim(self, self._set_m, ms=300)
        self._ma.setEasingCurve(QEasingCurve.OutBack)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        if tooltip:
            self.setToolTip(tooltip)
        pol = QSizePolicy.Fixed if (not text and size) else QSizePolicy.Minimum
        self.setSizePolicy(pol, QSizePolicy.Fixed)
    def _set_h(self, v):
        self._h = float(v)
        self.update()
    def _set_p(self, v):
        self._p = float(v)
        self.update()
    def _set_m(self, v):
        self._m = float(v)
        self.update()
    def set_icon(self, name, fill=None):
        morph = {self._icon, name} == {"play", "pause"} and self._icon != name and not T.reduce
        self._icon = name
        if fill is not None:
            self._fill = fill
        if name in ("play", "pause"):
            if morph:
                _to(self._ma, self._m, 1.0 if name == "pause" else 0.0)
            else:
                self._ma.stop()
                self._m = 1.0 if name == "pause" else 0.0
        self.update()
    def set_fill(self, fill):
        self._fill = fill
        self.update()
    def setIcon(self, *_):
        pass  # compat: use set_icon(nome)
    def enterEvent(self, e):
        _to(self._ha, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._ha, self._h, 0.0)
        _to(self._pa, self._p, 0.0)
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        _to(self._pa, self._p, 1.0)
        super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        _to(self._pa, self._p, 0.0)
        super().mouseReleaseEvent(e)
    def sizeHint(self):
        fm = QFontMetrics(self.font())
        h = self._size or 36
        if not self.text():
            return QSize(h, h)
        w = fm.horizontalAdvance(self.text()) + 30 + (22 if self._icon else 0)
        return QSize(w, h)
    def minimumSizeHint(self):
        return self.sizeHint()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        en = self.isEnabled()
        on = self.isChecked()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = 1.0 - 0.06 * self._p
        r = QRectF(r.center().x() - r.width() * s / 2, r.center().y() - r.height() * s / 2, r.width() * s, r.height() * s)
        rad = r.height() / 2
        h = self._h
        fg = T.fg
        k = self.kind
        if not en:
            p.setOpacity(0.35)
        if k == "primary":
            bg = QColor(255, 255, 255) if T.dark else QColor(28, 28, 30)
            bg = bg.lighter(100 + int(h * 6)) if T.dark else bg
            icfg = QColor(10, 10, 14) if T.dark else QColor(255, 255, 255)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, rad, rad)
        elif k in ("accent", "destructive"):
            bg = QColor("#ff453a") if k == "destructive" else QColor(T.accent)
            bg = bg.lighter(100 + int(h * 12))
            icfg = QColor("#ffffff")
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, rad, rad)
        else:
            icfg = QColor(T.accent).lighter(125) if (on and T.dark) else (QColor(T.accent) if on else QColor(fg))
            if k == "danger":
                icfg = QColor("#ff453a") if h > 0 else QColor("#ff7a70")  # vermelho sempre visível: apagar é uma ação destrutiva
            base = (0.08 if k == "glass" else 0.0) + (0.10 if on and k != "ghost" else 0) + 0.07 * h + 0.06 * self._p
            if base > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(T.ovc(base if T.dark else base * 0.8))
                p.drawRoundedRect(r, rad, rad)
            if k == "glass":
                bd = QLinearGradient(r.topLeft(), r.bottomRight())
                bd.setColorAt(0, T.ovc(0.28 + 0.1 * h))
                bd.setColorAt(1, T.ovc(0.08))
                p.setPen(QPen(bd, 1))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, rad, rad)
            if not on and k in ("ghost", "icon") and not self.text():
                icfg.setAlphaF(0.72 + 0.28 * h)
        col = icfg.name()
        has_t = bool(self.text())
        isz = (self._isz or (18 if has_t else min(22, int(self.height() * 0.46)))) * (1 + 0.10 * h)
        if has_t:
            fm = QFontMetrics(self.font())
            tw = fm.horizontalAdvance(self.text())
            gap = 8
            total = tw + ((isz + gap) if self._icon else 0)
            x = r.center().x() - total / 2
            if self._icon:
                icons.draw(p, self._icon, QRectF(x, r.center().y() - isz / 2, isz, isz), col, self._fill)
                x += isz + gap
            p.setPen(icfg)
            p.drawText(QRectF(x, r.top(), tw + 2, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        elif self._icon in ("play", "pause"):
            icons.draw_play_pause(p, r.center().x(), r.center().y(), isz, self._m, col)
        elif self._icon:
            icons.draw(p, self._icon, QRectF(r.center().x() - isz / 2, r.center().y() - isz / 2, isz, isz), col, self._fill)
        if on and not has_t and k != "primary":  # ponto indicador de "ligado" (como no Spotify)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(r.center().x(), r.bottom() - 1.5), 1.8, 1.8)

class GlassSlider(QSlider):
    def __init__(self, orientation=Qt.Horizontal, accent=False):
        super().__init__(orientation)
        self._h = 0.0
        self._accent = accent
        self.setMouseTracking(True)
        self._ha = _anim(self, self._set_h)
        self.setFixedHeight(20)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
    def _set_h(self, v):
        self._h = float(v)
        self.update()
    def enterEvent(self, e):
        _to(self._ha, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        if not self.isSliderDown():
            _to(self._ha, self._h, 0.0)
        super().leaveEvent(e)
    def _val(self, x):
        m = 7
        w = max(1, self.width() - 2 * m)
        f = min(1.0, max(0.0, (x - m) / w))
        return round(self.minimum() + f * (self.maximum() - self.minimum()))
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.isEnabled():
            return
        self.setSliderDown(True)
        self._move(e)
    def mouseMoveEvent(self, e):
        if self.isSliderDown():
            self._move(e)
    def mouseReleaseEvent(self, e):
        if self.isSliderDown():
            self._move(e)
            self.setSliderDown(False)
            if not self.underMouse():
                _to(self._ha, self._h, 0.0)
    def _move(self, e):
        v = self._val(e.position().x())
        self.setValue(v)
        self.sliderMoved.emit(v)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        m = 7
        rng = max(1, self.maximum() - self.minimum())
        f = (self.value() - self.minimum()) / rng
        w = self.width() - 2 * m
        cy = self.height() / 2
        th = 4 + 2 * self._h
        if not self.isEnabled():
            p.setOpacity(0.4)
        track = QRectF(m, cy - th / 2, w, th)
        p.setPen(Qt.NoPen)
        p.setBrush(T.ovc(0.20))
        p.drawRoundedRect(track, th / 2, th / 2)
        fillc = QColor(T.accent).lighter(115 if T.dark else 100) if (self._accent or self._h > 0.5) else QColor(T.fg)
        fr = QRectF(m, cy - th / 2, max(0.0, w * f), th)
        p.setBrush(fillc)
        p.drawRoundedRect(fr, th / 2, th / 2)
        if self._h > 0.01:
            p.setOpacity(self._h * (1 if self.isEnabled() else 0.4))
            p.setBrush(QColor(255, 255, 255) if T.dark else QColor(28, 28, 30))
            p.drawEllipse(QPointF(m + w * f, cy), 6, 6)

class Toggle(QAbstractButton):
    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self._t = 1.0 if checked else 0.0
        self._a = _anim(self, self._set, ms=180)
        self.setFixedSize(46, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.toggled.connect(lambda on: _to(self._a, self._t, 1.0 if on else 0.0))
        self.setFocusPolicy(Qt.TabFocus)
    def _set(self, v):
        self._t = float(v)
        self.update()
    def set_silent(self, on):
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._t = 1.0 if on else 0.0
        self.update()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        if not self.isEnabled():
            p.setOpacity(0.4)
        off = T.ovc(0.18)
        on = QColor(T.accent)
        t = self._t
        c = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                   int(off.blue() + (on.blue() - off.blue()) * t), int(off.alpha() + (255 - off.alpha()) * t))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.left() + 2 + (r.width() - d - 4) * t
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF(x, r.top() + 2.8, d, d))
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(x, r.top() + 2, d, d))

class Segmented(QWidget):
    changed = Signal(str)
    def __init__(self, options, current):
        super().__init__()
        self.options, self.current = list(options), current
        self._x = float(self.options.index(current) if current in self.options else 0)
        self._a = _anim(self, self._set, ms=200)
        self.setCursor(Qt.PointingHandCursor)
        fm = QFontMetrics(self.font())
        self._w = [fm.horizontalAdvance(o) + 28 for o in self.options]
        self.setFixedSize(sum(self._w) + 8, 34)
    def _set(self, v):
        self._x = float(v)
        self.update()
    def set_current(self, name):
        if name in self.options:
            self.current = name
            self._x = float(self.options.index(name))
            self.update()
    def _edges(self):
        xs = [4.0]
        for w in self._w:
            xs.append(xs[-1] + w)
        return xs
    def mousePressEvent(self, e):
        xs = self._edges()
        for i, o in enumerate(self.options):
            if xs[i] <= e.position().x() < xs[i + 1] and o != self.current:
                _to(self._a, self._x, float(i))
                self.current = o
                self.changed.emit(o)
                return
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(T.ovc(0.14), 1))
        p.setBrush(T.ovc(0.07))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        xs = self._edges()
        i = int(self._x)
        fr = self._x - i
        j = min(i + 1, len(xs) - 2)
        x0 = xs[i] + (xs[j] - xs[i]) * fr if i < len(xs) - 1 else xs[-2]
        w = self._w[i] + (self._w[j] - self._w[i]) * fr
        pill = QRectF(x0, 4, w, self.height() - 8)
        p.setPen(Qt.NoPen)
        p.setBrush(T.ovc(0.18 if T.dark else 0.12))
        p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        for k, o in enumerate(self.options):
            c = QColor(T.fg)
            if o != self.current:
                c.setAlphaF(0.62)
            p.setPen(c)
            p.drawText(QRectF(xs[k], 0, self._w[k], self.height()), Qt.AlignCenter, o)

class SearchField(QLineEdit):
    def __init__(self, placeholder=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(False)
        self.setMinimumHeight(38)
        self.addAction(icons.icon("search", T.fg.name(), 16), QLineEdit.LeadingPosition)


class NavButton(QAbstractButton):
    def __init__(self, text, icon_name):
        super().__init__()
        self.setText(text)
        self._icon = icon_name
        self.setCheckable(True)
        self._h = self._s = 0.0
        self._ha = _anim(self, self._set_h, ms=160)
        self._sa = _anim(self, self._set_s, ms=220)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    def _set_h(self, v):
        self._h = float(v)
        self.update()
    def _set_s(self, v):
        self._s = float(v)
        self.update()
    def set_active(self, on):
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
        h, s = self._h, self._s
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        a = max(0.07 * h, 0.12 * s)
        p.setPen(Qt.NoPen)
        p.setBrush(T.ovc(a if T.dark else a * 0.8))
        p.drawRoundedRect(r, 12, 12)
        if s > 0.01:  # barra de destaque
            bar = QColor(T.accent)
            bar.setAlphaF(s)
            p.setBrush(bar)
            bh = 14 + 8 * s
            p.drawRoundedRect(QRectF(r.left() + 2, r.center().y() - bh / 2, 3, bh), 1.5, 1.5)
        k = max(h, s)
        c = QColor(T.fg)
        c.setAlphaF(0.62 + 0.38 * k)
        ic = QColor(T.accent).lighter(125) if (s > 0.5 and T.dark) else (QColor(T.accent) if s > 0.5 else c)
        x = r.left() + 14 + 3 * h
        icons.draw(p, self._icon, QRectF(x, r.center().y() - 9, 18, 18), ic.name(), False, opacity=0.65 + 0.35 * k)
        f = self.font()
        f.setPixelSize(14)
        f.setWeight(f.Weight.DemiBold if s > 0.5 else f.Weight.Normal)
        p.setFont(f)
        p.setPen(c)
        p.drawText(QRectF(x + 30, r.top(), r.width() - 50, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())

class LogoButton(QAbstractButton):
    def __init__(self, path, width=58):
        super().__init__()
        self._src = QPixmap(str(path))
        self._w = width
        self._active = False
        self._h = self._p = 0.0
        self._ha = _anim(self, self._set_h, ms=220)
        self._pa = _anim(self, self._set_p, ms=90)
        self._ph = round(self._src.height() * width / max(1, self._src.width()))
        self._tint = None
        self.setFixedHeight(self._ph + 26)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setToolTip("Menu")
    def _set_h(self, v):
        self._h = float(v)
        self.update()
    def _set_p(self, v):
        self._p = float(v)
        self.update()
    def set_active(self, on):
        self._active = on
        self.update()
    def enterEvent(self, e):
        _to(self._ha, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._ha, self._h, 0.0)
        _to(self._pa, self._p, 0.0)
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        _to(self._pa, self._p, 1.0)
        super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        _to(self._pa, self._p, 0.0)
        super().mouseReleaseEvent(e)
    def _pix(self):
        dpr = self.devicePixelRatioF()
        key = (T.dark, dpr)
        if not self._tint or self._tint[0] != key:
            t = QPixmap(int(self._w * dpr), int(self._ph * dpr))
            t.setDevicePixelRatio(dpr)
            t.fill(Qt.transparent)
            q = QPainter(t)
            q.setRenderHint(QPainter.SmoothPixmapTransform)
            q.drawPixmap(QRectF(0, 0, self._w, self._ph), self._src, QRectF(self._src.rect()))
            q.setCompositionMode(QPainter.CompositionMode_SourceIn)
            q.fillRect(QRectF(0, 0, self._w, self._ph), QColor(255, 255, 255) if T.dark else QColor(0, 0, 0))
            q.end()
            self._tint = (key, t)
        return self._tint[1]
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        h = max(self._h, 1.0 if self._active else 0.0)
        cx, cy = 10 + self._w / 2, self.height() / 2
        if h > 0.01:  # brilho atrás da logo
            g = QRadialGradient(QPointF(cx, cy), self.height() / 2)
            c = QColor(T.accent)
            c.setAlphaF(0.38 * h)
            e = QColor(T.accent)
            e.setAlphaF(0)
            g.setColorAt(0, c)
            g.setColorAt(1, e)
            p.fillRect(self.rect(), g)
        p.translate(cx, cy)
        p.rotate(-5 * self._h)
        sc = (1 + 0.12 * self._h) * (1 - 0.07 * self._p)
        p.scale(sc, sc)
        p.drawPixmap(QPointF(-self._w / 2, -self._ph / 2), self._pix())
        if not self.isEnabled():
            return
        p.resetTransform()  # setinha "abre menu"
        icons.draw(p, "chevron-down", QRectF(self.width() - 30, cy - 8 + 2 * self._h, 16, 16), T.fg.name(), False, opacity=0.35 + 0.5 * h)

class MenuItem(QAbstractButton):
    def __init__(self, key, icon_name, title, desc):
        super().__init__()
        self.key, self._icon, self._title, self._desc = key, icon_name, title, desc
        self._h = self._p = 0.0
        self._ha = _anim(self, self._set_h, ms=160)
        self._pa = _anim(self, self._set_p, ms=90)
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
    def _set_h(self, v):
        self._h = float(v)
        self.update()
    def _set_p(self, v):
        self._p = float(v)
        self.update()
    def enterEvent(self, e):
        _to(self._ha, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._ha, self._h, 0.0)
        _to(self._pa, self._p, 0.0)
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        _to(self._pa, self._p, 1.0)
        super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        _to(self._pa, self._p, 0.0)
        super().mouseReleaseEvent(e)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self._h
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        sc = 1 - 0.02 * self._p
        r = QRectF(r.center().x() - r.width() * sc / 2, r.center().y() - r.height() * sc / 2, r.width() * sc, r.height() * sc)
        p.setPen(Qt.NoPen)
        p.setBrush(T.ovc(0.09 * h))
        p.drawRoundedRect(r, 14, 14)
        tile = QRectF(r.left() + 8, r.center().y() - 19, 38, 38)
        a = QColor(T.accent)
        g = QLinearGradient(tile.topLeft(), tile.bottomRight())
        c1 = QColor(a)
        c1.setAlphaF(0.20 + 0.45 * h)
        c2 = QColor(a)
        c2.setAlphaF(0.08 + 0.25 * h)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setBrush(g)
        p.drawRoundedRect(tile, 11, 11)
        isz = 20 * (1 + 0.10 * h)
        ic = a.lighter(135) if T.dark else a.darker(115)
        icons.draw(p, self._icon, QRectF(tile.center().x() - isz / 2, tile.center().y() - isz / 2, isz, isz), ic.name())
        f = self.font()
        f.setPixelSize(14)
        f.setWeight(f.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(T.fg))
        tx = tile.right() + 12
        p.drawText(QRectF(tx, r.top() + 9, r.width() - 80, 20), Qt.AlignVCenter | Qt.AlignLeft, self._title)
        f.setPixelSize(11)
        f.setWeight(f.Weight.Normal)
        p.setFont(f)
        m = QColor(T.fg)
        m.setAlphaF(0.58)
        p.setPen(m)
        p.drawText(QRectF(tx, r.top() + 29, r.width() - 80, 18), Qt.AlignVCenter | Qt.AlignLeft, self._desc)
        icons.draw(p, "chevron-right", QRectF(r.right() - 28 + 5 * h, r.center().y() - 8, 16, 16), T.fg.name(), False, opacity=h * 0.8)

class PopupMenu(QWidget):
    chosen = Signal(str)
    PAD = 14
    def __init__(self, parent, entries, width=290):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.closed_at = 0.0
        self._anim = None
        self._base = QPoint()
        v = QVBoxLayout(self)
        v.setContentsMargins(self.PAD + 8, self.PAD + 8, self.PAD + 8, self.PAD + 8)
        v.setSpacing(2)
        self.items = []
        for e in entries:
            if e is None:
                d = QFrame()
                d.setFixedHeight(9)
                d.setStyleSheet("background:transparent;")
                v.addWidget(d)
                continue
            it = MenuItem(*e)
            it.clicked.connect(lambda _=False, k=e[0]: (self.close(), self.chosen.emit(k)))
            v.addWidget(it)
            self.items.append(it)
        self.setFixedWidth(width + 2 * self.PAD)
        self.adjustSize()
    def paintEvent(self, _):
        p = QPainter(self)
        pad = self.PAD
        paint_sheet(p, QRectF(self.rect()).adjusted(pad, pad, -pad, -pad), 22)
    def popup_below(self, w):
        g = w.mapToGlobal(QPoint(0, w.height()))
        self._base = QPoint(g.x() - self.PAD + 4, g.y() - self.PAD - 6)
        if T.reduce:
            self.move(self._base)
            self.show()
            return
        self.setWindowOpacity(0.0)
        self.move(self._base + QPoint(0, -8))
        self.show()
        a = self._anim = QVariantAnimation(self)
        a.setDuration(180)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(lambda t: (self.setWindowOpacity(float(t)), self.move(self._base + QPoint(0, int(-8 * (1 - float(t)))))))
        a.start()
    def hideEvent(self, e):
        self.closed_at = time.monotonic()
        super().hideEvent(e)


class ColorButton(QAbstractButton):
    def __init__(self, color="#8b7cf6"):
        super().__init__()
        self.color = QColor(color)
        self._h = 0.0
        self._a = _anim(self, self._set, ms=140)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(122, 34)
        self.setFocusPolicy(Qt.TabFocus)
    def _set(self, v):
        self._h = float(v)
        self.update()
    def set_color(self, c):
        self.color = QColor(c)
        self.update()
    def enterEvent(self, e):
        _to(self._a, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._a, self._h, 0.0)
        super().leaveEvent(e)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(T.ovc(0.14 + 0.14 * self._h), 1))
        p.setBrush(T.ovc(0.07 + 0.05 * self._h))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        rad = 9 + 1.5 * self._h
        c = QPointF(r.left() + 18, r.center().y())
        p.setPen(QPen(T.ovc(0.35), 1))
        p.setBrush(self.color)
        p.drawEllipse(c, rad, rad)
        p.setPen(T.fg)
        f = self.font()
        f.setPixelSize(13)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 36, r.top(), r.width() - 40, r.height()), Qt.AlignVCenter, self.color.name().upper())


class PlayFab(QAbstractButton):
    PAD = 7
    def __init__(self, diameter=56, tooltip="Play"):
        super().__init__()
        self._d = diameter
        self._h = self._p = self._m = self._r = 0.0
        self._playing = False
        self._tip = tooltip
        self._ha = _anim(self, self._set_h, ms=180)
        self._pa = _anim(self, self._set_p, ms=90)
        self._ma = _anim(self, self._set_m, ms=300)
        self._ma.setEasingCurve(QEasingCurve.OutBack)
        self._ra = _anim(self, self._set_r, ms=520)
        self.setFixedSize(diameter + 2 * self.PAD, diameter + 2 * self.PAD)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setToolTip(tooltip)
        self.truth = None  # função que diz o estado real; confere depois do clique
        self._rt = QTimer(self)
        self._rt.setSingleShot(True)
        self._rt.timeout.connect(self._resync)
        self.clicked.connect(self._optimistic)
    def _optimistic(self):
        # vira play/pause na hora; o estado real chega depois e confirma
        self.set_playing(not self._playing)
        self._rt.start(700)
    def _resync(self):
        if self.truth:
            self.set_playing(self.truth())
    def _set_h(self, v):
        self._h = float(v)
        self.update()
    def _set_p(self, v):
        self._p = float(v)
        self.update()
    def _set_m(self, v):
        self._m = float(v)
        self.update()
    def _set_r(self, v):
        self._r = float(v)
        self.update()
    @property
    def playing(self):
        return self._playing
    def set_playing(self, on, animate=True):
        on = bool(on)
        if on == self._playing:
            return
        self._playing = on
        self.setToolTip("Pause" if on else self._tip)
        if animate and not T.reduce:
            _to(self._ma, self._m, 1.0 if on else 0.0)
        else:
            self._ma.stop()
            self._m = 1.0 if on else 0.0
            self.update()
    def enterEvent(self, e):
        _to(self._ha, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._ha, self._h, 0.0)
        _to(self._pa, self._p, 0.0)
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            _to(self._pa, self._p, 1.0)
        super().mousePressEvent(e)
    def mouseReleaseEvent(self, e):
        _to(self._pa, self._p, 0.0)
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()) and not T.reduce:
            self._ra.stop()
            self._ra.setStartValue(0.0)
            self._ra.setEndValue(1.0)
            self._ra.start()
        super().mouseReleaseEvent(e)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if not self.isEnabled():
            p.setOpacity(0.35)
        sc = 1 + 0.07 * self._h - 0.10 * self._p
        rad = self._d / 2 * sc
        if 0.0 < self._r < 1.0:  # anel do clique
            ring = QColor(T.accent)
            ring.setAlphaF(0.55 * (1 - self._r))
            p.setPen(QPen(ring, 2))
            p.setBrush(Qt.NoBrush)
            rr = self._d / 2 + self.PAD * self._r
            p.drawEllipse(c, rr, rr)
        if self._h > 0.01:  # brilho no hover
            g = QRadialGradient(c, rad + 8)
            a = QColor(T.accent)
            a.setAlphaF(0.35 * self._h)
            b = QColor(T.accent)
            b.setAlphaF(0)
            g.setColorAt(0.7, a)
            g.setColorAt(1, b)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, rad + 8, rad + 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.accent).lighter(100 + int(10 * self._h)))
        p.drawEllipse(c, rad, rad)
        icons.draw_play_pause(p, c.x(), c.y(), self._d * 0.40 * sc, self._m)


class _ComboDelegate(QStyledItemDelegate):
    def sizeHint(self, o, i):
        return QSize(100, 36)
    def paint(self, p, o, idx):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(o.rect).adjusted(2, 1, -2, -1)
        on = bool(o.state & (QStyle.State_Selected | QStyle.State_MouseOver))
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.accent.red(), T.accent.green(), T.accent.blue(), 95))
            p.drawRoundedRect(r, 10, 10)
        f = p.font()
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(T.fg)
        p.drawText(QRectF(r.left() + 12, r.top(), r.width() - 20, r.height()), Qt.AlignVCenter, idx.data(Qt.DisplayRole) or "")
        p.restore()

class GlassCombo(QComboBox):
    """lista suspensa de vidro, sem a moldura do sistema"""
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QListView()
        self.setView(v)
        v.setMouseTracking(True)
        v.setItemDelegate(_ComboDelegate())
        v.setSpacing(0)
        pop = v.window()
        pop.setObjectName("comboPop")
        pop.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        pop.setAttribute(Qt.WA_TranslucentBackground)
        pop.setStyleSheet("#comboPop{background:transparent;border:none;}")
