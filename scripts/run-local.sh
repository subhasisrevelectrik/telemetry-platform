#!/bin/bash
# Run the full local development stack

set -e

echo "===== CAN Telemetry Platform - Local Mode ====="
echo ""

# Check if sample data exists
if [ ! -d "sample-data/decoded" ]; then
    echo "Warning: No sample data found"
    echo "Run: cd sample-data/scripts && python3 generate_sample_data.py"
    echo ""
fi

# Copy sample data to data directory
echo "Copying sample data to ./data/decoded/..."
mkdir -p data/decoded
cp -r sample-data/decoded/* data/decoded/ 2>/dev/null || true

echo ""
echo "Starting services..."
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $(jobs -p) 2>/dev/null || true
    exit
}

trap cleanup EXIT INT TERM

# Start backend
echo "Starting FastAPI backend on :8000..."
cd backend
LOCAL_MODE=true python3 local_dev.py &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 3

# Start frontend if npm is available
if command -v npm &> /dev/null; then
    echo "Starting Vite frontend on :5173..."
    cd frontend
    npm run dev &
    FRONTEND_PID=$!
    cd ..

    echo ""
    echo "===== Services Running ====="
    echo ""
    echo "  Frontend: http://localhost:5173"
    echo "  Backend:  http://localhost:8000"
    echo "  API Docs: http://localhost:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop all services"
    echo ""
else
    echo ""
    echo "===== Backend Running ====="
    echo ""
    echo "  Backend:  http://localhost:8000"
    echo "  API Docs: http://localhost:8000/docs"
    echo ""
    echo "Note: Frontend not started (npm not found)"
    echo "Press Ctrl+C to stop"
    echo ""
fi

# Wait for all background jobs
wait
