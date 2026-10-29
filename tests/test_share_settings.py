import json
from hexsound.library.db import Library
from hexsound.playlists import share
from hexsound.settings.store import Settings

def make(tmp_path, name="l.db"):
    lib = Library(tmp_path / name)
    a, _ = lib.add_track("Song A", "Art", path="/x/a.mp3")
    y, _ = lib.add_track("Yt Song", "Chan", source="youtube", source_id="abc123XYZ_-")
    return lib, a, y

def test_export_import_roundtrip(tmp_path):
    lib, a, y = make(tmp_path)
    pid = lib.create_playlist("Chill", "relax")
    lib.add_to_playlist(pid, y)
    lib.add_to_playlist(pid, a)
    f = tmp_path / "c.hexplaylist"
    share.export_playlist(lib, pid, f)
    other = Library(tmp_path / "o.db")
    other.add_track("song a", "ART", path="/y/other.mp3")  # casa por título+artista
    res = share.import_playlist(other, f)
    assert res["added"] == 1 and len(res["missing"]) == 1
    assert res["missing"][0]["url"] == "https://www.youtube.com/watch?v=abc123XYZ_-"
    assert res["id"] == pid and other.playlist(pid)["name"] == "Chill"
    res2 = share.import_playlist(other, f)  # mesmo ID já existe: cria outro, sem sobrescrever
    assert res2["id"] != pid and len(other.playlists()) == 2

def test_import_rejects_garbage(tmp_path):
    import pytest
    lib, *_ = make(tmp_path)
    for content in ("nope", json.dumps({"format": "x"}), json.dumps({"format": "hexplaylist", "name": "n", "tracks": "no"})):
        f = tmp_path / "bad.hexplaylist"
        f.write_text(content)
        with pytest.raises(ValueError):
            share.import_playlist(lib, f)

def test_find_by_id_blocks_traversal(tmp_path):
    (tmp_path / "ABC123DEF456.hexplaylist").write_text("{}")
    assert share.find_playlist_file("abc123def456", tmp_path)
    assert share.find_playlist_file("../../etc/passwd", tmp_path) is None
    assert share.find_playlist_file("ZZZZZZ", tmp_path) is None

def test_settings_persist(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("theme", "light")
    s.set("volume", 33)
    s2 = Settings(tmp_path / "s.json")
    assert s2["theme"] == "light" and s2["volume"] == 33 and s2["resume"] is True
    (tmp_path / "s.json").write_text("{corrupt")
    assert Settings(tmp_path / "s.json")["theme"] == "dark"

def test_groups_and_downloads(tmp_path):
    lib, a, y = make(tmp_path)
    assert [t["title"] for t in lib.tracks(downloaded=True)] == ["Yt Song"]
    assert {g["name"] for g in lib.groups("artist")} == {"Art", "Chan"}
    assert lib.groups("album")[0]["name"] == "Unknown" and len(lib.tracks_by("artist", "Art")) == 1
