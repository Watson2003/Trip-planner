@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

if not exist "%BACKEND_DIR%" mkdir "%BACKEND_DIR%"
if not exist "%FRONTEND_DIR%" mkdir "%FRONTEND_DIR%"

cd /d "%BACKEND_DIR%"

if not exist "venv" (
  python -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist ".env" (
  (
    echo NVIDIA_API_KEY=your_key_here
    echo NVIDIA_MODEL=meta/llama-3.1-70b-instruct
    echo GEOAPIFY_API_KEY=your_key_here
    echo OPENWEATHERMAP_API_KEY=your_key_here
    echo OPENROUTESERVICE_API_KEY=your_key_here
  ) > .env
)

cd /d "%FRONTEND_DIR%"

for /f "tokens=1 delims=v." %%a in ('node -v') do set "NODE_VERSION=%%a"
if not defined NODE_VERSION (
  echo Node.js is required but was not found on PATH.
  exit /b 1
)
for /f "tokens=1 delims=." %%a in ("!NODE_VERSION:~1!") do set "NODE_MAJOR=%%a"
if not defined NODE_MAJOR (
  echo Unable to determine the installed Node.js version.
  exit /b 1
)
if !NODE_MAJOR! LSS 18 (
  echo Node.js 18 or newer is required. Current version: !NODE_VERSION!
  exit /b 1
)

npm install

endlocal
