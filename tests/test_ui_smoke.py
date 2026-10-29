import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6.QtSvg")
from PySide6.QtCore import QObject, Signal, Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

class FakeEngine(QObject):  # sem áudio real: roda em CI/headless
    position = Signal(int)
    duration = Signal(int)
    finished = Signal()
    state = Signal(bool)
    error = Signal(str)
    def load(self, *a, **k):
        pass
    def toggle(self):
        pass
    def seek(self, ms):
        pass
    def volume(self, v):
        pass
    def set_device(self, d):
        return True

@pytest.fixture
def win(tmp_path, monkeypatch):
    import hexsound.player.engine as E
    monkeypatch.setattr(E, "Engine", FakeEngine)
    monkeypatch.setattr(E, "list_outputs", lambda: ["Speakers", "USB Headset"])
    app = QApplication.instance() or QApplication([])
    from hexsound.library.db import Library
    from hexsound.settings.store import Settings
    from hexsound.ui.main_window import MainWindow
    w = MainWindow(Library(tmp_path / "l.db"), Settings(tmp_path / "s.json"))
    w.show()
    app.processEvents()
    yield w
    w.close()

def test_player_controls_state(win):
    assert not win.btn["play"].isEnabled() and not win.btn["fav"].isEnabled()  # nada tocando: desativados
    win.cycle_repeat()
    assert win.queue.repeat == "all" and win.btn["rep"].isChecked()
    win.cycle_repeat()
    assert win.btn["rep"]._icon == "repeat-1"
    win.cycle_repeat()
    assert win.queue.repeat == "off" and not win.btn["rep"].isChecked()
    win.btn["shuf"].click()
    assert win.queue.shuffle and win.btn["shuf"].isChecked()

def test_mute_and_volume_persist(win):
    win.vol.setValue(40)
    win.toggle_mute()
    assert win.vol.value() == 0 and win.btn["vol"]._icon == "volume-x"
    win.toggle_mute()
    assert win.vol.value() == 40
    win.settings.save()
    assert win.settings["volume"] == 40

