@echo off
setlocal
rem GoldenGate one-command start for Windows: venv + install + demo data + dashboard at http://localhost:8000
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo [GoldenGate] Python 3.11 or newer is required. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [GoldenGate] Creating virtual environment...
  %PY% -m venv .venv || goto :error
)

echo [GoldenGate] Installing dependencies (first run takes a minute)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e . -c requirements-lock.txt || goto :error

echo [GoldenGate] Seeding demo data (only if empty)...
".venv\Scripts\python.exe" -m goldengate demo || goto :error

echo [GoldenGate] Starting dashboard (default http://localhost:8000)
".venv\Scripts\python.exe" -m goldengate serve %*
exit /b 0

:error
echo [GoldenGate] Setup failed. See the messages above.
pause
exit /b 1
