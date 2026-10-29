import os, sys
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QStandardPaths, QDir
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStyledItemDelegate,
                               QStyle, QAbstractItemView, QFileDialog, QDialog)
from hexsound.ui import icons
from hexsound.ui.dialogs import GlassDialog, confirm
from hexsound.ui.style import T
from hexsound.ui.widgets import GlassButton

_last = {"dir": ""}  # lembra a última pasta usada durante a sessão
AUDIO_EXT = (".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

def _size(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024

def _hidden(e):
    if e.name.startswith("."):
        return True
    try:
        return bool(getattr(e.stat(), "st_file_attributes", 0) & 2)  # Windows: atributo 'oculto'
    except OSError:
        return False

def _places():
    out = []
    for name, icon, loc in (("Home", "house", QStandardPaths.HomeLocation), ("Desktop", "monitor", QStandardPaths.DesktopLocation),
                            ("Documents", "file-text", QStandardPaths.DocumentsLocation), ("Music", "music", QStandardPaths.MusicLocation),
                            ("Downloads", "download", QStandardPaths.DownloadLocation), ("Pictures", "image", QStandardPaths.PicturesLocation)):
        p = QStandardPaths.writableLocation(loc)
        if p and os.path.isdir(p) and p not in [o[2] for o in out]:
            out.append((name, icon, p))
    for d in QDir.drives():
        p = d.absoluteFilePath()
        out.append((p.rstrip("/\\") or "Computer" if sys.platform == "win32" else "Computer", "hard-drive", p))
    return out

class _PlaceDelegate(QStyledItemDelegate):
    def sizeHint(self, o, i):
        return QSize(100, 38)
    def paint(self, p, o, idx):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(o.rect).adjusted(2, 2, -2, -2)
        cur = bool(o.state & QStyle.State_Selected)
        if cur:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.accent.red(), T.accent.green(), T.accent.blue(), 80))
            p.drawRoundedRect(r, 11, 11)
        elif o.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(T.ovc(0.07))
            p.drawRoundedRect(r, 11, 11)
        icons.draw(p, idx.data(Qt.UserRole + 1), QRectF(r.left() + 10, r.center().y() - 9, 18, 18), (T.accent.lighter(135) if T.dark else T.accent).name() if cur else T.fg.name(), opacity=1.0 if cur else 0.8)
        f = p.font()
        f.setPixelSize(13)
        f.setWeight(f.Weight.DemiBold if cur else f.Weight.Normal)
        p.setFont(f)
        p.setPen(T.fg)
        p.drawText(QRectF(r.left() + 38, r.top(), r.width() - 44, r.height()), Qt.AlignVCenter, idx.data(Qt.DisplayRole))
        p.restore()

class _FileDelegate(QStyledItemDelegate):
    def sizeHint(self, o, i):
        return QSize(100, 46)
    def paint(self, p, o, idx):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(o.rect).adjusted(2, 2, -2, -2)
        sel, is_dir, name, path = bool(o.state & QStyle.State_Selected), idx.data(Qt.UserRole + 1), idx.data(Qt.DisplayRole), idx.data(Qt.UserRole)
        if sel:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.accent.red(), T.accent.green(), T.accent.blue(), 80))
            p.drawRoundedRect(r, 12, 12)
        elif o.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(T.ovc(0.07))
            p.drawRoundedRect(r, 12, 12)
        tile = QRectF(r.left() + 8, r.center().y() - 15, 30, 30)
        a = QColor(T.accent)
        if not is_dir:
            a = QColor(T.fg)
        c1 = QColor(a)
        c1.setAlphaF(0.30 if is_dir else 0.16)
        p.setPen(Qt.NoPen)
        p.setBrush(c1)
        p.drawRoundedRect(tile, 9, 9)
        ext = Path(path).suffix.lower()
        ic = "folder" if is_dir else "music" if ext in AUDIO_EXT else "image" if ext in IMAGE_EXT else "file"
        icons.draw(p, ic, QRectF(tile.center().x() - 9, tile.center().y() - 9, 18, 18), (a.lighter(135) if (is_dir and T.dark) else a).name())
        f = p.font()
        f.setPixelSize(13)
        f.setWeight(f.Weight.DemiBold if is_dir else f.Weight.Normal)
        p.setFont(f)
        p.setPen(T.fg)
        right = 84
        p.drawText(QRectF(tile.right() + 12, r.top(), r.width() - 62 - right, r.height()), Qt.AlignVCenter,
                               p.fontMetrics().elidedText(name, Qt.ElideRight, int(r.width() - 62 - right)))
        m = QColor(T.fg)
        m.setAlphaF(0.55)
        p.setPen(m)
        f.setWeight(f.Weight.Normal)
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(r.right() - right - 8, r.top(), right, r.height()), Qt.AlignVCenter | Qt.AlignRight, idx.data(Qt.UserRole + 2) or "")
        p.restore()