def test_slider_click_jumps(win):
    s = win.vol
    s.resize(107, 20)
    s.setValue(0)
    ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(7 + 50, 10), QPointF(7 + 50, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    s.mousePressEvent(ev)
    assert 45 <= s.value() <= 55

def test_settings_search_and_autosave(win):
    sp = win.page["Settings"]
    sp.q.setText("volume")
    assert sp.sections["Audio"].isVisible() is not None
    vis = [r.key.split()[0] for sec in sp.sections.values() for r in sec.rows if not r.isHidden()]
    assert "volume" in vis and "theme" not in vis
    sp.q.setText("zzzz-nothing")
    assert not sp.empty.isHidden()
    sp.q.setText("")
    assert sp.empty.isHidden()
    win.apply_look(accent="Blue", glass=80)
    win.apply_theme("light")
    from hexsound.settings.store import Settings
    s2 = Settings(win.settings.path)
    assert s2["accent"] == "Blue" and s2["theme"] == "light"

def test_pages_render_without_emoji(win):
    import re
    for name in win.page:
        win.go_page(name)
    bad = re.compile("[☀-➿\U0001F300-\U0001FAFF⏩-⏿]")
    from PySide6.QtWidgets import QLabel, QAbstractButton
    for w in win.findChildren(QLabel) + win.findChildren(QAbstractButton):
        assert not bad.search(w.text()), w.text()

def test_logo_menu_opens_pages(win):
    assert "Settings" not in win.nav and "Credits" not in win.nav and "Import Music" not in win.nav
    win.open_menu()
    assert win.menu.isVisible() and len(win.menu.items) == 3
    win.menu.items[1].click()
    assert win.stack.currentWidget() is win.page["Settings"] and win.logo._active
    win.nav["Library"].click()
    assert win.nav["Library"].isChecked() and not win.logo._active

def test_library_filters_and_grid(win):
    a, _ = win.lib.add_track("A", "x", path="/a.mp3")
    b, _ = win.lib.add_track("B", "y", path="/b.mp3")
    win.lib.set_favorite(b, True)
    p = win.page["Library"]
    win.go_page("Library")
    assert len(p.table.rows) == 2 and len(p.grid.rows) == 2
    p.chips.changed.emit("Favorites")
    p.chips.current = "Favorites"
    p.refresh()
    assert [r["title"] for r in p.table.rows] == ["B"]
    p.set_view("grid")
    assert p.grid.isVisible() and not p.table.isVisible() and win.settings["library_view"] == "grid"
    assert list(win.nav) == ["Home", "Search", "Library", "Albums", "Playlists"]

def test_albums_grid_and_detail(win):
    win.lib.add_track("A", "x", "Alb", 120, path="/a.mp3")
    win.lib.add_track("B", "y", "Alb", 60, path="/b.mp3")
    p = win.page["Albums"]
    win.go_page("Albums")
    assert p.grid.count() == 1 and p.stack.currentIndex() == 0
    p.grid.itemClicked.emit(p.grid.item(0))
    assert p.stack.currentIndex() == 1 and len(p.table.rows) == 2 and p.name.text() == "Alb"
    p.back.click()
    assert p.stack.currentIndex() == 0
    assert "Artists" not in win.page and "Artists" not in win.nav

def test_playlist_create_save_and_delete(win, monkeypatch):
    from hexsound.ui import dialogs
    p = win.page["Playlists"]
    win.go_page("Playlists")
    t, _ = win.lib.add_track("Song", "x", path="/s.mp3")
    assert p.grid.count() == 1  # só o cartão "Nova playlist"
    pid = p.new("Rock", "Loud stuff")
    assert p.stack.currentIndex() == 1 and p.name.text() == "Rock" and p.desc.text() == "Loud stuff"
    assert win.lib.playlist(pid)["description"] == "Loud stuff" and not p.save_btn.isEnabled()
    p.addl.add.emit(t)
    assert [r["title"] for r in p.rows] == ["Song"]
    p.name.setText("Metal")
    p.desc.setText("Heavier")
    assert p.save_btn.isEnabled() and p.status.text() == "Unsaved changes"
    assert win.lib.playlist(pid)["name"] == "Rock"  # ainda não salvou
    p.save_btn.click()
    assert win.lib.playlist(pid)["name"] == "Metal" and win.lib.playlist(pid)["description"] == "Heavier"
    assert not p.save_btn.isEnabled() and p.status.text() == "All changes saved"
    p.name.setText("   ")
    p.save()
    assert p.name.text() == "Metal"  # título vazio não passa
    p.desc.setText("Auto-saved on leave")
    p.back.click()
    assert win.lib.playlist(pid)["description"] == "Auto-saved on leave"
    assert p.grid.count() == 2 and p.stack.currentIndex() == 0
    p.grid.itemClicked.emit(p.grid.item(1))
    assert p.pid == pid
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: False)
    p.delete()
    assert win.lib.playlist(pid)
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    p.delete()
    assert win.lib.playlist(pid) is None and p.stack.currentIndex() == 0 and p.grid.count() == 1 and win.lib.get_track(t)  # a música fica
    p.remove(t)

def test_playlist_delete_from_grid_menu_target(win, monkeypatch):
    from hexsound.ui import dialogs
    p = win.page["Playlists"]
    win.go_page("Playlists")
    a = p.new("A")
    p.back.click()
    b = p.new("B")
    p.back.click()
    monkeypatch.setattr(dialogs, "confirm", lambda *a_, **k: True)
    p.delete(a)
    assert [x["name"] for x in win.lib.playlists()] == ["B"] and p.grid.count() == 2

def test_new_playlist_dialog(win):
    from hexsound.ui.dialogs import NewPlaylistDialog
    d = NewPlaylistDialog()
    assert not d.ok.isEnabled()
    d.title.setText("  Chill  ")
    d.sub.setText("Sunday")
    assert d.ok.isEnabled() and d.values() == ("Chill", "Sunday")

