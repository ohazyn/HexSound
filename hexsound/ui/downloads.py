import math
from PySide6.QtCore import Qt, QRectF, Signal, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFontMetrics, QFont, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel
from hexsound.ui import icons
from hexsound.ui.home import load_cover
from hexsound.ui.style import T
from hexsound.ui.widgets import _anim

LABEL = {"queued": "Waiting", "searching": "Finding audio…", "downloading": "Downloading", "converting": "Converting to MP3…",
         "done": "Added to library", "skipped": "Already in library", "failed": "Failed", "cancelled": "Cancelled"}
FINAL = {"done", "skipped", "failed", "cancelled"}
RED = QColor("#ff453a")

def _muted():
    c = QColor(T.fg)
    c.setAlphaF(0.62)
    return c


class DownloadRow(QWidget):
    play = Signal(int)  # track_id
    retry = Signal(int)  # idx da linha
    H = 58

    def __init__(self, entry):
        super().__init__()
        self.idx = entry["idx"]
        self.title, self.artist = entry["title"], entry.get("artist", "")
        self.state, self.pct, self.msg, self.track_id, self.cover = "queued", 0.0, "", None, None
        self._shown = 0.0
        self._h = 0.0
        self._rh = False
        self._a = _anim(self, self._set_shown, ms=180)
        self._ha = _anim(self, self._set_h, ms=140)
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)
        self.setToolTip(self.title)
        # animações: entrada (desliza+aparece), brilho "carregando", pulso ao concluir, tremida ao falhar
        self._in, self._sh, self._pulse, self._shake = 1.0, 0.0, 1.0, 1.0
        self._ain = self._mk(lambda v: self._set("_in", v), 380, QEasingCurve.OutCubic)
        self._ash = self._mk(lambda v: self._set("_sh", v), 1150, QEasingCurve.Linear)
        self._ash.setLoopCount(-1)
        self._apulse = self._mk(lambda v: self._set("_pulse", v), 750, QEasingCurve.OutCubic)
        self._ashake = self._mk(lambda v: self._set("_shake", v), 460, QEasingCurve.Linear)
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.timeout.connect(self._ain.start)

    def _mk(self, setter, ms, curve):
        a = QVariantAnimation(self)
        a.setDuration(ms)
        a.setEasingCurve(curve)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(setter)
        return a

    def _set(self, name, v):
        setattr(self, name, float(v))
        self.update()

    def enter(self, delay=0):
        if T.reduce:
            return
        self._in = 0.0
        self.update()
        self._delay.start(max(1, int(delay)))

    def collapse(self, done):
        if T.reduce:
            done()
            return
        self._ash.stop()
        a = self._mk(lambda v: (self._set("_in", 1 - float(v)), self.setFixedHeight(max(0, int(self.H * (1 - float(v)))))), 240, QEasingCurve.InCubic)
        a.finished.connect(done)
        a.start()
        self._acol = a

    def _set_shown(self, v):
        self._shown = float(v)
        self.update()
    def _set_h(self, v):
        self._h = float(v)
        self.update()

    def set_state(self, state, pct=0.0, msg=""):
        prev = self.state
        self.state, self.msg = state, msg
        if not T.reduce:
            if state in ("searching", "converting"):
                if self._ash.state() != QVariantAnimation.Running:
                    self._ash.start()
            else:
                self._ash.stop()
            if state != prev and state == "done":
                self._apulse.stop()
                self._apulse.start()
            if state != prev and state == "failed":
                self._ashake.stop()
                self._ashake.start()
        if state == "done":
            pct = 100.0
        self.pct = pct
        self.setToolTip(f"{self.title}\n{msg}" if msg else self.title)
        if T.reduce:
            self._shown = pct
            self.update()
        else:
            self._a.stop()
            self._a.setStartValue(self._shown)
            self._a.setEndValue(pct)
            self._a.start()
        self.setCursor(Qt.PointingHandCursor if self.playable else Qt.ArrowCursor)
        self.update()

    def set_done(self, track_id, cover):
        self.track_id, self.cover = track_id, cover
        self.set_state("done")
        self.setCursor(Qt.PointingHandCursor)

    @property
    def playable(self):
        return self.state in ("done", "skipped") and self.track_id is not None

    @property
    def retryable(self):
        return self.state in ("failed", "cancelled")

    def _pill(self):
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        return QRectF(r.right() - 12 - 82, r.center().y() - 14, 82, 28)

    def mouseMoveEvent(self, e):
        over = self.retryable and self._pill().contains(e.position())
        if over != self._rh:
            self._rh = over
            self.setCursor(Qt.PointingHandCursor if over or self.playable else Qt.ArrowCursor)
            self.update()
        super().mouseMoveEvent(e)

    def enterEvent(self, e):
        self._ha.stop()
        self._ha.setStartValue(self._h)
        self._ha.setEndValue(1.0 if self.playable else 0.0)
        self._ha.start()
    def leaveEvent(self, e):
        self._rh = False
        self._ha.stop()
        self._ha.setStartValue(self._h)
        self._ha.setEndValue(0.0)
        self._ha.start()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.retryable and self._pill().contains(e.position()):
            self.retry.emit(self.idx)
        elif e.button() == Qt.LeftButton and self.playable:
            self.play.emit(self.track_id)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        p.setOpacity(max(0.0, min(1.0, self._in)))
        dx = -(1 - self._in) * 22 + (7 * (1 - self._shake) * math.sin(self._shake * 6 * math.pi) if self._shake < 1 else 0)
        p.translate(dx, 0)
        bg = T.ovc(0.05 + 0.05 * self._h)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 12, 12)
        if self._pulse < 1:  # clarão de sucesso
            a = QColor(T.accent)
            a.setAlphaF(0.28 * (1 - self._pulse))
            p.setBrush(a)
            p.drawRoundedRect(r, 12, 12)
        if self._shake < 1:  # clarão vermelho curto ao falhar
            a = QColor(RED)
            a.setAlphaF(0.20 * (1 - self._shake))
            p.setBrush(a)
            p.drawRoundedRect(r, 12, 12)
        # capa
        cr = QRectF(r.left() + 8, r.top() + 7, 40, 40)
        clip = QPainterPath()
        clip.addRoundedRect(cr, 9, 9)
        p.save()
        p.setClipPath(clip)
        pm = load_cover(self.cover, 40) if self.cover else None
        if pm:
            p.drawPixmap(cr.toRect(), pm)
        else:
            p.fillRect(cr, T.ovc(0.10))
            icons.draw(p, "music", cr.adjusted(10, 10, -10, -10), T.fg.name(), opacity=0.5)
        if self._h > 0.01 and self.playable:
            p.fillRect(cr, QColor(0, 0, 0, int(110 * self._h)))
            icons.draw(p, "play", cr.adjusted(11, 11, -11, -11), "#ffffff", fill=True, opacity=self._h)
        p.restore()
        # texto
        right = 250 if not self.retryable else 360
        tx = cr.right() + 12
        w = r.right() - tx - right - 10
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(T.fg)
        p.drawText(QRectF(tx, r.top() + 8, w, 18), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(f).elidedText(self.title, Qt.ElideRight, int(w)))
        f.setBold(False)
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(_muted())
        p.drawText(QRectF(tx, r.top() + 27, w, 16), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(f).elidedText(self.artist, Qt.ElideRight, int(w)))
        # estado
        s = self.state
        col = RED if s in ("failed",) else T.accent.lighter(130) if s == "done" else _muted()
        label = self.msg if (s == "failed" and self.msg) else LABEL[s]
        if s == "downloading":
            label = f"Downloading {int(self.pct)}%"
        sx = r.right() - right - 6
        ic = {"done": "check", "skipped": "check"}.get(s)
        if ic:
            k = 16 * (1 + 0.5 * math.sin(math.pi * self._pulse)) if s == "done" else 16  # o "check" dá um pulinho ao concluir
            icons.draw(p, ic, QRectF(sx + right - 14 - k / 2, r.top() + 16 - k / 2, k, k), col.name())
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(col)
        if self.retryable:
            pill = self._pill()
            tw = int(pill.left() - 12 - sx)
            p.drawText(QRectF(sx, r.center().y() - 9, tw, 18), Qt.AlignVCenter | Qt.AlignRight, QFontMetrics(f).elidedText(label, Qt.ElideRight, tw))
            p.setPen(Qt.NoPen)
            a = QColor(T.accent)
            a.setAlphaF(0.30 + 0.35 * self._rh)
            p.setBrush(a)
            p.drawRoundedRect(pill, 14, 14)
            icons.draw(p, "refresh", QRectF(pill.left() + 11, pill.center().y() - 7, 14, 14), "#ffffff")
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(pill.left() + 29, pill.top(), pill.width() - 33, pill.height()), Qt.AlignVCenter | Qt.AlignLeft, "Retry")
            p.end()
            return
        p.drawText(QRectF(sx, r.top() + 8, right - 30, 18), Qt.AlignVCenter | Qt.AlignRight, QFontMetrics(f).elidedText(label, Qt.ElideRight, right - 30))
        # barra
        bar = QRectF(sx + 10, r.top() + 34, right - 16, 5)
        if s in ("searching", "converting", "downloading", "queued") or s == "done":
            p.setBrush(T.ovc(0.12))
            p.drawRoundedRect(bar, 2.5, 2.5)
            frac = 1.0 if s == "done" else 0.0 if s in ("queued", "searching") else (1.0 if s == "converting" else self._shown / 100.0)
            if s in ("searching", "converting"):  # indeterminado: faixa de brilho correndo
                seg = bar.width() * 0.38
                x = bar.left() - seg + (bar.width() + seg) * self._sh
                p.save()
                cp = QPainterPath()
                cp.addRoundedRect(bar, 2.5, 2.5)
                p.setClipPath(cp)
                g = QLinearGradient(x, 0, x + seg, 0)
                c0 = QColor(T.accent)
                c0.setAlpha(0)
                c1 = QColor(T.accent)
                g.setColorAt(0, c0)
                g.setColorAt(0.5, c1)
                g.setColorAt(1, c0)
                p.setBrush(g)
                p.drawRect(QRectF(x, bar.top(), seg, bar.height()))
                p.restore()
            elif frac > 0:
                p.setBrush(T.accent)
                w = bar.width() * max(0.0, min(1.0, frac))
                p.drawRoundedRect(QRectF(bar.left(), bar.top(), w, bar.height()), 2.5, 2.5)
                if s == "downloading" and w > 6:  # ponta brilhando
                    gl = QColor(T.accent.lighter(160))
                    gl.setAlphaF(0.9)
                    p.setBrush(gl)
                    p.drawEllipse(QRectF(bar.left() + w - 5, bar.top() - 0.5, 6, 6))
        p.end()