class GlassFileDialog(GlassDialog):
    """mode: 'open' | 'dir' | 'save'"""
    def __init__(self, parent, title, mode="open", exts=None, start="", suggested="", multi=False, label=""):
        super().__init__(parent, "folder")
        self.mode, self.exts, self.multi, self.result_paths = mode, tuple(e.lower() for e in (exts or ())), multi, []
        self.setWindowTitle(title)
        self.setFixedSize(880 + 2 * self.PAD, 580 + 2 * self.PAD)
        self.body.setContentsMargins(self.PAD + 22, self.PAD + 18, self.PAD + 22, self.PAD + 18)
        self.body.setSpacing(10)
        self.hist, self.hi = [], -1
        top = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("font-size:19px;font-weight:700;")
        top.addWidget(t)
        top.addStretch()
        x = GlassButton("", "x", "ghost", size=34, tooltip="Close")
        x.clicked.connect(self.reject)
        top.addWidget(x)
        self.body.addLayout(top)
        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.bk = GlassButton("", "arrow-left", "glass", size=36, tooltip="Back")
        self.bk.clicked.connect(lambda: self._step(-1))
        self.fw = GlassButton("", "arrow-right", "glass", size=36, tooltip="Forward")
        self.fw.clicked.connect(lambda: self._step(1))
        self.up = GlassButton("", "arrow-up", "glass", size=36, tooltip="Up one folder")
        self.up.clicked.connect(self.go_up)
        self.path = QLineEdit()
        self.path.setMinimumHeight(36)
        self.path.addAction(icons.icon("folder", T.fg.name(), 16), QLineEdit.LeadingPosition)
        self.path.returnPressed.connect(self._path_enter)
        for w in (self.bk, self.fw, self.up):
            nav.addWidget(w)
        nav.addWidget(self.path, 1)
        self.body.addLayout(nav)
        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.body.addLayout(mid, 1)
        self.places = QListWidget()
        self.places.setFixedWidth(184)
        self.places.setItemDelegate(_PlaceDelegate())
        self.places.setMouseTracking(True)
        self.places.setFocusPolicy(Qt.NoFocus)
        for name, icon, p in _places():
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, p)
            it.setData(Qt.UserRole + 1, icon)
            self.places.addItem(it)
        self.places.itemClicked.connect(lambda it: self.go(it.data(Qt.UserRole)))
        mid.addWidget(self.places)
        self.files = QListWidget()
        self.files.setItemDelegate(_FileDelegate())
        self.files.setMouseTracking(True)
        self.files.setFocusPolicy(Qt.StrongFocus)
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection if multi else QAbstractItemView.SingleSelection)
        self.files.itemDoubleClicked.connect(self._open_item)
        self.files.itemSelectionChanged.connect(self._sel)
        self.files.itemActivated.connect(self._open_item)
        self.files.keyPressEvent = self._files_key
        mid.addWidget(self.files, 1)
        self.empty = QLabel("", self.files)
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.name = QLineEdit(suggested)
        self.name.setPlaceholderText("File name")
        self.name.setMinimumHeight(36)
        self.name.setVisible(mode == "save")
        self.name.textChanged.connect(self._sel)
        self.name.returnPressed.connect(self._ok)
        self.info = QLabel(label or ("Folders" if mode == "dir" else ""), objectName="muted")
        foot.addWidget(self.name, 1 if mode == "save" else 0)
        foot.addWidget(self.info, 1)
        foot.addStretch(0)
        self.cancel_btn = GlassButton("Cancel", None, "glass", size=40)
        self.cancel_btn.setMinimumWidth(104)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = GlassButton({"open": "Open", "dir": "Select folder", "save": "Save"}[mode], "check", "accent", size=40)
        self.ok_btn.setMinimumWidth(128)
        self.ok_btn.clicked.connect(self._ok)
        foot.addWidget(self.cancel_btn)
        foot.addWidget(self.ok_btn)
        self.body.addLayout(foot)
        s = Path(start) if start else Path(_last["dir"] or QStandardPaths.writableLocation(QStandardPaths.MusicLocation) or Path.home())
        if s.is_file():
            s = s.parent
        self.cwd = Path.home()
        self.go(s if s.is_dir() else Path.home())
        self.files.setFocus()

    def go(self, p, push=True):
        p = Path(p)
        try:
            p = p.resolve()
        except OSError:
            pass
        if not p.is_dir():
            return
        self.cwd = p
        if push:
            self.hist = self.hist[:self.hi + 1] + [p]
            self.hi = len(self.hist) - 1
        self.path.setText(str(p))
        self._load()
        self.bk.setEnabled(self.hi > 0)
        self.fw.setEnabled(self.hi < len(self.hist) - 1)
        self.up.setEnabled(p.parent != p)
        for i in range(self.places.count()):  # destaca o lugar atual (se for um deles)
            it = self.places.item(i)
            same = Path(it.data(Qt.UserRole)) == p
            if same:
                self.places.setCurrentItem(it)
        if not any(Path(self.places.item(i).data(Qt.UserRole)) == p for i in range(self.places.count())):
            self.places.clearSelection()
    def _step(self, d):
        j = self.hi + d
        if 0 <= j < len(self.hist):
            self.hi = j
            self.go(self.hist[j], push=False)
    def go_up(self):
        if self.cwd.parent != self.cwd:
            self.go(self.cwd.parent)
    def _path_enter(self):
        p = Path(os.path.expanduser(self.path.text().strip().strip('"')))
        if p.is_dir():
            self.go(p)
        elif p.is_file() and self.mode != "dir":
            self.go(p.parent)
            self._select_name(p.name)
        else:
            self.path.setText(str(self.cwd))
    def _select_name(self, n):
        for i in range(self.files.count()):
            if self.files.item(i).text() == n:
                self.files.setCurrentRow(i)
                break
    def _load(self):
        self.files.clear()
        self.empty.hide()
        dirs, files = [], []
        try:
            with os.scandir(self.cwd) as it:
                for e in it:
                    if _hidden(e):
                        continue
                    try:
                        isd = e.is_dir()
                    except OSError:
                        continue
                    if isd:
                        dirs.append(e)
                    elif self.mode != "dir" and (not self.exts or e.name.lower().endswith(self.exts)):
                        files.append(e)
        except OSError:
            self.empty.setText("Can’t open this folder.")
            self._place_empty()
            return
        for e in sorted(dirs, key=lambda e: e.name.casefold()) + sorted(files, key=lambda e: e.name.casefold()):
            isd = e.is_dir()
            it = QListWidgetItem(e.name)
            it.setData(Qt.UserRole, e.path)
            it.setData(Qt.UserRole + 1, isd)
            try:
                it.setData(Qt.UserRole + 2, "Folder" if isd else _size(e.stat().st_size))
            except OSError:
                it.setData(Qt.UserRole + 2, "")
            self.files.addItem(it)
        if not self.files.count():
            self.empty.setText("This folder is empty." if self.mode == "dir" else "No matching files here.")
            self._place_empty()
        self._sel()
    def _place_empty(self):
        self.empty.setGeometry(self.files.rect())
        self.empty.show()
        self.empty.raise_()
        self._sel()
    def _files_key(self, e):
        if e.key() == Qt.Key_Backspace:
            self.go_up()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._ok()
        else:
            QListWidget.keyPressEvent(self.files, e)
    def _open_item(self, it):
        if it.data(Qt.UserRole + 1):
            self.go(it.data(Qt.UserRole))
        elif self.mode == "open":
            self._ok()
        elif self.mode == "save":
            self.name.setText(it.text())

    def _selected(self):
        return [i for i in self.files.selectedItems()]
    def _sel(self, *_):
        sel = self._selected()
        fl = [i for i in sel if not i.data(Qt.UserRole + 1)]
        if self.mode == "open":
            self.ok_btn.setEnabled(bool(fl))
            self.info.setText(f"{len(fl)} selected" if len(fl) > 1 else self.info.text() if not fl else fl[0].text())
        elif self.mode == "dir":
            self.ok_btn.setEnabled(True)
            self.info.setText(sel[0].text() if sel else str(self.cwd.name or self.cwd))
        else:
            self.ok_btn.setEnabled(bool(self.name.text().strip()))
    def _ok(self):
        if not self.ok_btn.isEnabled():
            sel = self._selected()
            if sel and sel[0].data(Qt.UserRole + 1):
                self.go(sel[0].data(Qt.UserRole))
            return
        sel = self._selected()
        if self.mode == "open":
            self.result_paths = [i.data(Qt.UserRole) for i in sel if not i.data(Qt.UserRole + 1)]
        elif self.mode == "dir":
            self.result_paths = [sel[0].data(Qt.UserRole) if sel and sel[0].data(Qt.UserRole + 1) else str(self.cwd)]
        else:
            n = self.name.text().strip()
            if self.exts and not n.lower().endswith(self.exts):
                n += self.exts[0]
            tgt = self.cwd / n
            if tgt.exists() and not confirm(self, "Replace file?", f"“{n}” already exists in this folder. Replace it?", "Replace", "Cancel", danger=True):
                return
            self.result_paths = [str(tgt)]
        _last["dir"] = str(self.cwd if self.mode != "dir" else Path(self.result_paths[0]))
        self.accept()
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.empty.isVisible():
            self.empty.setGeometry(self.files.rect())