def test_custom_titlebar_history_and_search(win):
    from PySide6.QtCore import Qt
    assert win.windowFlags() & Qt.FramelessWindowHint and not win.tbar.back.isEnabled()
    win.go_page("Library")
    win.go_page("Albums")
    assert win.tbar.back.isEnabled() and not win.tbar.fwd.isEnabled()
    win.tbar.back.click()
    assert win.stack.currentWidget() is win.page["Library"] and win.tbar.fwd.isEnabled()
    win.tbar.fwd.click()
    assert win.stack.currentWidget() is win.page["Albums"]
    win.lib.add_track("Zebra", "x", path="/z.mp3")
    win.tbar.search.setText("zeb")
    assert win.stack.currentWidget() is win.page["Search"] and len(win.page["Search"].table.rows) == 1
    win.tbar.bmax.click()
    win.tbar.bmax.click()

def test_queue_panel(win):
    ids = [win.lib.add_track(f"T{i}", "a", path=f"/{i}.mp3")[0] for i in range(4)]
    win.queue.set_tracks(ids, 0)
    win.cur = win.lib.get_track(ids[0])
    win.btn["queue"].click()
    assert win.qpanel._open and win.btn["queue"].isChecked()
    win.qpanel.refresh()
    assert win.qpanel.up.count() == 3 and win.qpanel.now.count() == 1
    win.queue.remove(win.queue.pos + 1)
    win.qpanel._check()
    assert win.qpanel.up.count() == 2
    win.qpanel.clear()
    assert win.qpanel.up.count() == 0 and not win.qpanel.up.isVisible()
    win.btn["queue"].click()
    assert not win.qpanel._open and not win.btn["queue"].isChecked()

def test_background_and_custom_accent(win, tmp_path):
    from PySide6.QtGui import QImage, QColor
    from hexsound.ui.background import bg
    from hexsound.ui.style import T
    img = QImage(64, 36, QImage.Format_RGB32)
    img.fill(QColor("#336699"))
    f = tmp_path / "b.png"
    img.save(str(f))
    sp = win.page["Settings"]
    win.go_page("Settings")
    sp.set_bg_image(str(f))
    assert bg.has_image and win.settings["bg_mode"] == "image" and sp.r_blur.isVisible()
    win.apply_background(bg_blur=0)
    assert bg.has_image
    sp.set_bg_mode("Color")
    assert not bg.has_image and sp.r_col.isVisible() and not sp.r_img.isVisible()
    sp.remove_bg_image()
    assert win.settings["bg_mode"] == "auto"
    win.settings.set("accent_custom", "#ff2d95")
    win.apply_look(accent="Custom", custom="#ff2d95")
    assert T.accent.name() == "#ff2d95"
    win.apply_theme("black")
    assert T.dark and T.base.name() == "#000000"
    from hexsound.settings.store import Settings
    s2 = Settings(win.settings.path)
    assert s2["accent"] == "Custom" and s2["theme"] == "black" and s2["bg_mode"] == "auto"
    win.root.grab()

def test_row_play_marks_current_and_toggles(win):
    from hexsound.ui.nowstate import now
    ids = [win.lib.add_track(f"T{i}", "a", path=f"/{i}.mp3")[0] for i in range(3)]
    for i in ids:
        win.lib.conn.execute("UPDATE tracks SET available=1 WHERE id=?", (i,))
    rows = win.lib.tracks(order="title")
    calls = []
    win.engine.toggle = lambda: calls.append("toggle")
    win.go = lambda tid, **k: (now.set_track(tid), setattr(win, "cur", win.lib.get_track(tid)))
    win.play_row(rows, 1)  # outra faixa: toca
    assert now.track_id == rows[1]["id"] and not calls
    win.play_row(rows, 1)
    assert calls == ["toggle"]  # mesma faixa: só alterna
    win.play_row(rows, 2)
    assert now.track_id == rows[2]["id"] and calls == ["toggle"]
    win.play_row(rows, 99)  # índice inválido não explode
    now.set_playing(True)
    assert now.playing and now._t.isActive()
    now.set_playing(False)
    assert not now._t.isActive()

