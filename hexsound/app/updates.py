"""Aviso de versão nova: consulta a última release no GitHub (sem servidor próprio)."""
import json, re, threading, urllib.request
from PySide6.QtCore import QObject, Signal
from hexsound import __version__

REPO = "ohazyn/HexSound"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/"

def parse_version(tag):
    """'v1.2.3' -> (1, 2, 3); None se não parecer uma versão"""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(tag or ""))
    return tuple(int(x) for x in m.group(1).split(".")) if m else None

def is_newer(latest, current=__version__):
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))

def fetch_latest(timeout=6):
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"HexSound/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    tag = str(d.get("tag_name", ""))
    v = parse_version(tag)
    url = str(d.get("html_url", ""))
    if not url.startswith(PAGE):  # só abre links do próprio repositório
        url = PAGE
    return {"tag": tag, "version": ".".join(map(str, v)) if v else tag, "url": url}

class UpdateCheck(QObject):
    """roda a consulta numa thread à parte; result = dict da release, ou None se falhou"""
    result = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
    def start(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._run, daemon=True).start()  # daemon: nunca trava o fechamento do app
    def _run(self):
        try:
            info = fetch_latest()
        except Exception:
            info = None
        self._busy = False
        try:
            self.result.emit(info)
        except RuntimeError:  # app já fechou
            pass
