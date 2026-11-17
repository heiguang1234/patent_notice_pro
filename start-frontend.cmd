@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project Python environment not found. Run: python -m venv .venv
    exit /b 1
)
".venv\Scripts\python.exe" -m http.server 5173 --bind 127.0.0.1 --directory frontend
exit /b %errorlevel%
