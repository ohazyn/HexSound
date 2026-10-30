@echo off
REM Gera dist\HexSound\HexSound.exe e cria um atalho na Area de Trabalho. Basta dar dois cliques.
REM Versao corrigida: usa sempre o python de dentro do venv (nao o pip/pyinstaller globais).
setlocal
cd /d "%~dp0"

set "PY=venv\Scripts\python.exe"

if not exist "%PY%" (
  echo Criando ambiente...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3.12 -m venv venv 2>nul
    if not exist "%PY%" py -3.13 -m venv venv 2>nul
  )
  if not exist "%PY%" (
    where python >nul 2>nul
    if errorlevel 1 goto nopy
    python -m venv venv
  )
  if not exist "%PY%" goto erro
)

"%PY%" --version
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto erro

"%PY%" -m PyInstaller --noconsole --noconfirm --clean --name HexSound --icon assets\icon.ico --add-data "assets;assets" --collect-submodules yt_dlp --collect-all yt_dlp_ejs --collect-all imageio_ffmpeg main.py
if errorlevel 1 goto erro

powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\HexSound.lnk'); $s.TargetPath='%~dp0dist\HexSound\HexSound.exe'; $s.WorkingDirectory='%~dp0dist\HexSound'; $s.IconLocation='%~dp0assets\icon.ico'; $s.Save()"
echo.
echo Pronto! Atalho "HexSound" criado na Area de Trabalho.
echo O programa esta em: %~dp0dist\HexSound\HexSound.exe
pause
exit /b 0
:nopy
echo Python nao encontrado. Instale em python.org e marque "Add Python to PATH".
pause
exit /b 1
:erro
echo Algo deu errado. Copie a mensagem acima e me envie.
pause
exit /b 1
