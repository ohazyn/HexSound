import sys
from pathlib import Path

def set_autostart(on: bool) -> bool:
    """só Windows; False nos outros"""
    if sys.platform != "win32":
        return False
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    try:
        if on:
            cmd = f'"{sys.executable}"' if getattr(sys, "frozen", False) else \
                  f'"{sys.executable}" "{Path(sys.argv[0]).resolve()}"'
            winreg.SetValueEx(key, "HexSound", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "HexSound")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
    return True
