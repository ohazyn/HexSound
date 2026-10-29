import sqlite3, time, uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks(
 id INTEGER PRIMARY KEY, title TEXT, artist TEXT, album TEXT, duration REAL,
 cover TEXT, source TEXT DEFAULT 'local', source_id TEXT, path TEXT,
 imported_at REAL, last_played REAL, favorite INTEGER DEFAULT 0, available INTEGER DEFAULT 1,
 UNIQUE(source, source_id), UNIQUE(path));
CREATE TABLE IF NOT EXISTS playlists(
 id TEXT PRIMARY KEY, name TEXT, description TEXT DEFAULT '', cover TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS playlist_tracks(
 playlist_id TEXT REFERENCES playlists(id) ON DELETE CASCADE,
 track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE, position INTEGER);
CREATE TABLE IF NOT EXISTS history(track_id INTEGER, played_at REAL);
"""
ORDER = {"title": "title COLLATE NOCASE", "artist": "artist COLLATE NOCASE",
         "duration": "duration", "imported": "imported_at DESC", "played": "last_played DESC"}

_GROUP = {"album": "COALESCE(NULLIF(album,''),'Unknown')", "artist": "COALESCE(NULLIF(artist,''),'Unknown')"}

class Library:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def add_track(self, title, artist="", album="", duration=0.0, path=None,
                  source="local", source_id=None, cover=None):
        """retorna (id, criada)"""
        if path:
            r = self.conn.execute("SELECT id FROM tracks WHERE path=?", (path,)).fetchone()
        else:
            r = self.conn.execute("SELECT id FROM tracks WHERE source=? AND source_id=?",
                                  (source, source_id)).fetchone()
        if r:
            return r["id"], False
        cur = self.conn.execute(
            "INSERT INTO tracks(title,artist,album,duration,path,source,source_id,cover,imported_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (title, artist, album, duration, path, source, source_id or path, cover, time.time()))
        self.conn.commit()
        return cur.lastrowid, True

    def get_track(self, tid):
        return self.conn.execute("SELECT * FROM tracks WHERE id=?", (tid,)).fetchone()

    def tracks(self, search="", order="title", favorites=False, recent=False, downloaded=False):
        sql, args = "SELECT * FROM tracks WHERE 1=1", []
        if search:
            sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ?)"
            args += [f"%{search}%"] * 3
        if favorites:
            sql += " AND favorite=1"
        if downloaded:
            sql += " AND source != 'local'"
        if recent:
            sql += " AND last_played IS NOT NULL"
            order = "played"
        sql += " ORDER BY " + ORDER.get(order, ORDER["title"])
        return self.conn.execute(sql, args).fetchall()

    def set_favorite(self, tid, value):
        self.conn.execute("UPDATE tracks SET favorite=? WHERE id=?", (int(value), tid))
        self.conn.commit()

    def mark_played(self, tid):
        now = time.time()
        self.conn.execute("UPDATE tracks SET last_played=? WHERE id=?", (now, tid))
        self.conn.execute("INSERT INTO history VALUES(?,?)", (tid, now))
        self.conn.commit()

    def set_cover(self, tid, cover):
        self.conn.execute("UPDATE tracks SET cover=? WHERE id=? AND cover IS NULL", (cover, tid))
        self.conn.commit()

    def history(self, limit=50):
        return self.conn.execute("SELECT t.* FROM history h JOIN tracks t ON t.id=h.track_id"
                                 " ORDER BY h.played_at DESC LIMIT ?", (limit,)).fetchall()

    def check_availability(self):
        for r in self.conn.execute("SELECT id,path FROM tracks WHERE path IS NOT NULL").fetchall():
            self.conn.execute("UPDATE tracks SET available=? WHERE id=?",
                              (int(Path(r["path"]).exists()), r["id"]))
        self.conn.commit()

    def create_playlist(self, name, description="", pid=None):
        pid = pid or uuid.uuid4().hex[:12].upper()
        self.conn.execute("INSERT INTO playlists VALUES(?,?,?,NULL,?)",
                          (pid, name, description, time.time()))
        self.conn.commit()
        return pid

    def playlist(self, pid):
        return self.conn.execute("SELECT * FROM playlists WHERE id=?", (pid,)).fetchone()

    def update_playlist(self, pid, description=None, cover=None):
        if description is not None:
            self.conn.execute("UPDATE playlists SET description=? WHERE id=?", (description, pid))
        if cover is not None:
            self.conn.execute("UPDATE playlists SET cover=? WHERE id=?", (cover, pid))
        self.conn.commit()

    def set_playlist_order(self, pid, ids):
        self._rewrite(pid, ids)

    def find_source(self, source, source_id):
        return self.conn.execute("SELECT * FROM tracks WHERE source=? AND source_id=?", (source, source_id)).fetchone()

    def delete_track(self, tid):
        self.conn.execute("DELETE FROM tracks WHERE id=?", (tid,))
        self.conn.commit()

    def groups(self, field):
        f = _GROUP[field]
        return self.conn.execute(f"SELECT {f} AS name, COUNT(*) AS n FROM tracks GROUP BY name "
                                 "ORDER BY name COLLATE NOCASE").fetchall()

    def group_covers(self, field):
        out = {}
        for r in self.conn.execute(f"SELECT {_GROUP[field]} AS name, cover FROM tracks WHERE cover IS NOT NULL ORDER BY id"):
            out.setdefault(r["name"], r["cover"])
        return out

    def tracks_by(self, field, value):
        return self.conn.execute(f"SELECT * FROM tracks WHERE {_GROUP[field]}=? "
                                 "ORDER BY album COLLATE NOCASE, title COLLATE NOCASE", (value,)).fetchall()

    def playlists(self):
        return self.conn.execute("SELECT * FROM playlists ORDER BY created_at").fetchall()

    def rename_playlist(self, pid, name):
        self.conn.execute("UPDATE playlists SET name=? WHERE id=?", (name, pid))
        self.conn.commit()

    def delete_playlist(self, pid):
        self.conn.execute("DELETE FROM playlists WHERE id=?", (pid,))
        self.conn.commit()

    def playlist_tracks(self, pid):
        return self.conn.execute(
            "SELECT t.* FROM playlist_tracks p JOIN tracks t ON t.id=p.track_id"
            " WHERE p.playlist_id=? ORDER BY p.position", (pid,)).fetchall()

    def _rewrite(self, pid, ids):
        self.conn.execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (pid,))
        self.conn.executemany("INSERT INTO playlist_tracks VALUES(?,?,?)",
                              [(pid, t, i) for i, t in enumerate(ids)])
        self.conn.commit()

    def add_to_playlist(self, pid, tid):
        ids = [t["id"] for t in self.playlist_tracks(pid)]
        if tid not in ids:
            self._rewrite(pid, ids + [tid])

    def remove_from_playlist(self, pid, tid):
        self._rewrite(pid, [t["id"] for t in self.playlist_tracks(pid) if t["id"] != tid])

    def move_in_playlist(self, pid, src, dst):
        ids = [t["id"] for t in self.playlist_tracks(pid)]
        ids.insert(dst, ids.pop(src))
        self._rewrite(pid, ids)

    def duplicate_playlist(self, pid):
        old = self.conn.execute("SELECT * FROM playlists WHERE id=?", (pid,)).fetchone()
        new = self.create_playlist(old["name"] + " (copy)", old["description"])
        self._rewrite(new, [t["id"] for t in self.playlist_tracks(pid)])
        return new
