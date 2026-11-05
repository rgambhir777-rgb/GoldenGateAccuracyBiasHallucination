@echo off
setlocal
rem Build dist\GoldenGate.exe (single file). Double-click it to seed demo data and open the dashboard.
cd /d "%~dp0"
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo [GoldenGate] Creating virtual environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e ".[build]" -c requirements-lock.txt || goto :error

if not exist "frontend\dist\index.html" (
  echo [GoldenGate] frontend\dist is missing. Build it with: cd frontend ^&^& npm install ^&^& npm run build
  goto :error
)

echo [GoldenGate] Building GoldenGate.exe with PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean GoldenGate.spec || goto :error
echo.
echo [GoldenGate] Done: dist\GoldenGate.exe
echo Run it and open http://localhost:8000 (data is stored in dist\goldengate_workspace).
exit /b 0

:error
echo [GoldenGate] Build failed.
exit /b 1
