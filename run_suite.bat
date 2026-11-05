@echo off
setlocal
rem Run the regression suite and release gates in the terminal.
rem Usage: run_suite.bat [release_1.0|release_1.1|release_1.2|release_1.3|llm] [golden version]
cd /d "%~dp0"
chcp 65001 >nul
set "SYSTEM=%~1"
if "%SYSTEM%"=="" set "SYSTEM=release_1.3"
set "GOLDEN=%~2"
if "%GOLDEN%"=="" set "GOLDEN=v2"

if not exist ".venv\Scripts\python.exe" (
  echo [GoldenGate] No virtual environment yet - running start.bat setup first is recommended. Creating it now...
  py -3 -m venv .venv 2>nul || python -m venv .venv || exit /b 2
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e . -c requirements-lock.txt || exit /b 2
)
set PYTHONIOENCODING=utf-8

".venv\Scripts\python.exe" -m goldengate golden validate || exit /b 2
".venv\Scripts\python.exe" -m goldengate baseline show >nul 2>nul || (
  ".venv\Scripts\python.exe" -m goldengate run --system release_1.0 --golden %GOLDEN% >nul || exit /b 2
  ".venv\Scripts\python.exe" -m goldengate baseline set --release release_1.0 || exit /b 2
)
".venv\Scripts\python.exe" -m goldengate run --system %SYSTEM% --golden %GOLDEN% || exit /b 2
".venv\Scripts\python.exe" -m goldengate compare --baseline baseline --current %SYSTEM%
".venv\Scripts\python.exe" -m goldengate report --run %SYSTEM% --format html
".venv\Scripts\python.exe" -m goldengate gate --run %SYSTEM%
exit /b %ERRORLEVEL%
