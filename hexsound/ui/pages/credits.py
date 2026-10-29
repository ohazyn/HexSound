"""Tela Credits."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from hexsound import __version__
from hexsound.app.paths import resource
from hexsound.ui.home import CoverLabel

class CreditsPage(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        c = CoverLabel(128, 28)
        c.set_cover(str(resource("assets/icon.png")))
        lay.addWidget(c, 0, Qt.AlignCenter)
        t = QLabel("HexSound")
        t.setObjectName("h1")
        t.setAlignment(Qt.AlignCenter)
        m = QLabel("Made by Hazyn")
        m.setAlignment(Qt.AlignCenter)
        v = QLabel(f"Version {__version__}\n\nTechnologies: Python (PSF License) · PySide6 / Qt (LGPLv3) · SQLite (public domain)\n"
                   "Libraries: Mutagen (GPLv2+) · yt-dlp (Unlicense) · PyInstaller (GPLv2 with exception)\n"
                   "Icons: Lucide (ISC License) · App icon artwork: provided by the author (original artist not credited)\n"
                   "License: personal use. Respect the terms of the services you import from.")
        v.setObjectName("muted")
        v.setAlignment(Qt.AlignCenter)
        v.setWordWrap(True)
        for w in (t, m, v):
            lay.addWidget(w)
