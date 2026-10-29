import faulthandler, sys, time, traceback
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from hexsound.app.backup import apply_pending_restore
from hexsound.app.paths import DATA_DIR, resource
from hexsound.library.db import Library
from hexsound.settings.store import Settings
from hexsound.ui.main_window import MainWindow

LOG = DATA_DIR / "crash.log"
_native = None

def log(text):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except Exception:
        pass

def excepthook(t, v, tb):
    text = "".join(traceback.format_exception(t, v, tb))
    log(text)
    if QApplication.instance():
        try:  # janela de vidro do app; a caixa nativa fica só como reserva
            from hexsound.ui.dialogs import notify
            notify(None, "HexSound hit a problem", text[-900:] + f"\n\nLog: {LOG}", "error")
        except Exception:
            QMessageBox.critical(None, "HexSound error", text[-1500:] + f"\n\nLog: {LOG}")

def main():
    global _native
    DATA_DIR.mkdir(exist_ok=True)
    _native = open(DATA_DIR / "native_crash.log", "w")  # travamentos nativos (Qt/áudio) caem aqui
    faulthandler.enable(file=_native, all_threads=True)
    sys.excepthook = excepthook
    apply_pending_restore()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hazyn.HexSound")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("HexSound")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(resource("assets/icon.png"))))
    try:
        win = MainWindow(Library(DATA_DIR / "library.db"), Settings())
        win.show()
    except Exception:
        excepthook(*sys.exc_info())
        sys.exit(1)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()