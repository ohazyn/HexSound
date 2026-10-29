import random
from hexsound.library.db import Library
from hexsound.player.queue import PlayQueue

def mk():
    return PlayQueue(random.Random(1))

def test_shuffle_no_repeat_and_original_order_kept():
    q = mk()
    q.set_tracks(list(range(20)), 3)
    q.set_shuffle(True)
    seen = [q.current] + [q.next() for _ in range(19)]
    assert sorted(seen) == list(range(20)) and q.next() is None
    assert q.items == list(range(20)) and seen[0] == 3

def test_repeat_modes():
    q = mk()
    q.set_tracks([1, 2, 3], 2)
    assert q.next(auto=True) is None
    q.repeat = "one"
    assert q.next(auto=True) == 3
    q.repeat = "all"
    assert q.next(auto=True) == 1

def test_play_next_and_add_end():
    q = mk()
    q.set_tracks([1, 2, 3], 0)
    q.play_next(9)
    q.add_end(7)
    assert q.upcoming() == [9, 2, 3, 7]
    q.set_shuffle(True)
    q.add_end(8)
    assert sorted(q.upcoming() + [q.current]) == [1, 2, 3, 7, 8, 9]

def test_remove():
    q = mk()
    q.set_tracks([1, 2, 3, 4], 1)
    q.remove(2)
    assert q.current == 2 and q.upcoming() == [4]

def test_library_dedupe_and_persistence(tmp_path):
    db = tmp_path / "l.db"
    lib = Library(db)
    a, new = lib.add_track("A", path="/x/a.mp3")
    b, new2 = lib.add_track("A", path="/x/a.mp3")
    assert a == b and new and not new2
    lib.set_favorite(a, True)
    pid = lib.create_playlist("Chill")
    t2, _ = lib.add_track("B", path="/x/b.mp3")
    lib.add_to_playlist(pid, a)
    lib.add_to_playlist(pid, t2)
    lib.add_to_playlist(pid, a)
    lib.move_in_playlist(pid, 1, 0)
    lib2 = Library(db)
    assert [t["title"] for t in lib2.playlist_tracks(pid)] == ["B", "A"]
    assert len(lib2.tracks(favorites=True)) == 1 and len(lib2.tracks("b")) == 1
    assert len(lib2.playlist_tracks(lib2.duplicate_playlist(pid))) == 2

from hexsound.importers.links import classify, normalize
def test_classify():
    assert classify("https://youtu.be/dQw4w9WgXcQ") == "youtube_video"
    assert classify("https://www.youtube.com/watch?v=abc&list=PLxyz") == "youtube_video"
    assert classify("https://www.youtube.com/playlist?list=PLabcdefghijkl") == "youtube_playlist"
    assert classify("PLabcdefghijklmnop") == "youtube_playlist"
    assert normalize("PLabcdefghijklmnop", "youtube_playlist").startswith("https://www.youtube.com/playlist?list=")
    assert classify("https://soundcloud.com/a/b") == "soundcloud"
    assert classify("https://open.spotify.com/track/1") == "spotify"
    assert classify("https://example.com") == "unknown"


def test_queue_jump_and_db_cover_history(tmp_path):
    q = mk()
    q.set_tracks([1, 2, 3, 4], 0)
    assert q.jump(2) == 3 and q.upcoming() == [4] and q.jump(99) == 3
    lib = Library(tmp_path / "h.db")
    a, _ = lib.add_track("A", path="/a.mp3")
    lib.set_cover(a, "/c1.jpg")
    lib.set_cover(a, "/c2.jpg")
    lib.mark_played(a)
    assert lib.get_track(a)["cover"] == "/c1.jpg" and len(lib.history()) == 1

def test_extract_cover_mp3(tmp_path):
    from mutagen.id3 import ID3, APIC
    from hexsound.metadata.tags import extract_cover
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    f = tmp_path / "a.mp3"
    f.write_bytes(b"\0" * 16)
    t = ID3()
    t.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=png))
    t.save(str(f))
    out = extract_cover(str(f), tmp_path / "covers")
    assert out and out.endswith(".png") and open(out, "rb").read() == png
    assert extract_cover(str(tmp_path / "none.mp3"), tmp_path / "covers") is None


def test_extract_links_and_classify_extras():
    from hexsound.importers.links import extract_links, clean_error
    txt = "olha isso https://youtu.be/dQw4w9WgXcQ?si=abc, e https://on.soundcloud.com/xYz12\nPLabcdefghijklmnop\nhttps://youtu.be/dQw4w9WgXcQ?si=abc"
    assert extract_links(txt) == ["https://youtu.be/dQw4w9WgXcQ?si=abc", "https://on.soundcloud.com/xYz12", "PLabcdefghijklmnop"]
    assert classify("https://youtu.be/dQw4w9WgXcQ?list=PLabcdefghijkl") == "youtube_video"
    assert classify("https://m.youtube.com/watch?v=abc") == "youtube_video"
    assert classify("https://on.soundcloud.com/xYz12") == "soundcloud"
    assert clean_error(Exception("\x1b[0;31mERROR:\x1b[0m [youtube] x: Private video")).startswith("Vídeo privado")
