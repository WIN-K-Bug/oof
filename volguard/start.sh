#!/bin/bash
echo "Starting VolGuard Trading Signal System..."

[ -f .env ] || cp .env.example .env

echo "[1/3] Installing Python dependencies..."
pip install -r requirements.txt

echo "[2/3] Installing frontend dependencies..."
cd frontend && npm install && cd ..

echo "[3/3] Launching backend and frontend..."
cd backend && python main.py &
cd frontend && npm start &

echo "VolGuard is starting."
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API Docs: http://localhost:8000/docs"
