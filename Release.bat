@echo off
setlocal enableextensions enabledelayedexpansion

REM =============================================
REM  Image Classifier – ONE-CLICK RELEASE SCRIPT
REM =============================================

REM --- 1) Jump to this script directory ---
pushd "%~dp0"

REM --- Password: env var or installer\.pfx_password (one line, gitignored; use Python to strip CR/LF/BOM) ---
if not defined IMAGE_CLASSIFIER_PFX_PASSWORD (
  if exist "installer\.pfx_password" (
    REM Escape ! for batch so password with ! is preserved when we set the env var
for /f "delims=" %%a in ('py -c "p=open(r'installer\.pfx_password',encoding='utf-8').read().strip(); print(p.replace(chr(33), chr(94)+chr(33)), end='')"') do set "IMAGE_CLASSIFIER_PFX_PASSWORD=%%a"
  )
)
if not defined IMAGE_CLASSIFIER_PFX_PASSWORD (
  echo [ERROR] PFX password required. Set IMAGE_CLASSIFIER_PFX_PASSWORD or create installer\.pfx_password
  goto :error
)

REM --- 2) Parse filevers=(M, m, b, r) from version.txt ---
for /f "tokens=2-5 delims=(, " %%A in (
  'findstr /i "filevers" version.txt'
) do (
  set "VER_MAJOR=%%A"
  set "VER_MINOR=%%B"
  set "VER_BUILD=%%C"
  set "VER_REV=%%D"
  goto :got_version
)
echo [ERROR] Could not parse filevers from version.txt
goto :error

:got_version
set "VER_REV=%VER_REV:)=%"
set "VER_STR=%VER_MAJOR%.%VER_MINOR%.%VER_BUILD%.%VER_REV%"
set "VER_SHORT=%VER_MAJOR%.%VER_MINOR%"
echo Detected full version: %VER_STR%
echo Using short version: %VER_SHORT%

REM --- 2.5) Optional: Update changelog.html and sync website ---
echo.
set "CHANGELOG_UPDATED=0"
set /p UPDATE_CHANGELOG="Update changelog.html? (y/N): "
if /i "%UPDATE_CHANGELOG%"=="y" (
  py "%~dp0scripts\update_changelog.py"
  if errorlevel 1 (
    echo [WARNING] Changelog update failed, continuing anyway...
  ) else (
    set "CHANGELOG_UPDATED=1"
    REM Sync website files (index.html) with latest version/changelog
    py "%~dp0scripts\update_website.py"
  )
)

REM --- 3) Build & sign the EXE (pass VER_STR if needed) ---
REM Use same Python as "py" for PyInstaller
for /f "delims=" %%a in ('py -c "import sys; print(sys.executable)" 2^>nul') do set "IMAGE_CLASSIFIER_PYTHON=%%a"
py -m PyInstaller --help >nul 2>&1
if errorlevel 1 (
  echo [ERROR] PyInstaller not installed for this Python. Run:  py -m pip install pyinstaller
  goto :error
)
echo.
echo [1/4] Building ^& signing EXE...
call "%~dp0build-and-sign.bat" "%VER_STR%"
if errorlevel 1 (
  echo [ERROR] build-and-sign.bat failed.
  goto :error
)

REM --- 4) Compile Inno Setup installer (sync MyAppVersion from version.txt first) ---
echo.
echo [2/4] Compiling Inno Setup installer...
py "%~dp0scripts\update_iss_version.py"
if errorlevel 1 goto :error
if not exist "Output\" mkdir "Output"

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo [ERROR] ISCC.exe not found.
  goto :error
)

"%ISCC%" /Q /O"%~dp0Output" "%~dp0Image_Classifier.iss"
if errorlevel 1 (
  echo [ERROR] Inno Setup compilation failed.
  goto :error
)

REM --- 5) Sign the installer itself ---
echo.
echo [3/4] Signing the installer…
set "SIGNTOOL="
for /f "delims=" %%S in ('dir /b /ad "C:\Program Files (x86)\Windows Kits\10\bin" ^| sort /r') do (
  if exist "C:\Program Files (x86)\Windows Kits\10\bin\%%S\x64\signtool.exe" (
    set "SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\%%S\x64\signtool.exe"
    goto :found_signtool
  )
)
echo [ERROR] signtool.exe not found. Install the Windows SDK.
goto :error

:found_signtool
REM Sign whatever installer ISCC produced (Python script so password with ! or %% is safe)
set "SETUP_EXE="
set "INST_NAME="
for %%f in ("%~dp0Output\ImageClassifierSetup_v*.exe") do (
  set "SETUP_EXE=%%f"
  set "INST_NAME=%%~nxf"
)
if not defined SETUP_EXE (
  echo [ERROR] No ImageClassifierSetup_v*.exe found in Output.
  goto :error
)
echo Signing: !INST_NAME!
py "%~dp0scripts\sign_exe.py" "!SETUP_EXE!"
if errorlevel 1 (
  echo [ERROR] Signing the installer failed.
  goto :error
)

REM --- 6) Copy changelog.html to Output if it was updated ---
if "%CHANGELOG_UPDATED%"=="1" (
  if exist "docs\changelog.html" (
    copy /Y "docs\changelog.html" "Output\changelog.html" >nul
    echo [INFO] Changelog copied to Output\changelog.html
  )
)

REM --- 7) Success! ---
echo.
echo [SUCCESS] Release complete!
echo    • EXE:       installer\Image Classifier.exe
echo    • Installer: Output\!INST_NAME!
if "%CHANGELOG_UPDATED%"=="1" (
  echo    • Changelog: Output\changelog.html
)
echo.
pause
goto :eof

:error
echo.
echo Press any key to exit...
pause
exit /b 1

:eof
popd
