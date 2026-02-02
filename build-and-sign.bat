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
set "PFX=%~dp0imageclassifier_cert.pfx"
if not defined IMAGE_CLASSIFIER_PFX_PASSWORD (
  echo [ERROR] Set IMAGE_CLASSIFIER_PFX_PASSWORD before running. Do not commit the password.
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
if exist "%MAIN:.py=.spec%" del /q "%MAIN:.py:.spec%"

REM Build the standalone EXE (use same Python as release.py when set)
set "PYEXE=py"
if defined IMAGE_CLASSIFIER_PYTHON set "PYEXE=%IMAGE_CLASSIFIER_PYTHON%"
echo [INFO] Running PyInstaller...
"%PYEXE%" -m PyInstaller --onefile --windowed --clean --noupx ^
  --icon "%ICON%" ^
  --name "%EXE_NAME%" ^
  --version-file "%VERSION_FILE%" ^
  --distpath "%DIST_DIR%" ^
  --workpath "build" ^
  --specpath "build" ^
  "%MAIN%"
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  pause
  exit /b 1
)

REM Digitally sign the EXE (Python script so password with ! or %% is safe)
if not exist "%PFX%" (
  echo [ERROR] PFX not found: %PFX%
  echo Place your signing certificate .pfx in the repo root or set PFX path.
  exit /b 1
)
echo [INFO] Signing executable...
py "%~dp0scripts\sign_exe.py" "%DIST_DIR%\%EXE_NAME%.exe"
if errorlevel 1 (
  echo [ERROR] Code signing failed.
  pause
  exit /b 1
)

REM Verify the signature
echo [INFO] Verifying signature...
"%SIGNTOOL%" verify /pa /v "%DIST_DIR%\%EXE_NAME%.exe"
if errorlevel 1 (
  echo [ERROR] Signature verification failed.
  pause
  exit /b 1
)

echo [SUCCESS] Build ^& sign complete!
echo Output: %DIST_DIR%\%EXE_NAME%.exe

popd
exit /b 0
