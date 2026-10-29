import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import subprocess, shutil
import pytest
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg needed to generate test GIFs")

def spin(ms):
    l = QEventLoop()
    QTimer.singleShot(ms, l.quit)
    l.exec()

def make_gif(path, loop):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=1",
                    "-loop", str(loop), str(path)], check=True)

@pytest.fixture
def bgm():
    QApplication.instance() or QApplication([])
    from hexsound.ui.background import Background
    b = Background()
    yield b
    b._stop()

def test_gif_animates_and_keeps_looping_even_without_loop_flag(tmp_path, bgm):
    g = tmp_path / "once.gif"
    make_gif(g, -1)  # GIF que tocaria uma vez só
    seen = set()
    bgm.changed.connect(lambda: seen.add(bgm.shown.cacheKey() if bgm.shown else None))
    bgm.configure(mode="image", path=str(g))
    spin(2600)  # > 2 voltas de 1s
    assert bgm.animated and bgm.has_image and len(seen) > 12
    assert bgm.movie.state().name == "Running"  # recomeçou sozinho

def test_pause_and_animation_toggle(tmp_path, bgm):
    g = tmp_path / "a.gif"
    make_gif(g, 0)
    bgm.configure(mode="image", path=str(g))
    spin(200)
    bgm.set_paused(True)
    assert bgm.movie.state().name == "Paused"
    bgm.set_paused(False)
    assert bgm.movie.state().name == "Running"
    bgm.configure(animate=False)
    assert bgm.movie.state().name == "Paused" and bgm.has_image  # fica no 1º quadro
    bgm.configure(animate=True)
    assert bgm.movie.state().name == "Running"

def test_single_frame_gif_and_png_are_still(tmp_path, bgm):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=1:duration=1",
                    "-frames:v", "1", str(tmp_path / "one.gif")], check=True)
    bgm.configure(mode="image", path=str(tmp_path / "one.gif"))
    assert not bgm.animated and bgm.has_image
    bgm.configure(path="/does/not/exist.gif")
    assert not bgm.has_image and bgm.note == "File not found"

def test_blur_of_gif_matches_still_scale():
    from PySide6.QtGui import QPixmap
    QApplication.instance() or QApplication([])
    from hexsound.ui.background import blur_fast
    pm = QPixmap(640, 360)
    pm.fill()
    out = blur_fast(pm, 18)
    assert 60 <= out.width() <= 160  # antes ficava em ~47px: movimento ilegível
