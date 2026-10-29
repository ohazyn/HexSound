@echo off
REM Gera dist\HexSound\HexSound.exe e cria um atalho na Area de Trabalho. Basta dar dois cliques.
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopy
if not exist venv\Scripts\activate.bat (
  echo Criando ambiente...
  python -m venv venv
  if errorlevel 1 goto erro
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto erro
pyinstaller --noconsole --noconfirm --clean --name HexSound --icon assets\icon.ico --add-data "assets;assets" --collect-submodules yt_dlp --collect-all yt_dlp_ejs --collect-all imageio_ffmpeg main.py
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
