import hashlib, platform, time
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from hexsound.ui.widgets import _anim, _to
from PySide6.QtGui import QColor, QPainter, QPen
import shutil
from pathlib import Path
from PySide6.QtGui import QConicalGradient
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea, QFrame, QComboBox,
                               QPlainTextEdit, QApplication, QSizePolicy)
from hexsound import __version__
from hexsound.app import backup
from hexsound.app.autostart import set_autostart
from hexsound.app.paths import DATA_DIR
from hexsound.metadata.tags import COVERS_DIR
from hexsound.ui import pickers
from hexsound.ui import dialogs, icons
from hexsound.ui.style import T, ACCENTS
from hexsound.ui.background import bg
from hexsound.ui.widgets import GlassButton, GlassCombo, GlassSlider, Toggle, Segmented, SearchField, ColorButton

CATEGORIES = [("Playback", "play"), ("Audio", "headphones"), ("Appearance", "palette"), ("Library", "library"),
              ("Downloads", "download"), ("Shortcuts", "keyboard"), ("Advanced", "terminal")]
SHORTCUTS = [("Play / Pause", "Space  ·  media key"), ("Next / Previous", "Ctrl + Right / Left"), ("Volume up / down", "Ctrl + Up / Down"),
             ("Shuffle", "Ctrl + S"), ("Repeat", "Ctrl + R"), ("Search", "Ctrl + F"), ("Paste copied files or a link", "Ctrl + V"), ("Quit", "Ctrl + Q")]

class Swatches(QWidget):
    changed = Signal(str)
    custom_clicked = Signal()
    def __init__(self, current, custom="#8b7cf6"):
        super().__init__()
        self.current, self.custom = current, custom
        self._hover = -1
        self.setMouseTracking(True)
        self.setFixedSize((len(ACCENTS) + 1) * 34, 30)
        self.setCursor(Qt.PointingHandCursor)
        self._hp = [0.0] * (len(ACCENTS) + 1)
        self._anims = [_anim(self, lambda v, i=i: self._seth(i, v), ms=140) for i in range(len(self._hp))]
    def _seth(self, i, v):
        self._hp[i] = float(v)
        self.update()
    def mouseMoveEvent(self, e):
        i = int(e.position().x() // 34)
        i = i if 0 <= i < len(self._hp) else -1
        if i != self._hover:
            if self._hover >= 0:
                _to(self._anims[self._hover], self._hp[self._hover], 0.0)
            if i >= 0:
                _to(self._anims[i], self._hp[i], 1.0)
            self._hover = i
    def leaveEvent(self, e):
        if self._hover >= 0:
            _to(self._anims[self._hover], self._hp[self._hover], 0.0)
        self._hover = -1
        super().leaveEvent(e)
    def mousePressEvent(self, e):
        i = int(e.position().x() // 34)
        if i == len(ACCENTS):
            self.custom_clicked.emit()
        elif 0 <= i < len(ACCENTS):
            name = list(ACCENTS)[i]
            if name != self.current:
                self.current = name
                self.changed.emit(name)
                self.update()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i, (name, hexc) in enumerate(ACCENTS.items()):
            c = QPointF(15 + i * 34, 15)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(hexc))
            p.drawEllipse(c, 10 + 1.5 * self._hp[i], 10 + 1.5 * self._hp[i])
            if name == self.current:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(T.fg, 2))
                p.drawEllipse(c, 13.5, 13.5)
        i = len(ACCENTS)
        c = QPointF(15 + i * 34, 15)
        rad = 10 + 1.5 * self._hp[i]
        on = self.current == "Custom"
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(self.custom))
            p.drawEllipse(c, rad, rad)
        else:
            g = QConicalGradient(c, 0)
            for k, col in enumerate(("#ff453a", "#ff9f0a", "#ffd60a", "#30d158", "#0a84ff", "#bf5af2", "#ff453a")):
                g.setColorAt(k / 6, QColor(col))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, rad, rad)
        icons.draw(p, "pencil" if on else "plus", QRectF(c.x() - 6, c.y() - 6, 12, 12), "#ffffff", False, opacity=0.9)
        if on:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(T.fg, 2))
            p.drawEllipse(c, 13.5, 13.5)
    def toolTip(self):
        return ""

