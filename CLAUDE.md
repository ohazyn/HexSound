# HexSound

Player de música desktop em PySide6 (foco: Windows), visual iOS 26 "Liquid Glass".
Dados do usuário ficam em `%USERPROFILE%\.hexsound` (fora do projeto; nunca commitar).

## Rodar e testar

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python main.py
    python -m pytest tests

Os testes usam `QT_QPA_PLATFORM=offscreen` e `HEXSOUND_NO_MODAL=1` (ver `tests/conftest.py`):
diálogos modais retornam "cancelado" na hora, então nenhum teste trava esperando clique.
Rode a suíte inteira antes de commitar. Ao corrigir um bug, adicione um teste que o reproduza.

## Estrutura

- `hexsound/ui/` interface: `main_window.py` (janela e player), `home.py`, `now_playing.py`, `queue_panel.py`,
  `settings_page.py`, `downloads.py`
- `hexsound/ui/pages/` uma tela por arquivo: `library.py`, `albums.py`, `search.py`, `playlists.py`, `import_page.py`,
  `credits.py`; `rows.py` (linhas, cartões, tabelas e menu de faixa) e `common.py` (utilitários de desenho).
  O `__init__.py` reexporta tudo, então `from hexsound.ui.pages import TrackPage` continua valendo
- `hexsound/ui/widgets.py` componentes de vidro reutilizáveis (GlassPanel, GlassButton, GlassSlider, Toggle...)
- `hexsound/ui/dialogs.py` GlassDialog, GlassMenu, `confirm` / `notify` / `ask_text`
- `hexsound/ui/pickers.py` seletor de arquivo/pasta (`pick_files`, `pick_dir`, `save_file`) e `pick_color`
- `hexsound/ui/style.py` tema e QSS (`T`, `build_qss`); `icons.py` ícones Lucide embutidos
- `hexsound/ui/nowstate.py` estado global de reprodução (`now`); as telas só leem dele
- `hexsound/library/db.py` banco SQLite; `hexsound/player/` engine e fila
- `hexsound/importers/` arquivos, links (yt-dlp) e Spotify; `hexsound/playlists/share.py` export/import

## Regras de interface

- Tudo segue o estilo Liquid Glass: painéis translúcidos, cantos bem arredondados, brilho sutil, sem molduras de caixa.
- **Nada de janelas nativas.** Use `GlassDialog`/`confirm`/`notify`/`ask_text`, `GlassMenu`, os `pick_*` e `pick_color`.
  Não use `QMessageBox`, `QInputDialog`, `QFileDialog`, `QColorDialog` nem `QMenu` puro.
- Nada de janelas separadas: "Now Playing" é uma camada dentro da janela principal.
- Cores via `T` (tema/accent), ícones via `icons.py`. Sem emojis na interface. Respeite `T.reduce` (Reduce effects).
- Favoritar sempre por `MainWindow.set_favorite(tid, on)`, que mantém o coração do player, o Now Playing e as listas em sincronia.
  Não chame `lib.set_favorite` direto na interface.
- Textos visíveis da interface em inglês; comentários de código e README em português.
- Depois de mexer em visual, confira em 1240x800 e no tamanho mínimo (980x640).

## Cuidados

- Áudio do Spotify tem DRM: o app só lê título/artista/capa e procura a faixa em outra fonte. Não tentar baixar do Spotify.
- Não commitar `venv/`, `dist/`, `build/`, arquivos `.whl`, chaves de API ou o banco/biblioteca do usuário.
- Se o download por link der 403, normalmente é o YouTube que mudou: atualizar o `yt-dlp`.
