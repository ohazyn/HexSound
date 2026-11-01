from itertools import zip_longest
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QTimer, QEasingCurve
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QLinearGradient, QColor, QFontMetrics, QFont
from hexsound.ui import icons
from hexsound.ui.style import T
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QSizePolicy, QLayout, QGridLayout
from hexsound.ui.nowstate import now
from hexsound.ui.widgets import Segmented, _anim, _to

from collections import OrderedDict
from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader

_cache = OrderedDict()
_CACHE_MAX = 600

def load_cover(path, size):
    key = (path, size)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    pm = None
    if path:
        rd = QImageReader(str(path))
        rd.setAutoTransform(True)
        sz = rd.size()
        if sz.isValid() and min(sz.width(), sz.height()) > size:  # decodifica já pequeno: bem mais rápido
            rd.setScaledSize(sz.scaled(QSize(size, size), Qt.KeepAspectRatioByExpanding))
        img = rd.read()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
            if pm.width() != size or pm.height() != size:
                pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                pm = pm.copy((pm.width() - size) // 2, (pm.height() - size) // 2, size, size)
    _cache[key] = pm
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return pm

class CoverLabel(QLabel):
    clicked = Signal()
    def __init__(self, size, radius=16):
        super().__init__()
        self.s, self.r, self._pm = size, radius, None
        self.setFixedSize(size, size)
    def set_cover(self, path):
        self._pm = load_cover(path, self.s)
        self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), self.r, self.r)
        p.setClipPath(clip)
        if self._pm:
            p.drawPixmap(0, 0, self._pm)
            return
        g = QLinearGradient(0, 0, self.s, self.s)
        g.setColorAt(0, T.ovc(0.16))
        g.setColorAt(1, T.ovc(0.05))
        p.fillRect(self.rect(), g)
        k = self.s * 0.38
        icons.draw(p, "music", QRectF((self.s - k) / 2, (self.s - k) / 2, k, k), T.fg.name(), opacity=0.45)

class HoverCover(CoverLabel):
    def __init__(self, size, radius=16):
        super().__init__(size, radius)
        self._h = 0.0
        self._a = _anim(self, self._set)
        self.ctx = None
        self.track_id = None
        self._m, self._mt = 0.0, 0.0  # play <-> pause (valor atual e alvo)
        self._ma = _anim(self, self._set_m, ms=300)
        self._ma.setEasingCurve(QEasingCurve.OutBack)
        self._rt = QTimer(self)
        self._rt.setSingleShot(True)
        self._rt.timeout.connect(self.sync_icon)
        now.changed.connect(self.sync_icon)
        now.changed.connect(self.update)
    def _set(self, v):
        self._h = float(v)
        self.update()
    def _set_m(self, v):
        self._m = float(v)
        self.update()
    def morph_to(self, target):
        if target == self._mt:
            return
        self._mt = target
        if T.reduce:
            self._ma.stop()
            self._m = target
            self.update()
        else:
            _to(self._ma, self._m, target)
    def sync_icon(self):
        self.morph_to(1.0 if self.live() else 0.0)
    def showEvent(self, e):
        self._ma.stop()
        self._mt = self._m = 1.0 if self.live() else 0.0  # ao aparecer já nasce no estado certo, sem animar
        super().showEvent(e)
    def pressed_play(self):
        self.morph_to(0.0 if self._mt else 1.0)  # vira na hora; o estado real confirma
        self._rt.start(700)
    def live(self):
        """true se o que esse cartão representa é o que está tocando (o botão vira pause)"""
        if not now.playing:
            return False
        return now.ctx_playing(self.ctx) or (self.track_id is not None and self.track_id == now.track_id)
    def hover(self, on):
        _to(self._a, self._h, 1.0 if on else 0.0)
    def play_rect(self):
        d = 38
        return QRectF(self.s - d - 10, self.s - d - 10, d, d)
    def mousePressEvent(self, e):
        e.ignore()  # o clique na capa (onde fica o botão play) sobe para o Card; antes era engolido aqui
    def paintEvent(self, e):
        super().paintEvent(e)
        live = self.live()
        if self._h < 0.01 and not live:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = 1.0 if live else self._h
        c = QPainterPath()
        c.addRoundedRect(QRectF(self.rect()), self.r, self.r)
        p.fillPath(c, QColor(0, 0, 0, int(70 * h)))
        d = 38
        x = self.s - d - 10
        y = self.s - d - 10 + 8 * (1 - h)
        p.setOpacity(h)
        p.setPen(Qt.NoPen)
        p.setBrush(T.accent)
        p.drawEllipse(QRectF(x, y, d, d))
        icons.draw_play_pause(p, x + d / 2, y + d / 2, 16, self._m)