class Row(QFrame):
    def __init__(self, title, desc, control, keywords=""):
        super().__init__()
        self.setObjectName("settingRow")
        self.setMinimumHeight(58)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.key = f"{title} {desc} {keywords}".lower()
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 8, 4, 8)
        h.setSpacing(18)
        v = QVBoxLayout()
        v.setSpacing(2)
        t = QLabel(title, objectName="rowTitle")
        v.addWidget(t)
        if desc:
            d = QLabel(desc, objectName="rowDesc")
            d.setWordWrap(True)
            v.addWidget(d)
        h.addLayout(v, 1)
        if control is not None:
            h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
    def paintEvent(self, _):
        sec = self.parentWidget() and self.parentWidget().parentWidget()  # Row → Group → Section
        if sec is None or not hasattr(sec, "is_last") or sec.is_last(self):
            return
        p = QPainter(self)
        p.setPen(QPen(T.ovc(0.10), 1))
        y = self.height() - 1
        p.drawLine(4, y, self.width() - 4, y)

class Section(QWidget):
    def __init__(self, name, icon):
        super().__init__()
        self.name, self.rows = name, []
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 12, 0, 8)
        self.v.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(6, 0, 0, 0)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon, T.fg.name(), 16))
        ic.setFixedWidth(20)
        head.addWidget(ic)
        head.addWidget(QLabel(name.upper(), objectName="sectionTitle"))
        head.addStretch()
        self.v.addLayout(head)
        self.group = QFrame()
        self.group.setObjectName("group")
        self.gl = QVBoxLayout(self.group)
        self.gl.setContentsMargins(14, 2, 14, 2)
        self.gl.setSpacing(0)
        self.v.addWidget(self.group)
    def add(self, row):
        self.rows.append(row)
        self.gl.addWidget(row)
        return row
    def is_last(self, row):
        vis = [r for r in self.rows if not r.isHidden()]
        return not vis or vis[-1] is row
    def filter(self, q):
        n = 0
        for r in self.rows:
            ok = (not q) or q in r.key or q in self.name.lower()
            r.setVisible(ok)
            n += ok
        self.group.setVisible(n > 0 or not q)
        self.group.update()
        return n

