#!/bin/bash
# Development environment setup script

set -e

echo "===== CAN Telemetry Platform - Dev Setup ====="
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "Found Python $PYTHON_VERSION"

# Check Node version
echo "Checking Node version..."
if ! command -v node &> /dev/null; then
    echo "Warning: Node.js not found (required for frontend)"
else
    NODE_VERSION=$(node --version)
    echo "Found Node $NODE_VERSION"
fi

# Setup Python virtual environments
echo ""
echo "Setting up Python virtual environments..."

# Edge agent
echo "  - edge-agent"
cd edge-agent
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
deactivate
cd ..

# Backend
echo "  - backend"
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
deactivate
cd ..

# Processing
echo "  - processing/decoder"
cd processing/decoder
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate
cd ../..

# Install frontend dependencies
if command -v npm &> /dev/null; then
    echo ""
    echo "Installing frontend dependencies..."
    cd frontend
    npm install --silent
    cd ..
fi

# Generate sample data
echo ""
echo "Generating sample data..."
cd sample-data/scripts
python3 -m pip install --quiet cantools pyarrow
python3 generate_sample_data.py --duration_min 20
cd ../..

# Create data directories
echo ""
echo "Creating data directories..."
mkdir -p data/decoded
mkdir -p data/archive
mkdir -p data/pending
mkdir -p logs

echo ""
echo "===== Setup Complete! ====="
echo ""
echo "Next steps:"
echo "  1. Generate sample data: cd sample-data/scripts && python3 generate_sample_data.py"
echo "  2. Run local stack: ./scripts/run-local.sh"
echo "  3. Open frontend: http://localhost:5173"
echo "  4. Open API docs: http://localhost:8000/docs"
echo ""