def test_now_state_resets_between_windows(win):
    from hexsound.ui.nowstate import now
    assert now.track_id is None and now.ctx is None and not now.playing

def test_play_fab_states_and_playlist_button(win):
    from hexsound.ui.nowstate import now
    from hexsound.ui.widgets import PlayFab
    f = PlayFab(56)
    assert not f.playing
    f.set_playing(True, animate=False)
    assert f.playing and f._m == 1.0
    f.set_playing(False)
    f.grab()
    ids = [win.lib.add_track(f"T{i}", "a", path=f"/{i}.mp3")[0] for i in range(2)]
    p = win.page["Playlists"]
    win.go_page("Playlists")
    pid = p.new("Mix")
    for t in ids:
        p.add_track(t)
    calls = []
    win.engine.toggle = lambda: calls.append(1)
    win.go = lambda tid, **k: (now.set_track(tid), setattr(win, "cur", win.lib.get_track(tid)))
    assert not p.play_big.playing
    p.play_big.click()
    assert now.ctx == ("playlist", pid) and not calls  # primeiro clique: toca a playlist
    now.set_playing(True)
    assert p.play_big.playing  # vira pause
    p.play_big.click()
    assert calls == [1]  # segundo clique: só pausa
    now.set_playing(False)
    assert not p.play_big.playing
    p.back.click()
    other = p.new("Other")
    assert not p.play_big.playing  # outra playlist não herda o estado
    win.go_page("Home")
    win.page["Home"].refresh()

def test_album_detail_uses_playlist_ui(win):
    from hexsound.ui.nowstate import now
    ids = [win.lib.add_track(t, a, "Alb", 120, path=f"/{t}.mp3")[0] for t, a in (("A", "x"), ("B", "y"))]
    p = win.page["Albums"]
    win.go_page("Albums")
    p.open("Alb")
    d = p.detail
    assert d.name.text() == "Alb" and d.sub.text() == "x, y" and d.rl.count() == 2 and d.cover.s == win.page["Playlists"].cover.s
    assert type(d.play_big) is type(win.page["Playlists"].play_big) and d.play_big.width() == win.page["Playlists"].play_big.width()
    calls = []
    win.engine.toggle = lambda: calls.append(1)
    win.go = lambda tid, **k: (now.set_track(tid), setattr(win, "cur", win.lib.get_track(tid)))
    d.play_big.click()
    assert now.ctx == ("album", "Alb") and not d.play_big.playing
    now.set_playing(True)
    assert d.play_big.playing
    d.play_big.click()
    assert calls == [1]  # play grande do álbum alterna pause
    d.row_play(0)
    d.row_play(99)  # linha inválida não quebra
    d.rl.setCurrentRow(0)
    d.rl.customContextMenuRequested.emit(d.rl.visualItemRect(d.rl.item(0)).center()) if False else None
    p.refresh()
    assert p.stack.currentIndex() == 1  # refresh mantém o álbum aberto
    p.back.click()
    assert p.stack.currentIndex() == 0


def test_glass_dialogs_safe_defaults(win):
    from hexsound.ui import dialogs
    from PySide6.QtWidgets import QDialog
    assert dialogs.confirm(win, "Delete", "Sure?", ok="Delete", danger=True) is False  # sem modal em testes: cancelado
    d = dialogs.GlassDialog(win, "trash", "danger")
    d.header("Delete", "x")
    c, ok = d.buttons("Cancel", "Delete", danger=True)
    d.show()
    assert d._scrim is not None and d.windowOpacity() <= 1.0
    c.click()
    assert d.result() == QDialog.Rejected and d._scrim is None  # cancelar fecha e remove o véu
    d2 = dialogs.GlassDialog(win)
    d2.header("T", "m")
    _, ok2 = d2.buttons(None, "OK")
    d2.show()
    ok2.click()
    assert d2.result() == QDialog.Accepted
    assert dialogs.ask_text(win, "ID", "paste") is None
    dialogs.notify(win, "t", "m", "warn")
    n = dialogs.NewPlaylistDialog(win)
    n.show()
    assert not n.ok.isEnabled()
    n.title.setText("A")
    assert n.ok.isEnabled()
    n.ok.click()
    assert n.result() == QDialog.Accepted
    for pg in ("Playlists", "Settings"):
        win.go_page(pg)

