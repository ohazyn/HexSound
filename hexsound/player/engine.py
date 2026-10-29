from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

class Engine(QObject):
    position = Signal(int)
    duration = Signal(int)
    finished = Signal()
    state = Signal(bool)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._start = 0
        self.p, self.out = QMediaPlayer(), QAudioOutput()
        self.p.setAudioOutput(self.out)
        self.out.setVolume(0.7)
        self.p.positionChanged.connect(lambda ms: self.position.emit(int(ms)))
        self.p.durationChanged.connect(self._dur)
        self.p.playbackStateChanged.connect(lambda s: self.state.emit(s == QMediaPlayer.PlayingState))
        self.p.mediaStatusChanged.connect(
            lambda s: self.finished.emit() if s == QMediaPlayer.EndOfMedia else None)
        self.p.errorOccurred.connect(lambda _e, msg: self.error.emit(msg))

    def _dur(self, ms):
        self.duration.emit(ms)
        if self._start and ms:
            self.p.setPosition(self._start)
            self._start = 0

    def load(self, path, autoplay=True, start=0):
        self._start = start
        self.p.setSource(QUrl.fromLocalFile(path))
        self.p.play() if autoplay else self.p.pause()
    def toggle(self):
        self.p.pause() if self.p.playbackState() == QMediaPlayer.PlayingState else self.p.play()
    def seek(self, ms):
        self.p.setPosition(ms)
    def volume(self, v):
        self.out.setVolume(v / 100)
    def set_device(self, description):
        from PySide6.QtMultimedia import QMediaDevices
        devs = QMediaDevices.audioOutputs()
        dev = next((d for d in devs if d.description() == description), None) if description else QMediaDevices.defaultAudioOutput()
        if dev is None:
            return False
        self.out.setDevice(dev)
        return True

def list_outputs():
    try:
        from PySide6.QtMultimedia import QMediaDevices
        return [d.description() for d in QMediaDevices.audioOutputs()]
    except Exception:
        return []
