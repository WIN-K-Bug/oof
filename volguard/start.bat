@echo off
echo Starting VolGuard Trading Signal System...

if not exist .env copy .env.example .env

echo [1/3] Installing Python dependencies...
pip install -r requirements.txt

echo [2/3] Installing frontend dependencies...
cd frontend
npm install
cd ..

echo [3/3] Launching backend and frontend...
start "VolGuard Backend" cmd /k "cd backend && python main.py"
start "VolGuard Frontend" cmd /k "cd frontend && npm start"

echo VolGuard is starting up.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo API Docs: http://localhost:8000/docs
pause
