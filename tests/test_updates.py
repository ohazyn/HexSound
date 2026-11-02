import json
from pathlib import Path
import pytest
from hexsound import __version__
from hexsound.app import updates as U


@pytest.mark.parametrize("latest,current,expected", [
    ("v1.0.1", "1.0.0", True),
    ("1.0.0", "1.0.0", False),
    ("v1.10.0", "1.9.9", True),   # compara número a número, não texto
    ("1.0", "1.0.0", False),
    ("v0.9.9", "1.0.0", False),
    ("beta", "1.0.0", False),
    ("", "1.0.0", False),
    (None, "1.0.0", False),
])
def test_is_newer(latest, current, expected):
    assert U.is_newer(latest, current) is expected


def test_version_matches_installer():
    f = Path(__file__).resolve().parent.parent / "installer.iss"
    if not f.exists():
        pytest.skip("installer.iss não está nesta pasta")
    iss = f.read_text(encoding="utf-8")
    assert f'#define MyAppVersion "{__version__}"' in iss  # os dois números têm que andar juntos


class _Resp:
    def __init__(self, data):
        self.data = json.dumps(data).encode()
    def read(self):
        return self.data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_fetch_latest_parses(monkeypatch):
    monkeypatch.setattr(U.urllib.request, "urlopen", lambda req, timeout=0: _Resp(
        {"tag_name": "v1.2.0", "html_url": "https://github.com/ohazyn/HexSound/releases/tag/v1.2.0"}))
    info = U.fetch_latest()
    assert info["version"] == "1.2.0" and info["url"].endswith("/tag/v1.2.0")


def test_fetch_latest_rejects_foreign_url(monkeypatch):
    monkeypatch.setattr(U.urllib.request, "urlopen", lambda req, timeout=0: _Resp(
        {"tag_name": "v9.0.0", "html_url": "https://evil.example.com/x"}))
    assert U.fetch_latest()["url"] == U.PAGE  # nunca abre link de fora do repositório