def _start(start=""):
    return start or _last["dir"] or QStandardPaths.writableLocation(QStandardPaths.MusicLocation) or str(Path.home())
def _filter(exts, label):
    if not exts:
        return "All files (*)"
    return f"{label or 'Files'} ({' '.join('*' + e for e in exts)});;All files (*)"
def _remember(path):
    if path:
        _last["dir"] = str(Path(path) if Path(path).is_dir() else Path(path).parent)

# Seletores NATIVOS do sistema (o explorador de arquivos original do Windows).
def pick_files(parent, title="Choose files", exts=AUDIO_EXT, start="", label="Audio files"):
    fs, _ = QFileDialog.getOpenFileNames(parent, title, _start(start), _filter(exts, label))
    if fs:
        _remember(fs[0])
    return fs
def pick_file(parent, title="Choose a file", exts=None, start="", label=""):
    f, _ = QFileDialog.getOpenFileName(parent, title, _start(start), _filter(exts, label))
    _remember(f)
    return f or None
def pick_dir(parent, title="Choose a folder", start=""):
    d = QFileDialog.getExistingDirectory(parent, title, _start(start))
    _remember(d)
    return d or None
def save_file(parent, title, suggested, ext, start="", label=""):
    f, _ = QFileDialog.getSaveFileName(parent, title, str(Path(_start(start)) / suggested), _filter((ext,) if ext else None, label))
    _remember(f)
    return f or None

