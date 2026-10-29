import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Qt, QRectF
from PySide6.QtGui import QColor, QImage, QImageReader, QMovie, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

MAX_STILL, MAX_FRAME = 1600, 640

def _limit(pm, side):
    return pm if max(pm.width(), pm.height()) <= side else pm.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)

def blur_quality(pm, radius):
    if radius <= 0:
        return pm
    pm = _limit(pm, 960)
    scene = QGraphicsScene()
    it = QGraphicsPixmapItem(pm)
    ef = QGraphicsBlurEffect()
    ef.setBlurRadius(radius)
    ef.setBlurHints(QGraphicsBlurEffect.QualityHint)
    it.setGraphicsEffect(ef)
    scene.addItem(it)
    pad = int(radius * 2)
    img = QImage(pm.width() + 2 * pad, pm.height() + 2 * pad, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    scene.render(p, QRectF(img.rect()), QRectF(-pad, -pad, img.width(), img.height()))
    p.end()
    return QPixmap.fromImage(img.copy(pad, pad, pm.width(), pm.height()))

def blur_fast(pm, amount):
    """desfoque rápido pros quadros de GIF"""
    pm = _limit(pm, MAX_FRAME)
    if amount <= 0:
        return pm
    f = 1 + amount * 0.30
    w, h = max(48, int(pm.width() / f)), max(48, int(pm.height() / f))
    return pm.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

ANIMATED_EXT = {".gif", ".webp", ".apng"}

class Background(QObject):
    changed = Signal()
    def __init__(self):
        super().__init__()
        self.mode, self.color, self.path, self.blur, self.dim = "auto", QColor("#1b1630"), "", 18, 35
        self.movie, self.base, self.shown, self.paused, self.animated = None, None, None, False, False
        self.animate, self.note, self.frames, self._last = True, "", 0, 0.0
    @property
    def has_image(self):
        return self.mode == "image" and self.shown is not None
    def configure(self, mode=None, color=None, path=None, blur=None, dim=None, animate=None):
        old = (self.mode, self.path, self.blur)
        if mode is not None:
            self.mode = mode
        if color is not None:
            self.color = QColor(color)
        if path is not None:
            self.path = path
        if blur is not None:
            self.blur = int(blur)
        if dim is not None:
            self.dim = int(dim)
        if animate is not None:
            self.animate = bool(animate)
            self._sync()
        if (self.mode, self.path) != old[:2]:
            self._load()
        elif self.blur != old[2]:
            if self.movie is not None:
                self._frame(force=True)
            else:
                self._rebuild()
        self.changed.emit()
    def set_paused(self, on):
        self.paused = bool(on)
        self._sync()
    def _sync(self):
        mv = self.movie
        if mv is None:
            return
        run, st = self.animate and not self.paused, mv.state()
        if run and st == QMovie.NotRunning:
            mv.start()
        elif run and st == QMovie.Paused:
            mv.setPaused(False)
        elif not run and st == QMovie.Running:
            mv.setPaused(True)
    def _stop(self):
        if self.movie:
            self.movie.stop()
            self.movie.frameChanged.disconnect()
            self.movie.finished.disconnect()
            self.movie.deleteLater()
        self.movie, self.base, self.shown, self.animated, self.frames = None, None, None, False, 0
    def _load(self):
        self._stop()
        self.note = ""
        if self.mode != "image" or not self.path:
            return
        if not Path(self.path).is_file():
            self.note = "File not found"
            return
        rd = QImageReader(self.path)
        rd.setAutoTransform(True)
        n = rd.imageCount()
        anim = rd.supportsAnimation() and n != 1  # n == 0: o formato não sabe contar, mas anima
        if anim:
            mv = QMovie(self.path)
            if mv.isValid():
                sz = rd.size()
                if sz.isValid() and max(sz.width(), sz.height()) > MAX_FRAME:  # decodifica já em tamanho reduzido: GIFs grandes ficam leves
                    mv.setScaledSize(sz.scaled(MAX_FRAME, MAX_FRAME, Qt.KeepAspectRatio))
                mv.setCacheMode(QMovie.CacheNone)
                mv.frameChanged.connect(self._frame)
                mv.finished.connect(self._again)
                self.movie, self.animated, self.frames = mv, True, max(n, 0)
                mv.jumpToFrame(0)
                self._frame(force=True)
                self.note = f"Animated · {n} frames" if n > 1 else "Animated"
                if self.shown is None:
                    self._stop()
                    anim = False
                else:
                    self._sync()
                    return
        pm = QPixmap(self.path)
        if pm.isNull():
            self.note = "Could not read this image"
            return
        self.base = _limit(pm, MAX_STILL)
        self._rebuild()
        self.note = "Still image" if Path(self.path).suffix.lower() not in ANIMATED_EXT else "Still image (this file has one frame)"
    def _again(self):
        """GIF sem loop recomeça"""
        if self.movie is not None and self.animate and not self.paused:
            self.movie.start()
    def _rebuild(self):
        if self.base is not None:
            self.shown = blur_quality(self.base, self.blur * 1.5)
    def _frame(self, *_, force=False):
        if self.movie is None:
            return
        now = time.monotonic()
        if not force and now - self._last < 0.033:
            return  # no máximo ~30 quadros/s: poupa CPU e a interface não engasga
        pm = self.movie.currentPixmap()
        if pm.isNull():
            return
        self._last = now
        self.shown = blur_fast(pm, self.blur)
        self.changed.emit()

bg = Background()
