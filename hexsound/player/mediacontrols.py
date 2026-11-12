"""Controles de mídia do Windows (SMTC): painel de volume, tela de bloqueio e teclas de mídia com o app em segundo plano.

Só funciona no Windows e com o pacote winrt instalado. Em qualquer outro caso o objeto existe mas não faz nada,
então o resto do app nunca precisa checar a plataforma nem trata erro daqui."""
import sys
from datetime import timedelta
from pathlib import Path
from PySide6.QtCore import QObject, Signal


class MediaControls(QObject):
    # emitidos na thread principal (o Windows chama o callback em outra thread; o Qt enfileira o sinal)
    play_requested = Signal()
    pause_requested = Signal()
    next_requested = Signal()
    previous_requested = Signal()
    stop_requested = Signal()
    seek_requested = Signal(int)  # ms

    def __init__(self, parent=None, enabled=True):
        super().__init__(parent)
        self.available = False
        self.error = ""
        self._mp = self._smtc = None
        self._tokens = []
        self._cbs = []  # referência forte: se o Python coletar o callback, o Windows chama o vazio
        self._enabled = bool(enabled)
        if sys.platform == "win32":
            try:
                self._setup()
                self.available = True
            except Exception as ex:  # winrt ausente, Windows antigo, COM ocupado...
                self.error = f"{type(ex).__name__}: {ex}"
                self._smtc = self._mp = None

    def _setup(self):
        # importa aqui (depois do QApplication existir) para não brigar com a inicialização COM do Qt
        from winrt.windows.media import (MediaPlaybackStatus, MediaPlaybackType,
                                         SystemMediaTransportControlsButton as Btn,
                                         SystemMediaTransportControlsTimelineProperties)
        from winrt.windows.media.playback import MediaPlayer
        from winrt.windows.storage.streams import RandomAccessStreamReference
        from winrt.windows.foundation import Uri
        self._w = dict(Status=MediaPlaybackStatus, Type=MediaPlaybackType, Timeline=SystemMediaTransportControlsTimelineProperties,
                       Stream=RandomAccessStreamReference, Uri=Uri)
        mp = self._mp = MediaPlayer()
        mp.command_manager.is_enabled = False  # o app controla os botões, não o MediaPlayer
        smtc = self._smtc = mp.system_media_transport_controls
        smtc.is_play_enabled = smtc.is_pause_enabled = True
        smtc.is_next_enabled = smtc.is_previous_enabled = True
        smtc.is_stop_enabled = False
        smtc.is_enabled = self._enabled
        buttons = {Btn.PLAY: self.play_requested, Btn.PAUSE: self.pause_requested, Btn.NEXT: self.next_requested,
                   Btn.PREVIOUS: self.previous_requested, Btn.STOP: self.stop_requested}

        def pressed(_sender, args):
            sig = buttons.get(args.button)
            if sig is not None:
                sig.emit()

        def moved(_sender, args):
            self.seek_requested.emit(int(args.requested_playback_position.total_seconds() * 1000))

        self._cbs += [pressed, moved]
        self._tokens.append(("button_pressed", smtc.add_button_pressed(pressed)))
        self._tokens.append(("playback_position_change_requested", smtc.add_playback_position_change_requested(moved)))

    def _safe(self, fn):
        if self._smtc is None:
            return
        try:
            fn()
        except Exception as ex:
            self.error = f"{type(ex).__name__}: {ex}"

    def set_enabled(self, on):
        self._enabled = bool(on)
        self._safe(lambda: setattr(self._smtc, "is_enabled", self._enabled))

    def set_track(self, title, artist="", album="", cover=None):
        def run():
            du = self._smtc.display_updater
            du.type = self._w["Type"].MUSIC
            m = du.music_properties
            m.title, m.artist, m.album_title = title or "", artist or "", album or ""
            if cover and Path(cover).is_file():
                try:
                    du.thumbnail = self._w["Stream"].create_from_uri(self._w["Uri"](Path(cover).resolve().as_uri()))
                except Exception:
                    pass  # capa é opcional: o texto aparece do mesmo jeito
            du.update()
        self._safe(run)

    def set_playing(self, playing):
        S = self._w["Status"] if self._smtc is not None else None
        self._safe(lambda: setattr(self._smtc, "playback_status", S.PLAYING if playing else S.PAUSED))

    def set_stopped(self):
        S = self._w["Status"] if self._smtc is not None else None
        self._safe(lambda: setattr(self._smtc, "playback_status", S.STOPPED))

    def set_timeline(self, position_ms, duration_ms):
        """o Windows continua a contar sozinho enquanto toca; só precisa avisar quando muda (faixa, pausa, seek)"""
        if not duration_ms or duration_ms <= 0:
            return
        def run():
            t = self._w["Timeline"]()
            t.start_time = t.min_seek_time = timedelta(0)
            t.end_time = t.max_seek_time = timedelta(milliseconds=duration_ms)
            t.position = timedelta(milliseconds=max(0, min(position_ms, duration_ms)))
            self._smtc.update_timeline_properties(t)
        self._safe(run)

    def shutdown(self):
        if self._smtc is None:
            return
        for name, tok in self._tokens:
            self._safe(lambda n=name, k=tok: getattr(self._smtc, f"remove_{n}")(k))
        self._tokens.clear()
        self._safe(lambda: self._mp.close())
        self._smtc = self._mp = None