class _SVPane(QWidget):
    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.setFixedSize(300, 190)
        self.setCursor(Qt.CrossCursor)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        c = QPainterPath()
        c.addRoundedRect(r, 14, 14)
        p.setClipPath(c)
        p.fillRect(r, QColor.fromHsvF(self.dlg.h, 1, 1))
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, g)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(r, g)
        p.setClipping(False)
        m = QPointF(self.dlg.s * r.width(), (1 - self.dlg.v) * r.height())
        p.setPen(QPen(QColor(0, 0, 0, 90), 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(m, 8, 8)
        p.setPen(QPen(QColor("#ffffff"), 2.2))
        p.setBrush(self.dlg.color())
        p.drawEllipse(m, 8, 8)
        p.setPen(QPen(T.ovc(0.2), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 14, 14)
    def _set(self, e):
        x, y = e.position().x(), e.position().y()
        self.dlg.set_sv(min(1, max(0, x / self.width())), 1 - min(1, max(0, y / self.height())))
    def mousePressEvent(self, e):
        self._set(e)
    def mouseMoveEvent(self, e):
        self._set(e)

class _HueBar(QWidget):
    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.setFixedSize(300, 22)
        self.setCursor(Qt.PointingHandCursor)
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 4, 0, -4)
        g = QLinearGradient(r.topLeft(), r.topRight())
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF(min(i / 6, 0.999), 1, 1))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 7, 7)
        x = self.dlg.h * (self.width() - 14) + 7
        p.setPen(QPen(QColor(0, 0, 0, 90), 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x, self.height() / 2), 9, 9)
        p.setPen(QPen(QColor("#ffffff"), 2.2))
        p.setBrush(QColor.fromHsvF(self.dlg.h, 1, 1))
        p.drawEllipse(QPointF(x, self.height() / 2), 9, 9)
    def _set(self, e):
        self.dlg.set_h(min(1, max(0, (e.position().x() - 7) / (self.width() - 14))))
    def mousePressEvent(self, e):
        self._set(e)
    def mouseMoveEvent(self, e):
        self._set(e)

