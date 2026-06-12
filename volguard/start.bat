@echo off
echo Starting VolGuard Trading Signal System...

if not exist .env (
    echo [0/3] Copying .env.example to .env...
    copy .env.example .env
)

echo [1/3] Installing Python dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python dependency installation failed!
    echo Please make sure Python is installed and added to your PATH.
    pause
    exit /b %errorlevel%
)

echo [2/3] Installing frontend dependencies...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Frontend dependency installation npm install failed!
    echo Please make sure Node.js and npm are installed and added to your PATH.
    cd ..
    pause
    exit /b %errorlevel%
)
cd ..

echo [3/3] Launching backend and frontend...
start "VolGuard Backend" cmd /k "cd backend && python main.py"
start "VolGuard Frontend" cmd /k "cd frontend && npm start"

echo.
echo VolGuard is starting up in separate terminal windows.
echo Backend API:  http://localhost:8000
echo Frontend UI:  http://localhost:3000
echo API Docs:     http://localhost:8000/docs
echo.
pause
