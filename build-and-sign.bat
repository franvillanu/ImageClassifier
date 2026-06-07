@echo off
setlocal enableextensions

REM ============================================
REM  Image Classifier – BUILD & SIGN SCRIPT
REM ============================================

REM --- Navigate to the script’s directory ---
pushd "%~dp0"

REM ---------- CONFIG ------------------------------
set "MAIN=image-classifier.py"
set "EXE_NAME=Image Classifier"
set "ICON=%~dp0star.ico"
set "VERSION_FILE=%~dp0version.txt"
set "DIST_DIR=installer"
set "PACKAGE_MODE=onedir"
set "PFX=%~dp0imageclassifier_cert.pfx"
if defined IMAGE_CLASSIFIER_PACKAGE_MODE set "PACKAGE_MODE=%IMAGE_CLASSIFIER_PACKAGE_MODE%"
if not defined IMAGE_CLASSIFIER_PFX_PASSWORD (
  echo [ERROR] Set IMAGE_CLASSIFIER_PFX_PASSWORD before running. Do not commit the password.
  exit /b 1
)
if /I not "%PACKAGE_MODE%"=="onedir" if /I not "%PACKAGE_MODE%"=="onefile" (
  echo [ERROR] IMAGE_CLASSIFIER_PACKAGE_MODE must be "onedir" or "onefile".
  exit /b 1
)
REM ------------------------------------------------

REM Locate signtool.exe from Windows SDK
set "SIGNTOOL="
for /f "delims=" %%S in ('dir /b /ad "C:\Program Files (x86)\Windows Kits\10\bin" ^| sort /r') do (
  if exist "C:\Program Files (x86)\Windows Kits\10\bin\%%S\x64\signtool.exe" (
    set "SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\%%S\x64\signtool.exe"
    goto :found_signtool
  )
)
:found_signtool
if not defined SIGNTOOL (
  echo [ERROR] signtool.exe not found. Install the Windows SDK.
  exit /b 1
)
echo [INFO] Using signtool: %SIGNTOOL%

REM Clean up previous build artifacts
for %%D in (build dist) do if exist "%%D" rmdir /s /q "%%D"
if exist "%MAIN:.py=.spec%" del /q "%MAIN:.py=.spec%"
if exist "%DIST_DIR%\%EXE_NAME%" rmdir /s /q "%DIST_DIR%\%EXE_NAME%"
if exist "%DIST_DIR%\%EXE_NAME%.exe" del /q "%DIST_DIR%\%EXE_NAME%.exe"

REM Build the standalone EXE (use same Python as release.py when set)
set "PYEXE=py"
if defined IMAGE_CLASSIFIER_PYTHON set "PYEXE=%IMAGE_CLASSIFIER_PYTHON%"
set "PYI_MODE=--onedir"
set "APP_DIR=%DIST_DIR%\%EXE_NAME%"
set "APP_EXE=%APP_DIR%\%EXE_NAME%.exe"
if /I "%PACKAGE_MODE%"=="onefile" (
  set "PYI_MODE=--onefile"
  set "BUILT_EXE=%DIST_DIR%\%EXE_NAME%.exe"
) else (
  set "BUILT_EXE=%APP_EXE%"
)
echo [INFO] Running PyInstaller...
"%PYEXE%" -m PyInstaller %PYI_MODE% --windowed --clean --noupx ^
  --icon "%ICON%" ^
  --name "%EXE_NAME%" ^
  --version-file "%VERSION_FILE%" ^
  --collect-all pillow_heif ^
  --distpath "%DIST_DIR%" ^
  --workpath "build" ^
  --specpath "build" ^
  "%MAIN%"
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  pause
  exit /b 1
)

REM Normalize the payload layout so installer packaging is consistent.
if /I "%PACKAGE_MODE%"=="onefile" (
  if not exist "%APP_DIR%" mkdir "%APP_DIR%"
  move /Y "%BUILT_EXE%" "%APP_EXE%" >nul
)

REM Digitally sign the EXE (Python script so password with ! or %% is safe)
if not exist "%PFX%" (
  echo [ERROR] PFX not found: %PFX%
  echo Place your signing certificate .pfx in the repo root or set PFX path.
  exit /b 1
)
echo [INFO] Signing executable...
py "%~dp0scripts\sign_exe.py" "%APP_EXE%"
if errorlevel 1 (
  echo [ERROR] Code signing failed.
  pause
  exit /b 1
)

REM Verify the signature
echo [INFO] Verifying signature...
"%SIGNTOOL%" verify /pa /v "%APP_EXE%"
if errorlevel 1 (
  echo [ERROR] Signature verification failed.
  pause
  exit /b 1
)

echo [SUCCESS] Build ^& sign complete!
echo Output: %APP_EXE%

popd
exit /b 0