class DownloadQueue(QScrollArea):
    play = Signal(int)
    retry = Signal(int)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.rows = {}
        self.body = QWidget()
        self.vl = QVBoxLayout(self.body)
        self.vl.setContentsMargins(0, 0, 6, 0)
        self.vl.setSpacing(2)
        self.vl.addStretch()
        self.setWidget(self.body)
        self.hint = QLabel("Paste a Spotify, YouTube or SoundCloud link (song or playlist) and press Download.", self.body)
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.vl.insertWidget(0, self.hint)

    def clear(self):
        for r in self.rows.values():
            r.hide()
            r.deleteLater()
        self.rows = {}
        self.hint.hide()

    def remove(self, idx):
        r = self.rows.pop(idx, None)
        if r is not None:
            r.collapse(lambda r=r: (r.hide(), r.deleteLater()))

    def reset_hint(self):
        self.hint.setVisible(not self.rows)

    def add_entries(self, entries):
        self.hint.hide()
        for n, e in enumerate(entries):
            row = DownloadRow(e)
            row.play.connect(self.play)
            row.retry.connect(self.retry)
            self.rows[e["idx"]] = row
            self.vl.insertWidget(self.vl.count() - 1, row)
            row.enter(min(n, 12) * 45)

    def set_state(self, idx, state, pct, msg):
        row = self.rows.get(idx)
        if row is not None:
            try:
                row.set_state(state, pct, msg)
            except RuntimeError:
                pass
            if state == "downloading" or state == "searching":
                self.ensureWidgetVisible(row, 0, 30)
