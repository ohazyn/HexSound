import shutil, sqlite3, zipfile
from hexsound.app.paths import DATA_DIR
from hexsound.metadata.tags import COVERS_DIR

def make_backup(lib, dest):
    tmp = DATA_DIR / "_backup_tmp.db"
    dst = sqlite3.connect(tmp)
    lib.conn.backup(dst)
    dst.close()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "library.db")
        sf = DATA_DIR / "settings.json"
        if sf.exists():
            z.write(sf, "settings.json")
        if COVERS_DIR.exists():
            for c in COVERS_DIR.glob("*"):
                z.write(c, f"covers/{c.name}")
    tmp.unlink()

def stage_restore(zip_path):
    """aplicado na próxima inicialização"""
    with zipfile.ZipFile(zip_path) as z:
        if "library.db" not in z.namelist():
            raise ValueError("This is not a HexSound backup.")
        pend = DATA_DIR / "restore_pending"
        shutil.rmtree(pend, ignore_errors=True)
        pend.mkdir(parents=True)
        z.extractall(pend)

def apply_pending_restore():
    pend = DATA_DIR / "restore_pending"
    if not (pend / "library.db").exists():
        return False
    db = DATA_DIR / "library.db"
    if db.exists():
        shutil.copy2(db, DATA_DIR / "library.db.bak")
    shutil.copy2(pend / "library.db", db)
    if (pend / "settings.json").exists():
        shutil.copy2(pend / "settings.json", DATA_DIR / "settings.json")
    if (pend / "covers").exists():
        shutil.copytree(pend / "covers", COVERS_DIR, dirs_exist_ok=True)
    shutil.rmtree(pend, ignore_errors=True)
    return True
