# sem janelas nativas do sistema
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import re
from pathlib import Path
import pytest
pytest.importorskip("PySide6.QtSvg")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_ui_smoke import win  # noqa: F401  (mesma janela de teste, motor de áudio falso)

def _extra_windows(win):
    return [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not win and not w.windowFlags() & Qt.ToolTip]

def test_now_playing_lives_inside_the_main_window(win):
    t, _ = win.lib.add_track("Song", "Art", path="/s.mp3")
    win.queue.set_tracks([t], 0)
    win.cur = win.lib.get_track(t)
    win.show_np()
    QApplication.processEvents()
    assert win.np.isVisible() and win.np.window() is win and not win.np.isWindow()  # filho da janela, sem barra do sistema
    assert _extra_windows(win) == []
    r = win.np.geometry()
    assert r == win.root.rect()  # cobre a janela e acompanha o tamanho
    win.resize(1000, 700)
    QApplication.processEvents()
    assert win.np.geometry() == win.root.rect()
    QTest.keyClick(win.np, Qt.Key_Escape)
    assert not win.np.isVisible()  # Esc fecha
    win.show_np()
    win.np.close_sheet()
    assert not win.np.isVisible()

def test_clicking_outside_the_sheet_closes_it(win):
    from PySide6.QtCore import QPoint
    win.show_np()
    QApplication.processEvents()
    QTest.mouseClick(win.np, Qt.LeftButton, Qt.NoModifier, QPoint(3, 3))
    assert not win.np.isVisible()

def test_file_dialog_lists_filters_and_returns(tmp_path, win):
    from hexsound.ui import pickers
    (tmp_path / "B dir").mkdir()
    (tmp_path / "a dir").mkdir()
    (tmp_path / ".hidden").mkdir()
    for n in ("z.mp3", "A.flac", "cover.jpg", "notes.txt"):
        (tmp_path / n).write_bytes(b"x")
    d = pickers.GlassFileDialog(win, "Add audio files", "open", pickers.AUDIO_EXT, str(tmp_path), multi=True)
    names = [d.files.item(i).text() for i in range(d.files.count())]
    assert names == ["a dir", "B dir", "A.flac", "z.mp3"]  # pastas primeiro, sem ocultos, só áudio
    assert not d.ok_btn.isEnabled()
    d.files.item(2).setSelected(True)
    d.files.item(3).setSelected(True)
    assert d.ok_btn.isEnabled()
    d._ok()
    assert sorted(Path(p).name for p in d.result_paths) == ["A.flac", "z.mp3"]

def test_file_dialog_navigation_dir_and_save(tmp_path, win):
    from hexsound.ui import pickers
    sub = tmp_path / "Albums"
    sub.mkdir()
    (sub / "x.mp3").write_bytes(b"x")
    d = pickers.GlassFileDialog(win, "Folder", "dir", None, str(tmp_path))
    assert [d.files.item(i).text() for i in range(d.files.count())] == ["Albums"]
    d.files.item(0).setSelected(True)
    d._ok()
    assert d.result_paths == [str(sub.resolve())]
    d = pickers.GlassFileDialog(win, "Open", "open", (".mp3",), str(tmp_path))
    d._open_item(d.files.item(0))
    assert d.cwd == sub.resolve() and d.bk.isEnabled()
    d.go_up()
    assert d.cwd == tmp_path.resolve()
    d._step(-1)
    assert d.cwd == sub.resolve()
    s = pickers.GlassFileDialog(win, "Save", "save", (".zip",), str(tmp_path), "backup")
    assert s.ok_btn.isEnabled()
    s._ok()
    assert s.result_paths == [str(tmp_path.resolve() / "backup.zip")]  # completa a extensão
    s.name.setText("")
    assert not s.ok_btn.isEnabled()

def test_color_dialog_roundtrip(win):
    from hexsound.ui import pickers
    d = pickers.GlassColorDialog(win, "#8b7cf6")
    assert d.color().name() == "#8b7cf6"
    d.hex.setText("#ff0000")
    d.hex.textEdited.emit("#ff0000")
    assert d.color().name() == "#ff0000"
    d.set_h(0.5)
    d.set_sv(1.0, 1.0)
    assert d.color().name() == "#00ffff"

def test_settings_use_glass_pickers(win, tmp_path, monkeypatch):
    from hexsound.ui import pickers
    from PySide6.QtGui import QColor
    sp = win.page["Settings"]
    img = tmp_path / "bg.png"
    img.write_bytes(b"not a real png")
    monkeypatch.setattr(pickers, "pick_file", lambda *a, **k: str(img))
    seen = []
    monkeypatch.setattr(sp, "set_bg_image", lambda f: seen.append(f))
    sp.pick_bg_image()
    assert seen == [str(img)]
    monkeypatch.setattr(pickers, "pick_color", lambda *a, **k: QColor("#123456"))
    sp.pick_bg_color()
    assert win.settings["bg_color"] == "#123456"
    monkeypatch.setattr(pickers, "pick_dir", lambda *a, **k: str(tmp_path))
    lab = sp.findChildren(type(sp.img_name))[0]
    sp.pick("download_dir", lab)
    assert win.settings["download_dir"] == str(tmp_path)

def test_combo_popup_is_frameless_glass(win):
    from hexsound.ui.widgets import GlassCombo
    c = win.page["Library"].sort
    assert isinstance(c, GlassCombo)
    pop = c.view().window()
    assert pop.windowFlags() & Qt.FramelessWindowHint and pop.testAttribute(Qt.WA_TranslucentBackground)

def test_tray_menu_is_glass(win):
    from hexsound.ui.dialogs import GlassMenu
    assert isinstance(win._tray_menu, GlassMenu) and len(win._tray_menu.actions()) == 5

def test_source_never_uses_native_dialogs():
    bad = re.compile(r"\b(QColorDialog|QMessageBox|QInputDialog|QFontDialog|QErrorMessage)\b")
    for f in Path(__file__).resolve().parents[1].glob("hexsound/**/*.py"):
        assert not bad.search(f.read_text("utf-8")), f"{f.name} usa uma janela nativa"
        if f.name != "pickers.py":
            assert "QFileDialog" not in f.read_text("utf-8"), f"{f.name}: o explorador nativo só é chamado via pickers.py"

def test_small_windows_share_one_black_surface(win):
    from hexsound.ui.style import T, pop_base, pop_mix, build_qss
    win.apply_theme("black")
    assert pop_base().name() == "#000000" and "#glassmenu" in build_qss()
    win.apply_theme("dark")
    assert pop_base().name() == "#000000" and pop_mix(0.2) != pop_base()
    assert pop_base().name() in build_qss()  # menus nativos (botão direito nos campos), combos e dicas usam a mesma cor
    win.apply_theme("light")
    assert pop_base().name() == "#ffffff"
    win.apply_theme("dark")

def test_text_field_context_menu_is_glass_with_icons(win, monkeypatch):
    from PySide6.QtWidgets import QLineEdit
    from hexsound.ui import dialogs
    seen = {}
    monkeypatch.setattr(dialogs.GlassMenu, "exec", lambda self, *a: seen.setdefault("acts", [(x.text().split("\t")[0], x.isSeparator(), x.icon().isNull()) for x in self.actions()]))
    e = QLineEdit(win)
    e.setText("abc")
    e.selectAll()
    dialogs.edit_menu(e, e.mapToGlobal(e.rect().center()))
    named = [a for a in seen["acts"] if not a[1]]
    assert {"Undo", "Copy", "Paste"} <= {a[0].replace("&", "") for a in named} and all(not a[2] for a in named)  # todos com ícone