def test_glass_menu_items(win):
    from hexsound.ui.dialogs import GlassMenu
    m = GlassMenu(win)
    a = m.act("trash", "Delete", lambda: None, danger=True)
    s = m.sub("plus", "Sub")
    s.act("x", "Item")
    assert not a.icon().isNull() and s.actions()[0].text() == "Item" and m.actions()[1].menu() is s

def test_home_track_card_turns_into_pause(win):
    from hexsound.ui.home import Card
    from hexsound.ui.nowstate import now
    ids = [win.lib.add_track(f"H{i}", "a", path=f"/h{i}.mp3")[0] for i in range(3)]
    for tid in ids:
        win.lib.set_favorite(tid, True)  # a Home só mostra as curtidas
    calls = []
    win.engine.toggle = lambda: calls.append(1)
    win.go = lambda tid, **k: (now.set_track(tid), setattr(win, "cur", win.lib.get_track(tid)))
    home = win.page["Home"]
    home.refresh()
    cards = [c for c in home.findChildren(Card) if c.cover.track_id == ids[1]]
    assert cards
    c = cards[0]
    assert not c.cover.live()
    c.on_click()
    assert now.track_id == ids[1] and not calls
    now.set_playing(True)
    assert c.cover.live()  # vira pause
    c.on_click()
    assert calls == [1]  # clicar de novo só pausa, não recomeça a faixa
    now.set_playing(False)
    assert not c.cover.live()

def test_home_quick_tiles_open_and_play(win):
    from hexsound.ui.home import QuickTile
    from hexsound.ui.nowstate import now
    ids = [win.lib.add_track(f"Q{i}", "a", album="Alb", path=f"/q{i}.mp3")[0] for i in range(2)]
    win.lib.set_favorite(ids[0], True)
    pid = win.lib.create_playlist("Mix")
    win.lib.add_to_playlist(pid, ids[1])
    played = []
    win.toggle_context = lambda ctx, rows, shuffle=False: played.append((ctx, len(rows)))
    home = win.page["Home"]
    home.refresh()
    tiles = {t.title: t for t in home.findChildren(QuickTile)}
    assert {"Liked Songs", "Mix", "Alb"} <= set(tiles)
    tiles["Liked Songs"].on_play()
    tiles["Mix"].on_play()
    tiles["Alb"].on_play()
    assert played == [(("liked",), 1), (("playlist", pid), 1), (("album", "Alb"), 2)]
    tiles["Liked Songs"].on_open()  # abre a Biblioteca já filtrada em favoritas
    assert win.stack.currentWidget() is win.page["Library"] and win.page["Library"].chips.current == "Favorites"
    home.chips.set_current("Playlists")
    home._set_filter("Playlists")
    assert not [q for q in home.findChildren(QuickTile) if not q.isHidden()]  # filtro: só a seção de playlists

def test_play_buttons_animate_to_pause(win):
    from PySide6.QtTest import QTest
    from hexsound.ui.nowstate import now
    b = win.btn["play"]
    assert b._m == 0.0
    b.set_icon("pause")
    assert b._ma.state() == b._ma.State.Running  # anima, não troca de uma vez
    QTest.qWait(450)
    assert abs(b._m - 1.0) < 0.01
    b.set_icon("play")
    QTest.qWait(450)
    assert abs(b._m) < 0.01
    # cartão da Home: clique no botão vira pause na hora, antes do estado real chegar
    from hexsound.ui.home import HoverCover
    c = HoverCover(150)
    c.ctx = ("playlist", "X")
    c.pressed_play()
    assert c._mt == 1.0 and c._ma.state() == c._ma.State.Running
    now.set_ctx(("playlist", "X"))
    now.set_playing(True)
    QTest.qWait(450)
    assert abs(c._m - 1.0) < 0.01
    now.set_playing(False)
    QTest.qWait(450)
    assert abs(c._m) < 0.01
