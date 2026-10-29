from pathlib import Path
from PySide6.QtCore import QThread, Signal
from hexsound.metadata.tags import read_tags, scan_folder, extract_cover, AUDIO_EXT

class FileImportWorker(QThread):
    found = Signal(str, dict, object)
    progress = Signal(int, int)
    done = Signal(int)
    def __init__(self, paths):
        super().__init__()
        self.paths = paths
    def run(self):
        files = []
        for p in self.paths:
            if Path(p).is_dir():
                files += list(scan_folder(p))
            elif Path(p).suffix.lower() in AUDIO_EXT:
                files.append(p)
        for i, f in enumerate(files, 1):
            self.found.emit(f, read_tags(f), extract_cover(f))
            self.progress.emit(i, len(files))
        self.done.emit(len(files))
