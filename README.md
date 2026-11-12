# HexSound

Player de música desktop em PySide6, feito por Hazyn

## Como rodar

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python main.py

Testes: `python -m pytest tests`

Pra gerar o .exe no Windows é só rodar o `build_exe.bat` (sai em `dist\HexSound\HexSound.exe` e cria atalho na área de trabalho).

## Atalhos

- Espaço / teclas de mídia: play e pause
- Ctrl+→ / Ctrl+←: próxima e anterior
- Ctrl+↑ / Ctrl+↓: volume
- Ctrl+S shuffle, Ctrl+R repeat, Ctrl+F busca, Ctrl+Q sair
- Ctrl+V: cola arquivos copiados ou um link

## Controles de mídia do Windows

O app aparece no painel de volume e na tela de bloqueio (título, artista, capa, play/pause, próxima, anterior e barra de progresso), e as teclas de mídia funcionam com ele em segundo plano. Usa o pacote `winrt` (só no Windows); se ele faltar, o app abre normalmente sem esse recurso. Dá pra desligar em Settings → Playback.

## Onde ficam os dados

Tudo em `%USERPROFILE%\.hexsound` (banco, configurações, capas, downloads, playlists compartilhadas).

## Baixar por link

no import tu pode colar os links do spotfy youtube e soundcloud e o futuro pretendo add mais.

- baixa 3 faixas ao mesmo tempo e dá pra cancelar
- não duplica: confere o link e também título/artista/duração
- se der 403 é o YouTube que mudou algo: `pip install -U yt-dlp` e refaz o .exe. "Retry failed" tenta só as que falharam
- precisa de internetpra instalar (meio obvio) O ffmpeg vem no pacote `imageio-ffmpeg`

O áudio do Spotify tem DRM e não é baixado. O app lê só título, artista e capa do link e procura a mesma música no YouTube/SoundCloud. Se não achar nada parecido, a faixa fica como "Failed". Álbuns e playlists do Spotify vão até 

## Compartilhar playlists

Playlists → Export gera um `.hexplaylist`. A cópia também vai pra pasta "Shared playlists" (Settings); se essa pasta for sincronizada (Drive, Dropbox), outra pessoa importa pelo ID em "Import by ID". Não existe servidor.

## O que ainda falta

- arrastar pra reordenar só funciona em playlist; na fila é remover e adicionar de novo

## Código

- `hexsound/ui/widgets.py`: botoes de vidro
- `hexsound/ui/icons.py`: ícones Lucide embutidos
- `hexsound/ui/style.py`: tema e QSS
- `hexsound/ui/settings_page.py`: configurações
- `hexsound/ui/pickers.py`: seletores de arquivo, pasta e cor
