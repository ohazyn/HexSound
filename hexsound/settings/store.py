import json
from pathlib import Path
from hexsound.app.paths import DATA_DIR

DEFAULTS = {"theme": "dark", "download_dir": str(DATA_DIR / "downloads"), "shared_dir": str(DATA_DIR / "shared"),
            "tray": False, "notify": True, "resume": True, "autostart": False, "volume": 70, "session": {},
            "accent": "Violet", "glass": 60, "reduce_effects": False, "audio_device": "", "library_view": "list",
            "accent_custom": "#8b7cf6", "bg_mode": "auto", "bg_color": "#1b1630", "bg_image": "", "bg_blur": 18, "bg_dim": 35, "bg_animate": True}

class Settings:
    def __init__(self, path=DATA_DIR / "settings.json"):
        self.path = Path(path)
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(self.path.read_text("utf-8")))
        except Exception:
            pass
    def __getitem__(self, k):
        return self.data[k]
    def set(self, k, v):
        self.data[k] = v
        self.save()
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), "utf-8")
        tmp.replace(self.path)
