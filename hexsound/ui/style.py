from string import Template
from PySide6.QtGui import QColor

ACCENTS = {"Violet": "#8b7cf6", "Blue": "#0a84ff", "Pink": "#ff4f81", "Green": "#30d158", "Orange": "#ff9f0a"}

def pop_base():
    return QColor("#000000") if T.dark else QColor("#ffffff")

def pop_mix(a):
    b, c = pop_base(), T.accent
    return QColor(round(b.red() + (c.red() - b.red()) * a), round(b.green() + (c.green() - b.green()) * a), round(b.blue() + (c.blue() - b.blue()) * a))

def paint_sheet(p, body, radius=26, shadow=True):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPainterPath, QLinearGradient, QPen
    p.setRenderHint(QPainter.Antialiasing)
    if shadow:
        for i in range(10, 0, -1):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 4 + (10 - i) * 2))
            p.drawRoundedRect(body.adjusted(-i, -i + 7, i, i + 7), radius + i, radius + i)
    path = QPainterPath()
    path.addRoundedRect(body, radius, radius)
    g = QLinearGradient(body.topLeft(), body.bottomRight())
    g.setColorAt(0, pop_mix(0.11 if T.dark else 0.07))
    g.setColorAt(0.6, pop_mix(0.03))
    g.setColorAt(1, pop_base())
    p.fillPath(path, g)
    bd = QLinearGradient(body.topLeft(), body.bottomRight())
    a = QColor(T.accent)
    a.setAlphaF(0.30 if T.dark else 0.25)
    bd.setColorAt(0, a)
    bd.setColorAt(0.5, T.ovc(0.16 if T.dark else 0.12))
    bd.setColorAt(1, T.ovc(0.12))
    p.setPen(QPen(bd, 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)

class _Theme:
    def __init__(self):
        self.name, self.accent_name, self.glass, self.reduce, self.custom = "dark", "Violet", 60, False, "#8b7cf6"
        self.update()
    def update(self):
        self.dark = self.name != "light"
        self.accent = QColor(self.custom) if self.accent_name == "Custom" else QColor(ACCENTS.get(self.accent_name, ACCENTS["Violet"]))
        self.fg = QColor("#f5f5f7") if self.dark else QColor("#1c1c1e")
        self.ov = QColor(255, 255, 255) if self.dark else QColor(0, 0, 0)  # cor de sobreposição (hover, bordas)
        black = self.name == "black"
        self.base = QColor("#000000") if black else QColor("#07070c") if self.dark else QColor("#eceaf6")
        self.base2 = QColor("#0a0a0e") if black else QColor("#14121f") if self.dark else QColor("#f8f6ff")
    def configure(self, name=None, accent=None, glass=None, reduce=None, custom=None):
        if name is not None:
            self.name = name
        if custom is not None:
            self.custom = custom
        if accent is not None:
            self.accent_name = accent
        if glass is not None:
            self.glass = int(glass)
        if reduce is not None:
            self.reduce = bool(reduce)
        self.update()
    def ovc(self, a):
        c = QColor(self.ov)
        c.setAlphaF(max(0.0, min(1.0, a)))
        return c
    def rgba(self, a, c=None):
        c = c or self.ov
        return f"rgba({c.red()},{c.green()},{c.blue()},{max(0.0, min(1.0, a)):.3f})"
    @property
    def glass_k(self):  # 0.4 .. 1.6: intensidade do vidro (ajustável nas configurações)
        return 0.4 + 1.2 * self.glass / 100

T = _Theme()

_QSS = Template("""
* { outline:none; }
QWidget { color:$fg; font-family:'Segoe UI Variable Display','Segoe UI','SF Pro Display','Helvetica Neue',sans-serif; font-size:13px; }
QToolTip { background:$popg; color:$fg; border:1px solid $b2; border-radius:8px; padding:5px 9px; }
QLabel { background:transparent; }
QLabel#h1 { font-size:28px; font-weight:700; }
QLabel#h2 { font-size:17px; font-weight:700; }
QLabel#muted, QLabel#rowDesc { color:$muted; }
QLabel#logo { font-size:19px; font-weight:700; }
QLabel#sectionTitle { font-size:12px; font-weight:600; color:$muted; letter-spacing:1px; }
QLabel#rowTitle { font-size:14px; }
QLabel#trackTitle { font-size:13px; font-weight:600; }
QLabel#time { color:$muted; font-size:11px; }

QListWidget { background:transparent; border:none; }
QListWidget::item { padding:8px 12px; border-radius:10px; margin:1px 0; }
QListWidget::item:hover { background:$o06; }
QListWidget::item:selected { background:$o12; }
QListWidget#nav { font-size:14px; }
QListWidget#nav::item { padding:9px 12px; color:$muted; margin:1px 0; }
QListWidget#nav::item:hover { background:$o06; color:$fg; }
QListWidget#nav::item:selected { background:$o12; color:$fg; font-weight:600; }

QTableWidget { background:transparent; border:none; gridline-color:transparent; selection-background-color:$o12; selection-color:$fg; alternate-background-color:transparent; }
QTableWidget::item { padding:4px 8px; border:none; }
QTableWidget::item:hover, QTableWidget::item:selected { background:transparent; }
QHeaderView { background:transparent; }
QHeaderView::section { background:transparent; border:none; border-bottom:1px solid $b1; padding:7px 8px; color:$muted; font-size:11px; font-weight:600; text-align:left; }
QTableCornerButton::section { background:transparent; border:none; }

QLineEdit { background:$o08; border:1px solid $b1; border-radius:18px; padding:8px 14px; selection-background-color:$accent; }
QLineEdit:hover { background:$o10; }
QLineEdit:focus { border:1px solid $b3; background:$o12; }
QComboBox { background:$o08; border:1px solid $b1; border-radius:14px; padding:6px 14px; min-height:20px; }
QComboBox:hover { background:$o12; }
QComboBox::drop-down { border:none; width:22px; }
QComboBox QAbstractItemView { background:$popg; border:1px solid $b2; border-radius:14px; padding:6px; selection-background-color:$accent_a; outline:none; }
QComboBox QAbstractItemView::item { padding:8px 12px; border-radius:9px; min-height:22px; }
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover { background:$accent_a; }
QMenu { background:$popg; border:1px solid $b2; border-radius:14px; padding:8px; }
QMenu#glassmenu { background:transparent; border:none; }
QMenu::item { padding:10px 34px 10px 14px; margin:1px 2px; border-radius:9px; }
QMenu::item:disabled { color:$muted; }
QMenu::icon { padding-left:8px; }
QMenu::right-arrow { margin-right:8px; }
QMenu::item:selected { background:$o12; }
QMenu::separator { height:1px; background:$b1; margin:5px 8px; }
QDialog { background:$dialog; }
QDialog QPushButton { background:$o10; border:1px solid $b1; border-radius:14px; padding:7px 18px; min-width:64px; }
QDialog QPushButton:hover { background:$o16; }
QDialog QPushButton:default { background:$accent; color:#fff; border:none; }
QPlainTextEdit { background:$o04; border:1px solid $b1; border-radius:14px; padding:8px; font-family:Consolas,'Cascadia Mono',monospace; font-size:12px; }
QProgressBar { background:$o10; border:none; border-radius:3px; }
QProgressBar::chunk { background:$accent; border-radius:3px; }
QTabWidget::pane { border:none; }
QTabBar { background:transparent; }
QTabBar::tab { background:transparent; padding:8px 14px; color:$muted; margin-right:4px; border-radius:12px; }
QTabBar::tab:hover { color:$fg; background:$o06; }
QTabBar::tab:selected { color:$fg; background:$o12; }
QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; border:none; }
QScrollBar:vertical { background:transparent; width:12px; margin:2px; }
QScrollBar::handle:vertical { background:$o20; border-radius:4px; min-height:36px; margin:0 2px; }
QScrollBar::handle:vertical:hover { background:$o30; }
QScrollBar:horizontal { background:transparent; height:12px; margin:2px; }
QScrollBar::handle:horizontal { background:$o20; border-radius:4px; min-width:36px; margin:2px 0; }
QScrollBar::handle:horizontal:hover { background:$o30; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { width:0; height:0; background:transparent; }

#settingRow { background:transparent; border:none; }
#group { background:$o05; border:1px solid $b1; border-radius:18px; }
""")

def build_qss(theme=None, accent=None):
    if theme is not None or accent is not None:
        T.configure(name=theme, accent=accent)
    a = T.accent
    pop = pop_base().name()
    popg = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {pop_mix(0.10 if T.dark else 0.06).name()},stop:1 {pop})"
    v = dict(fg=T.fg.name(), muted=T.rgba(0.62, T.fg), pop=pop, popg=popg, dialog="#12101c" if T.dark else "#f4f2fb",
             accent=a.name(), accent_a=f"rgba({a.red()},{a.green()},{a.blue()},0.38)",
             b1=T.rgba(0.10), b2=T.rgba(0.20), b3=T.rgba(0.30))
    for n in (4, 5, 6, 8, 10, 12, 16, 20, 30):
        v[f"o{n:02d}"] = T.rgba(n / 100)
    return _QSS.substitute(v)
