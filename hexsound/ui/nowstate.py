"""estado global de reprodução; as telas leem daqui"""
from PySide6.QtCore import QObject, QTimer, Signal

class NowState(QObject):
    changed = Signal()  # faixa, contexto ou play/pause mudaram
    tick = Signal()  # quadro da animação do equalizador (só enquanto toca)

    def __init__(self):
        super().__init__()
        self.track_id, self.playing, self.ctx, self.phase = None, False, None, 0
        self._t = None

    def reset(self):
        self.track_id, self.playing, self.ctx, self.phase = None, False, None, 0
        if self._t:
            self._t.stop()
        self.changed.emit()

    def is_ctx(self, ctx):
        return ctx is not None and self.ctx == ctx
    def ctx_playing(self, ctx):
        return self.is_ctx(ctx) and self.playing

    def set_track(self, tid):
        self.track_id = tid
        self.changed.emit()
    def set_ctx(self, ctx):
        self.ctx = ctx
        self.changed.emit()
    def set_playing(self, on):
        on = bool(on)
        if on == self.playing:
            return
        self.playing = on
        self._sync_timer()
        self.changed.emit()

    def _sync_timer(self):
        if self._t is None:  # criado sob demanda: precisa existir um QApplication
            self._t = QTimer(self)
            self._t.setInterval(70)
            self._t.timeout.connect(self._step)
        from hexsound.ui.style import T
        self._t.start() if (self.playing and not T.reduce) else self._t.stop()
    def _step(self):
        self.phase += 1
        self.tick.emit()

now = NowState()
