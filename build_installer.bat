@echo off
REM Gera o instalador HexSoundSetup.exe (precisa do Inno Setup instalado neste PC)
setlocal
cd /d "%~dp0"

if not exist "dist\HexSound\HexSound.exe" (
  echo Primeiro gere o app: de dois cliques no build_exe.bat
  pause
  exit /b 1
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
  echo Inno Setup nao encontrado. Instale em https://jrsoftware.org/isdl.php
  echo ou rode: winget install JRSoftware.InnoSetup
  pause
  exit /b 1
)

"%ISCC%" installer.iss
if errorlevel 1 (
  echo Algo deu errado. Copie a mensagem acima e me envie.
  pause
  exit /b 1
)

echo.
echo Pronto! Instalador criado em: %~dp0HexSoundSetup.exe
pause