class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        s = win.settings
        self.sections = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        h = QLabel("Settings", objectName="h1")
        lay.addWidget(h)
        self.q = SearchField("Search settings")
        self.q.textChanged.connect(self.apply_filter)
        lay.addWidget(self.q)
        self.chips = QWidget()
        ch = QHBoxLayout(self.chips)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(6)
        for name, ic in CATEGORIES:
            b = GlassButton(name, ic, "ghost", size=32)
            b.clicked.connect(lambda _=0, n=name: self.jump(n))
            ch.addWidget(b)
        ch.addStretch()
        lay.addWidget(self.chips)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.bl = QVBoxLayout(body)
        self.bl.setContentsMargins(0, 0, 8, 20)
        self.scroll.setWidget(body)
        lay.addWidget(self.scroll, 1)
        self.empty = QLabel("No settings match your search.", objectName="muted")
        self.empty.hide()
        self.bl.addWidget(self.empty)
        for name, ic in CATEGORIES:
            sec = self.sections[name] = Section(name, ic)
            self.bl.addWidget(sec)
        self.bl.addStretch()
        self._build(s)

    def _toggle(self, key, hook=None):
        t = Toggle(bool(self.win.settings[key]))
        t.toggled.connect(lambda v: (self.win.settings.set(key, v), hook() if hook else None))
        return t
    def _btn(self, text, icon, fn):
        b = GlassButton(text, icon, "glass", size=34)
        b.clicked.connect(lambda _=0: fn())
        return b
    def _folder_ctl(self, key):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        lab = QLabel(self.win.settings[key], objectName="muted")
        lab.setMaximumWidth(260)
        lab.setToolTip(self.win.settings[key])
        lab.setText(lab.fontMetrics().elidedText(lab.text(), Qt.ElideMiddle, 250))
        h.addWidget(lab)
        h.addWidget(self._btn("Change", "folder", lambda: self.pick(key, lab)))
        return box
    def _build(self, s):
        win, S = self.win, self.sections
        S["Playback"].add(Row("Resume last session", "Reopen the previous queue and position when HexSound starts.", self._toggle("resume"), "startup restore"))
        S["Playback"].add(Row("Track change notifications", "Show a notification when the song changes while the window is in the background. Needs the tray icon (Advanced).",
                              self._toggle("notify"), "popup toast"))
        self.vol = GlassSlider(accent=False)
        self.vol.setRange(0, 100)
        self.vol.setFixedWidth(190)
        self.vol.setValue(int(s["volume"]))
        self.vol.valueChanged.connect(lambda v: win.vol.setValue(v) if win.vol.value() != v else None)
        self.vol_lbl = QLabel(f"{int(s['volume'])}%", objectName="muted")
        self.vol_lbl.setFixedWidth(38)
        vb = QWidget()
        vh = QHBoxLayout(vb)
        vh.setContentsMargins(0, 0, 0, 0)
        vh.addWidget(self.vol)
        vh.addWidget(self.vol_lbl)
        S["Audio"].add(Row("Volume", "Master volume of the player.", vb, "loudness sound"))
        self.dev = GlassCombo()
        self.dev.setMinimumWidth(230)
        self.fill_devices()
        self.dev.currentIndexChanged.connect(self.set_device)
        S["Audio"].add(Row("Output device", "Where the sound plays. “System default” follows Windows.", self.dev, "speakers headphones bluetooth"))
        self.theme = Segmented(["Dark", "Black", "Light"], s["theme"].capitalize())
        self.theme.changed.connect(lambda t: win.apply_theme(t.lower()))
        S["Appearance"].add(Row("Theme", "Dark is the Liquid Glass look; Black is pure black for OLED screens; Light is a brighter variant.", self.theme, "dark light black amoled mode"))
        self.sw = Swatches(s["accent"], s["accent_custom"])
        self.sw.changed.connect(lambda n: win.apply_look(accent=n))
        self.sw.custom_clicked.connect(self.pick_accent)
        S["Appearance"].add(Row("Accent color", "Used for selected items, toggles and highlights. The rainbow circle lets you pick any color.", self.sw, "colour custom"))
        self.bgmode = Segmented(["Auto", "Color", "Image"], {"auto": "Auto", "color": "Color", "image": "Image"}[s["bg_mode"]])
        self.bgmode.changed.connect(self.set_bg_mode)
        S["Appearance"].add(Row("Background", "Auto follows the cover of the song that is playing. Or use a solid color, or an image or GIF.", self.bgmode, "wallpaper gif picture"))
        self.bgcol = ColorButton(s["bg_color"])
        self.bgcol.clicked.connect(self.pick_bg_color)
        self.r_col = S["Appearance"].add(Row("Background color", "The base color behind the glass.", self.bgcol, "wallpaper"))
        box = QWidget()
        bh = QHBoxLayout(box)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(8)
        info = QVBoxLayout()
        info.setSpacing(0)
        self.img_name = QLabel("", objectName="muted")
        self.img_note = QLabel("", objectName="muted")
        info.addWidget(self.img_name)
        info.addWidget(self.img_note)
        bh.addLayout(info)
        bh.addWidget(self._btn("Choose…", "image", self.pick_bg_image))
        self.img_rm = self._btn("Remove", "x", self.remove_bg_image)
        bh.addWidget(self.img_rm)
        self.r_img = S["Appearance"].add(Row("Background image", "PNG, JPG, WebP or GIF. A copy is kept inside HexSound’s data folder.", box, "wallpaper gif picture photo"))
        self.r_anim = S["Appearance"].add(Row("Play animated backgrounds", "Lets GIFs and animated WebP move. Turn it off to keep only the first frame and save battery.",
                                              self._toggle("bg_animate", lambda: win.apply_background(bg_animate=bool(win.settings["bg_animate"]), persist=False)), "gif animation motion"))
        self.blur = GlassSlider()
        self.blur.setRange(0, 40)
        self.blur.setFixedWidth(190)
        self.blur.setValue(int(s["bg_blur"]))
        self.blur_l = QLabel(str(int(s["bg_blur"])), objectName="muted")
        self.blur_l.setFixedWidth(30)
        self.blur.valueChanged.connect(lambda v: (self.blur_l.setText(str(v)), win.apply_background(bg_blur=v, persist=False)))
        self.blur.sliderReleased.connect(lambda: win.settings.set("bg_blur", self.blur.value()))
        bb = QWidget()
        bbh = QHBoxLayout(bb)
        bbh.setContentsMargins(0, 0, 0, 0)
        bbh.addWidget(self.blur)
        bbh.addWidget(self.blur_l)
        self.r_blur = S["Appearance"].add(Row("Blur", "0 keeps the image sharp. Higher values blur it behind the glass.", bb, "blurry soften"))
        self.dim = GlassSlider()
        self.dim.setRange(0, 80)
        self.dim.setFixedWidth(190)
        self.dim.setValue(int(s["bg_dim"]))
        self.dim_l = QLabel(f"{int(s['bg_dim'])}%", objectName="muted")
        self.dim_l.setFixedWidth(38)
        self.dim.valueChanged.connect(lambda v: (self.dim_l.setText(f"{v}%"), win.apply_background(bg_dim=v, persist=False)))
        self.dim.sliderReleased.connect(lambda: win.settings.set("bg_dim", self.dim.value()))
        dd = QWidget()
        ddh = QHBoxLayout(dd)
        ddh.setContentsMargins(0, 0, 0, 0)
        ddh.addWidget(self.dim)
        ddh.addWidget(self.dim_l)
        self.r_dim = S["Appearance"].add(Row("Image darkness", "Darkens the image so text stays readable.", dd, "dim brightness overlay"))
        self._bg_rows()
        self.glass = GlassSlider()
        self.glass.setRange(0, 100)
        self.glass.setFixedWidth(190)
        self.glass.setValue(int(s["glass"]))
        self.glass.valueChanged.connect(lambda v: win.apply_look(glass=v, persist=False))
        self.glass.sliderReleased.connect(lambda: win.settings.set("glass", self.glass.value()))
        S["Appearance"].add(Row("Glass intensity", "How visible the translucent surfaces and their reflections are.", self.glass, "transparency blur opacity"))
        S["Appearance"].add(Row("Reduce effects", "Turns off the light background and highlights. Use it if the app feels slow.",
                                self._toggle("reduce_effects", lambda: win.apply_look(reduce=bool(win.settings["reduce_effects"]))), "performance animation motion"))
        S["Library"].add(Row("Rescan files", "Check which tracks still exist on disk. Missing ones are greyed out.", self._btn("Rescan", "refresh", lambda: (win.lib.check_availability(), self.diagnose(), win.refresh_all()))))
        S["Library"].add(Row("Clear unused covers", "Delete cover images that no track or playlist uses anymore.", self._btn("Clear", "image", self.clear_cache)))
        S["Library"].add(Row("Backup", "Save your library, playlists and settings to a .zip file.", self._btn("Backup…", "archive", self.backup)))
        S["Library"].add(Row("Restore backup", "Load a backup. It is applied the next time HexSound starts.", self._btn("Restore…", "upload", self.restore)))
        S["Downloads"].add(Row("Downloads folder", "Where audio imported from links is saved.", self._folder_ctl("download_dir"), "youtube soundcloud"))
        S["Downloads"].add(Row("Shared playlists folder", "Exported playlists are copied here. Point it to a synced folder to share by ID.", self._folder_ctl("shared_dir"), "drive dropbox"))
        for name, keys in SHORTCUTS:
            k = QLabel(keys, objectName="muted")
            S["Shortcuts"].add(Row(name, "", k, "keyboard hotkey"))
        self.adv_toggle = GlassButton("Show advanced options", "chevron-down", "ghost", size=32)
        self.adv_toggle.clicked.connect(self.toggle_adv)
        S["Advanced"].v.addWidget(self.adv_toggle, 0, Qt.AlignLeft)
        S["Advanced"].add(Row("Minimize to tray", "Closing the window keeps HexSound playing in the system tray.", self._toggle("tray", win.update_tray), "system"))
        S["Advanced"].add(Row("Start with Windows", "Open HexSound automatically when you sign in.", self._toggle("autostart", self.set_auto), "startup boot"))
        self.diag = QPlainTextEdit(readOnly=True)
        self.diag.setFixedHeight(190)
        self.diag_row = S["Advanced"].add(Row("Diagnostics", "Versions, library size and recent errors. Useful when reporting a problem.",
                              self._btn("List audio devices", "headphones", self.audio_devices), "log errors version"))
        S["Advanced"].v.addWidget(self.diag)
        self._adv_open = False
        self.toggle_adv(force=False)

    def _bg_rows(self):
        m = self.win.settings["bg_mode"]
        self.r_col.setVisible(m == "color")
        [r.setVisible(m == "image") for r in (self.r_img, self.r_blur, self.r_dim)]
        self.r_anim.setVisible(m == "image" and bg.animated)
        n = self.win.settings["bg_image"]
        self.img_name.setText(self.img_name.fontMetrics().elidedText(Path(n).name, Qt.ElideMiddle, 150) if n else "None")
        self.img_rm.setVisible(bool(n))
        self.img_note.setText(bg.note if n else "")
        self.img_note.setVisible(bool(n))
    def set_bg_mode(self, name):
        self.win.apply_background(bg_mode=name.lower())
        self._bg_rows()
    def pick_accent(self):
        c = pickers.pick_color(self, self.win.settings["accent_custom"], "Accent color")
        if c is not None:
            self.win.settings.set("accent_custom", c.name())
            self.win.apply_look(accent="Custom", custom=c.name())
            self.sw.custom = c.name()
            self.sw.current = "Custom"
            self.sw.update()
    def pick_bg_color(self):
        c = pickers.pick_color(self, self.win.settings["bg_color"], "Background color")
        if c is not None:
            self.bgcol.set_color(c.name())
            self.win.apply_background(bg_color=c.name())
    def pick_bg_image(self):
        f = pickers.pick_file(self, "Choose a background", pickers.IMAGE_EXT, label="Images and GIFs")
        if f:
            self.set_bg_image(f)
    def set_bg_image(self, f):
        src = Path(f)
        dst_dir = DATA_DIR / "backgrounds"
        dst_dir.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha1()
        with open(src, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        dst = dst_dir / f"bg_{h.hexdigest()[:12]}{src.suffix.lower()}"  # nome único: trocar de fundo nunca sobrescreve um arquivo aberto
        if not dst.exists():
            shutil.copy2(src, dst)
        old = self.win.settings["bg_image"]
        self.win.apply_background(bg_image=str(dst), bg_mode="image")
        self.bgmode.set_current("Image")
        self._bg_rows()
        self._drop_old(old, dst)
    def _drop_old(self, old, keep=None):
        """no Windows o arquivo fica travado até o QMovie soltar"""
        if not old or (keep and Path(old) == Path(keep)):
            return
        p = Path(old)
        if p.parent != DATA_DIR / "backgrounds":
            return
        def rm():
            try:
                p.unlink()
            except OSError:
                pass
        QTimer.singleShot(1500, rm)
    def remove_bg_image(self):
        old = self.win.settings["bg_image"]
        self.win.apply_background(bg_image="", bg_mode="auto")
        self.bgmode.set_current("Auto")
        self._bg_rows()
        self._drop_old(old)

    def toggle_adv(self, *_, force=None):
        self._adv_open = (not self._adv_open) if force is None else force
        adv = self.sections["Advanced"]
        for r in adv.rows:
            r.setVisible(self._adv_open)
        self.diag.setVisible(self._adv_open)
        self.adv_toggle.setText("Hide advanced options" if self._adv_open else "Show advanced options")
        self.adv_toggle.set_icon("chevron-up" if self._adv_open else "chevron-down")
    def jump(self, name):
        if name == "Advanced" and not self._adv_open:
            self.toggle_adv(force=True)
        self.scroll.verticalScrollBar().setValue(self.sections[name].y())
    def apply_filter(self, text):
        q = text.strip().lower()
        total = 0
        for name, sec in self.sections.items():
            if name == "Advanced":
                self.adv_toggle.setVisible(not q)
                if q:
                    n = sec.filter(q)
                    self.diag.setVisible(self.diag_row.isVisible())
                else:
                    n = 1
                    for r in sec.rows:
                        r.setVisible(True)
                    self.toggle_adv(force=self._adv_open)
            else:
                n = sec.filter(q)
            sec.setVisible(n > 0 or not q)
            total += n
        self.chips.setVisible(not q)
        self.empty.setVisible(bool(q) and total == 0)
        if not q:
            self._bg_rows()
    def attach(self):
        self.win.vol.valueChanged.connect(self._vol_from_bar)
    def refresh(self):
        self.diagnose()
    def _vol_from_bar(self, v):
        self.vol.blockSignals(True)
        self.vol.setValue(v)
        self.vol.blockSignals(False)
        self.vol_lbl.setText(f"{v}%")
    def fill_devices(self):
        from hexsound.player import engine
        self.dev.blockSignals(True)
        self.dev.clear()
        self.dev.addItem("System default", "")
        for d in engine.list_outputs():
            self.dev.addItem(d, d)
        i = self.dev.findData(self.win.settings["audio_device"])
        self.dev.setCurrentIndex(max(i, 0))
        self.dev.blockSignals(False)
    def set_device(self, _):
        name = self.dev.currentData() or ""
        if self.win.engine.set_device(name):
            self.win.settings.set("audio_device", name)
        else:
            dialogs.notify(self, "Audio", "That device is not available right now.", "warn")
    def set_auto(self):
        if not set_autostart(self.win.settings["autostart"]):
            dialogs.notify(self, "Not available", "Start with Windows is only available on Windows.", "warn")
    def pick(self, key, label):
        d = pickers.pick_dir(self, "Choose a folder", self.win.settings[key])
        if d:
            self.win.settings.set(key, d)
            label.setToolTip(d)
            label.setText(label.fontMetrics().elidedText(d, Qt.ElideMiddle, 250))
    def clear_cache(self):
        used = {r[0] for r in self.win.lib.conn.execute("SELECT cover FROM tracks UNION SELECT cover FROM playlists")}
        n = 0
        for f in (COVERS_DIR.glob("*") if COVERS_DIR.exists() else []):
            if str(f) not in used:
                f.unlink()
                n += 1
        dialogs.notify(self, "Cache cleared", f"Removed {n} unused cover file(s).", "success")
    def backup(self):
        f = pickers.save_file(self, "Save backup", f"hexsound-backup-{time.strftime('%Y%m%d')}.zip", ".zip", label="Zip archive")
        if f:
            backup.make_backup(self.win.lib, f)
            dialogs.notify(self, "Backup saved", f"Saved to {f}", "success")
    def restore(self):
        f = pickers.pick_file(self, "Restore backup", (".zip",), label="Zip archive")
        if not f:
            return
        try:
            backup.stage_restore(f)
        except Exception as e:
            return dialogs.notify(self, "Restore failed", str(e), "error")
        dialogs.notify(self, "Backup staged", "Restart HexSound to finish restoring.", "success")
    def audio_devices(self):
        from hexsound.player import engine
        outs = engine.list_outputs() or ["none found"]
        self.diag.appendPlainText("\nAudio outputs: " + "; ".join(outs))
    def diagnose(self):
        import PySide6, mutagen
        try:
            import yt_dlp.version as v
            ytv = v.__version__
        except Exception:
            ytv = "not installed"
        lib = self.win.lib
        c = lambda q: lib.conn.execute(q).fetchone()[0]
        lines = [f"HexSound {__version__} | Python {platform.python_version()} | PySide6 {PySide6.__version__} | mutagen {mutagen.version_string} | yt-dlp {ytv}",
                 f"Data folder: {DATA_DIR}", f"Tracks: {c('SELECT COUNT(*) FROM tracks')} ({c('SELECT COUNT(*) FROM tracks WHERE available=0')} unavailable) | Playlists: {c('SELECT COUNT(*) FROM playlists')}",
                 "", "Recent errors:"] + (self.win.error_log[-20:] or ["(none)"])
        self.diag.setPlainText("\n".join(lines))
