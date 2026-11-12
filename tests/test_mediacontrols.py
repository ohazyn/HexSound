import sys
import types
from datetime import timedelta
import pytest
from PySide6.QtWidgets import QApplication
from hexsound.player import mediacontrols as MC


@pytest.fixture(scope="module", autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


def test_noop_fora_do_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    m = MC.MediaControls()
    assert not m.available
    # nenhuma chamada pode levantar erro
    m.set_track("a", "b", "c", None)
    m.set_playing(True)
    m.set_stopped()
    m.set_timeline(1000, 5000)
    m.set_enabled(False)
    m.shutdown()


# ---- um "winrt" de mentira, para testar a nossa lógica sem Windows
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeSMTC:
    def __init__(self):
        self.handlers, self.removed = {}, []
        self.display_updater = _Obj(type=None, thumbnail=None, updated=0,
                                    music_properties=_Obj(title="", artist="", album_title=""),
                                    update=lambda: setattr(self.display_updater, "updated", self.display_updater.updated + 1))
        self.timeline = None
        self.playback_status = None
    def add_button_pressed(self, cb):
        self.handlers["button"] = cb
        return "tok1"
    def add_playback_position_change_requested(self, cb):
        self.handlers["seek"] = cb
        return "tok2"
    def remove_button_pressed(self, tok):
        self.removed.append(tok)
    def remove_playback_position_change_requested(self, tok):
        self.removed.append(tok)
    def update_timeline_properties(self, t):
        self.timeline = t


def _install_fake_winrt(monkeypatch):
    import enum
    class Status(enum.IntEnum):
        CLOSED, CHANGING, STOPPED, PLAYING, PAUSED = 0, 1, 2, 3, 4
    class Type(enum.IntEnum):
        UNKNOWN, MUSIC = 0, 1
    class Btn(enum.IntEnum):
        PLAY, PAUSE, STOP, RECORD, FAST_FORWARD, REWIND, NEXT, PREVIOUS = range(8)
    smtc = FakeSMTC()
    class Timeline:
        pass
    class MediaPlayer:
        def __init__(self):
            self.command_manager = _Obj(is_enabled=True)
            self.system_media_transport_controls = smtc
            self.closed = False
        def close(self):
            self.closed = True
    class Stream:
        @staticmethod
        def create_from_uri(uri):
            return ("stream", uri.text)
    class Uri:
        def __init__(self, text):
            self.text = text
    mods = {
        "winrt": types.ModuleType("winrt"),
        "winrt.windows": types.ModuleType("winrt.windows"),
        "winrt.windows.media": _Obj(MediaPlaybackStatus=Status, MediaPlaybackType=Type, SystemMediaTransportControlsButton=Btn,
                                    SystemMediaTransportControlsTimelineProperties=Timeline),
        "winrt.windows.media.playback": _Obj(MediaPlayer=MediaPlayer),
        "winrt.windows.storage": types.ModuleType("winrt.windows.storage"),
        "winrt.windows.storage.streams": _Obj(RandomAccessStreamReference=Stream),
        "winrt.windows.foundation": _Obj(Uri=Uri),
    }
    for k, v in mods.items():
        monkeypatch.setitem(sys.modules, k, v)
    monkeypatch.setattr(sys, "platform", "win32")
    return smtc, Status, Btn


def test_setup_e_botoes(monkeypatch):
    smtc, Status, Btn = _install_fake_winrt(monkeypatch)
    m = MC.MediaControls()
    assert m.available and smtc.is_enabled and smtc.is_play_enabled and smtc.is_next_enabled
    assert m._mp.command_manager.is_enabled is False
    got = []
    m.play_requested.connect(lambda: got.append("play"))
    m.pause_requested.connect(lambda: got.append("pause"))
    m.next_requested.connect(lambda: got.append("next"))
    m.previous_requested.connect(lambda: got.append("prev"))
    m.seek_requested.connect(lambda ms: got.append(("seek", ms)))
    press = smtc.handlers["button"]
    for b in (Btn.PLAY, Btn.PAUSE, Btn.NEXT, Btn.PREVIOUS, Btn.RECORD):  # RECORD não é nosso: ignora
        press(None, _Obj(button=b))
    smtc.handlers["seek"](None, _Obj(requested_playback_position=timedelta(seconds=12.5)))
    assert got == ["play", "pause", "next", "prev", ("seek", 12500)]


def test_faixa_estado_e_linha_do_tempo(monkeypatch, tmp_path):
    smtc, Status, _ = _install_fake_winrt(monkeypatch)
    cover = tmp_path / "capa.jpg"
    cover.write_bytes(b"x")
    m = MC.MediaControls()
    m.set_track("Titulo", "Artista", "Album", str(cover))
    du = smtc.display_updater
    assert (du.music_properties.title, du.music_properties.artist, du.music_properties.album_title) == ("Titulo", "Artista", "Album")
    assert du.type == 1 and du.updated == 1
    assert du.thumbnail[0] == "stream" and du.thumbnail[1].startswith("file://") and du.thumbnail[1].endswith("capa.jpg")
    m.set_track("Sem capa", "x", "y", "/nao/existe.jpg")  # capa inexistente não derruba nada
    assert du.music_properties.title == "Sem capa" and du.updated == 2
    m.set_playing(True)
    assert smtc.playback_status == Status.PLAYING
    m.set_playing(False)
    assert smtc.playback_status == Status.PAUSED
    m.set_stopped()
    assert smtc.playback_status == Status.STOPPED
    m.set_timeline(90_000, 60_000)  # posição maior que a duração é limitada
    t = smtc.timeline
    assert t.end_time == t.max_seek_time == timedelta(seconds=60) and t.position == timedelta(seconds=60)
    smtc.timeline = None
    m.set_timeline(1000, 0)  # duração desconhecida: não envia nada
    assert smtc.timeline is None
    m.set_enabled(False)
    assert smtc.is_enabled is False


def test_erro_do_windows_nao_derruba_o_app(monkeypatch):
    smtc, _, _ = _install_fake_winrt(monkeypatch)
    m = MC.MediaControls()
    def boom(_):
        raise OSError("COM ocupado")
    smtc.update_timeline_properties = boom
    m.set_timeline(1000, 5000)  # só guarda o erro
    assert "COM ocupado" in m.error


def test_falha_no_setup_deixa_indisponivel(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winrt", None)  # import falha, como se o pacote não estivesse instalado
    monkeypatch.setitem(sys.modules, "winrt.windows", None)
    monkeypatch.setitem(sys.modules, "winrt.windows.media", None)
    m = MC.MediaControls()
    assert not m.available and m.error
    m.set_track("a")  # continua inofensivo
    m.shutdown()


def test_shutdown_remove_callbacks(monkeypatch):
    smtc, _, _ = _install_fake_winrt(monkeypatch)
    m = MC.MediaControls()
    mp = m._mp
    m.shutdown()
    assert smtc.removed == ["tok1", "tok2"] and mp.closed