class Card(QWidget):
    """cartão de capa. on_click abre/toca; se tiver on_play, só o botão redondo da capa toca"""
    def __init__(self, title, sub, cover, on_click, size=150, ctx=None, track_id=None, on_play=None):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.on_click, self.on_play = on_click, on_play
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        self.cover = HoverCover(size, 16)
        self.cover.ctx = ctx
        self.cover.track_id = track_id
        self.cover.set_cover(cover)
        lay.addWidget(self.cover)
        lay.addSpacing(6)
        for text, name in ((title, "trackTitle"), (sub, "muted")):
            l = QLabel()
            l.setObjectName(name)
            l.setToolTip(text or "")
            l.setText(QFontMetrics(l.font()).elidedText(text or " ", Qt.ElideRight, size))
            l.setFixedWidth(size)
            lay.addWidget(l)
    def enterEvent(self, e):
        self.cover.hover(True)
        super().enterEvent(e)
    def leaveEvent(self, e):
        self.cover.hover(False)
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.on_play:
            pos = e.position() - QPointF(self.cover.pos())
            if self.cover.play_rect().contains(pos):
                self.cover.pressed_play()
                self.on_play()
                return
        self.on_click()

class QuickTile(QWidget):
    """atalho da grade do topo: capa quadrada + título; no hover aparece o botão play"""
    H = 56
    def __init__(self, title, cover, ctx, on_open, on_play, liked=False):
        super().__init__()
        self.title, self.ctx, self.liked = title, ctx, liked
        self.on_open, self.on_play = on_open, on_play
        self._pm = load_cover(cover, self.H)
        self._h = 0.0
        self._m, self._mt = 0.0, 0.0
        self._a = _anim(self, self._set, ms=150)
        self._ma = _anim(self, self._set_m, ms=300)
        self._ma.setEasingCurve(QEasingCurve.OutBack)
        self._rt = QTimer(self)
        self._rt.setSingleShot(True)
        self._rt.timeout.connect(self.sync_icon)
        self.setFixedHeight(self.H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(title)
        now.changed.connect(self.sync_icon)
        now.changed.connect(self.update)
    def _set(self, v):
        self._h = float(v)
        self.update()
    def _set_m(self, v):
        self._m = float(v)
        self.update()
    def morph_to(self, target):
        if target == self._mt:
            return
        self._mt = target
        if T.reduce:
            self._ma.stop()
            self._m = target
            self.update()
        else:
            _to(self._ma, self._m, target)
    def sync_icon(self):
        self.morph_to(1.0 if self.live() else 0.0)
    def showEvent(self, e):
        self._ma.stop()
        self._mt = self._m = 1.0 if self.live() else 0.0  # ao aparecer já nasce no estado certo, sem animar
        super().showEvent(e)
    def live(self):
        return now.ctx_playing(self.ctx)
    def play_rect(self):
        d = 34
        return QRectF(self.width() - d - 12, (self.H - d) / 2, d, d)
    def enterEvent(self, e):
        _to(self._a, self._h, 1.0)
        super().enterEvent(e)
    def leaveEvent(self, e):
        _to(self._a, self._h, 0.0)
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if (self._h > 0.5 or self.live()) and self.play_rect().contains(e.position()):
            self.morph_to(0.0 if self._mt else 1.0)  # vira na hora; o estado real confirma
            self._rt.start(700)
            self.on_play()
        else:
            self.on_open()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        plate = QPainterPath()
        plate.addRoundedRect(r, 10, 10)
        p.fillPath(plate, T.ovc(0.07 + 0.06 * self._h))
        p.save()
        p.setClipPath(plate)
        box = QRectF(0, 0, self.H, self.H)
        if self.liked:
            g = QLinearGradient(0, 0, self.H, self.H)
            g.setColorAt(0, T.accent.lighter(135))
            g.setColorAt(1, T.accent.darker(150))
            p.fillRect(box, g)
            icons.draw(p, "heart", QRectF(self.H / 2 - 11, self.H / 2 - 11, 22, 22), "#ffffff", True)
        elif self._pm:
            p.drawPixmap(0, 0, self._pm)
        else:
            p.fillRect(box, T.ovc(0.10))
            icons.draw(p, "music", QRectF(self.H / 2 - 11, self.H / 2 - 11, 22, 22), T.fg.name(), opacity=0.45)
        p.restore()
        live = self.live()
        show = 1.0 if live else self._h
        f = p.font()
        f.setPixelSize(13)
        f.setWeight(f.Weight.DemiBold)
        p.setFont(f)
        p.setPen(T.fg)
        right = self.width() - 14 - (46 if show > 0.01 else 0)
        txt = QFontMetrics(f).elidedText(self.title, Qt.ElideRight, int(right - self.H - 14))
        p.drawText(QRectF(self.H + 14, 0, right - self.H - 14, self.H), Qt.AlignVCenter | Qt.AlignLeft, txt)
        if show > 0.01:
            b = self.play_rect()
            p.setOpacity(show)
            p.setPen(Qt.NoPen)
            p.setBrush(T.accent)
            p.drawEllipse(b.translated(0, 6 * (1 - show)))
            icons.draw_play_pause(p, b.center().x(), b.center().y() + 6 * (1 - show), 16, self._m)

class LinkLabel(QLabel):
    clicked = Signal()
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("muted")
        self.setCursor(Qt.PointingHandCursor)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

CARD = 150
GAP = 18

class HomePage(QWidget):
    FILTERS = ["All", "Playlists", "Albums", "Liked"]
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.filter = "All"
        self._cols, self._per_row = 4, 5
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        self.chips = Segmented(self.FILTERS, "All")
        self.chips.changed.connect(self._set_filter)
        top = QHBoxLayout()
        top.addWidget(self.chips)
        top.addStretch()
        outer.addLayout(top)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.vl = QVBoxLayout(self.body)
        self.vl.setContentsMargins(0, 6, 10, 10)
        self.vl.setSpacing(8)
        sc.setWidget(self.body)
        outer.addWidget(sc)

    def _set_filter(self, name):
        self.filter = name
        self.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.width() - 10
        cols = 4 if w >= 860 else 3 if w >= 640 else 2
        per_row = max(1, (w + GAP) // (CARD + GAP))
        if (cols, per_row) != (self._cols, self._per_row):
            self._cols, self._per_row = cols, per_row
            self.refresh()

    # abrir páginas
    def open_playlist(self, pid):
        self.win.go_page("Playlists")
        self.win.page["Playlists"].open(pid)
    def open_album(self, name):
        self.win.go_page("Albums")
        self.win.page["Albums"].open(name)
    def open_liked(self):
        self.win.page["Library"].chips.set_current("Favorites")
        self.win.go_page("Library")

    # tocar
    def play_playlist(self, pid):
        self.win.toggle_context(("playlist", pid), self.win.lib.playlist_tracks(pid))
    def play_album(self, name):
        self.win.toggle_context(("album", name), self.win.lib.tracks_by("album", name))
    def play_liked(self):
        self.win.toggle_context(("liked",), self.win.lib.tracks(favorites=True))

    def header(self, title, on_all):
        row = QHBoxLayout()
        row.addWidget(QLabel(title, objectName="h2"))
        row.addStretch()
        link = LinkLabel("Show all")
        link.clicked.connect(on_all)
        row.addWidget(link)
        self.vl.addLayout(row)

    def cards_grid(self, cards, empty):
        if not cards:
            self.vl.addWidget(QLabel(empty, objectName="muted"))
            self.vl.addSpacing(14)
            return
        g = QGridLayout()
        g.setHorizontalSpacing(GAP)
        g.setVerticalSpacing(14)
        g.setContentsMargins(0, 4, 0, 0)
        n = self._per_row
        for i, c in enumerate(cards):
            g.addWidget(c, i // n, i % n, Qt.AlignLeft | Qt.AlignTop)
        g.setColumnStretch(n, 1)
        self.vl.addLayout(g)
        self.vl.addSpacing(14)

    def track_cards(self, rows):
        return [Card(t["title"], t["artist"], t["cover"], lambda i=i: self.win.play_row(rows, i), CARD, track_id=t["id"])
                for i, t in enumerate(rows)]

    def refresh(self):
        while self.vl.count():
            it = self.vl.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()  # esconde já: evita um quadro com seções antigas sobrepostas
            elif it.layout():
                self._drop(it.layout())
        lib, f = self.win.lib, self.filter
        playlists = []
        for p in lib.playlists():
            tr = lib.playlist_tracks(p["id"])
            cover = p["cover"] or next((t["cover"] for t in tr if t["cover"]), None)
            playlists.append((p["id"], p["name"], len(tr), cover))
        covers = lib.group_covers("album")
        albums = [(g["name"], g["n"], covers.get(g["name"])) for g in lib.groups("album")]
        liked = lib.tracks(favorites=True)
        limit = None if f != "All" else self._per_row   # em "All" cada seção mostra só o que cabe numa linha

        if f == "All":
            self.vl.addLayout(self.quick_grid(playlists, albums))
            self.vl.addSpacing(10)
        if f in ("All", "Playlists"):
            self.header("Your Playlists", lambda: self.win.go_page("Playlists"))
            cards = [Card(name, f"{n} track{'s' if n != 1 else ''}", cover, lambda pid=pid: self.open_playlist(pid), CARD,
                          ctx=("playlist", pid), on_play=lambda pid=pid: self.play_playlist(pid))
                     for pid, name, n, cover in playlists[:limit]]
            self.cards_grid(cards, "Create a playlist in the Playlists page.")
        if f in ("All", "Albums"):
            self.header("Albums", lambda: self.win.go_page("Albums"))
            cards = [Card(name, f"{n} track{'s' if n != 1 else ''}", cover, lambda name=name: self.open_album(name), CARD,
                          ctx=("album", name), on_play=lambda name=name: self.play_album(name))
                     for name, n, cover in albums[:limit]]
            self.cards_grid(cards, "Import some music to see your albums.")
        if f in ("All", "Liked"):
            self.header("Liked Songs", self.open_liked)
            self.cards_grid(self.track_cards(liked[:limit]), "Use the heart on a song to add it here.")
        self.vl.addStretch()

    def _drop(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
            elif it.layout():
                self._drop(it.layout())

    def quick_grid(self, playlists, albums):
        """Liked Songs primeiro, depois playlists e álbuns alternados, em 2 linhas"""
        items = [("liked", None)]
        for pl, al in zip_longest(playlists, albums):
            if pl:
                items.append(("playlist", pl))
            if al:
                items.append(("album", al))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(12)
        g.setContentsMargins(0, 4, 0, 0)
        for i, (kind, d) in enumerate(items[:self._cols * 2]):
            if kind == "liked":
                t = QuickTile("Liked Songs", None, ("liked",), self.open_liked, self.play_liked, liked=True)
            elif kind == "playlist":
                pid, name, _n, cover = d
                t = QuickTile(name, cover, ("playlist", pid), lambda pid=pid: self.open_playlist(pid), lambda pid=pid: self.play_playlist(pid))
            else:
                name, _n, cover = d
                t = QuickTile(name, cover, ("album", name), lambda name=name: self.open_album(name), lambda name=name: self.play_album(name))
            g.addWidget(t, i // self._cols, i % self._cols)
        for c in range(self._cols):
            g.setColumnStretch(c, 1)
        return g