PRESETS = ["#8b7cf6", "#0a84ff", "#5ac8fa", "#30d158", "#ffd60a", "#ff9f0a", "#ff453a", "#ff4f81", "#bf5af2", "#1b1630", "#2c2c34", "#ffffff"]

class GlassColorDialog(GlassDialog):
    def __init__(self, parent, initial, title="Pick a color"):
        super().__init__(parent, "palette")
        self.setWindowTitle(title)
        self.header(title, "Drag in the square, or type a hex code.")
        c = QColor(initial)
        self.h, self.s, self.v = [max(0.0, x) for x in (c.hsvHueF(), c.hsvSaturationF(), c.valueF())]
        self.sv, self.hue = _SVPane(self), _HueBar(self)
        self.body.addWidget(self.sv, 0, Qt.AlignHCenter)
        self.body.addWidget(self.hue, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.chip = QLabel()
        self.chip.setFixedSize(44, 36)
        row.addWidget(self.chip)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setMinimumHeight(36)
        self.hex.setValidator(QRegularExpressionValidator(QRegularExpression("#?[0-9A-Fa-f]{0,6}")))
        self.hex.textEdited.connect(self._hex)
        row.addWidget(self.hex, 1)
        self.body.addLayout(row)
        sw = QHBoxLayout()
        sw.setSpacing(6)
        for col in PRESETS:
            b = QLabel()
            b.setFixedSize(21, 21)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"background:{col};border-radius:10px;border:1px solid rgba(255,255,255,0.25);")
            b.mousePressEvent = lambda e, col=col: self.set_color(QColor(col))
            sw.addWidget(b)
        sw.addStretch()
        self.body.addLayout(sw)
        self.buttons("Cancel", "Select", ok_icon="check")
        self.setFixedWidth(360 + 2 * self.PAD)
        self._sync()
    def color(self):
        return QColor.fromHsvF(min(self.h, 0.999), self.s, self.v)
    def set_h(self, h):
        self.h = h
        self._sync()
    def set_sv(self, s, v):
        self.s, self.v = s, v
        self._sync()
    def set_color(self, c):
        self.h, self.s, self.v = max(0.0, c.hsvHueF()), c.hsvSaturationF(), c.valueF()
        self._sync()
    def _hex(self, t):
        t = t.lstrip("#")
        if len(t) == 6:
            self.set_color(QColor("#" + t), from_hex=True) if False else self._apply_hex("#" + t)
    def _apply_hex(self, t):
        c = QColor(t)
        if c.isValid():
            self.h, self.s, self.v = max(0.0, c.hsvHueF()), c.hsvSaturationF(), c.valueF()
            self._sync(skip_hex=True)
    def _sync(self, skip_hex=False):
        c = self.color()
        self.chip.setStyleSheet(f"background:{c.name()};border-radius:12px;border:1px solid rgba(255,255,255,0.3);")
        if not skip_hex:
            self.hex.setText(c.name().upper())
        self.sv.update()
        self.hue.update()

def pick_color(parent, initial, title="Pick a color"):
    d = GlassColorDialog(parent, initial, title)
    return d.color() if d.exec() == QDialog.DialogCode.Accepted else None
