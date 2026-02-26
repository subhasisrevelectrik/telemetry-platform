#!/bin/bash
# Run all test suites

set -e

echo "===== CAN Telemetry Platform - Test Suite ====="
echo ""

FAILED=0

# Test edge-agent
echo "Testing edge-agent..."
cd edge-agent
if source venv/bin/activate && pytest tests/ -v; then
    echo "✓ edge-agent tests passed"
else
    echo "✗ edge-agent tests failed"
    FAILED=1
fi
deactivate
cd ..

echo ""

# Test processing/decoder
echo "Testing processing/decoder..."
cd processing/decoder
if source venv/bin/activate && pytest tests/ -v; then
    echo "✓ decoder tests passed"
else
    echo "✗ decoder tests failed"
    FAILED=1
fi
deactivate
cd ../..

echo ""

# Test backend
echo "Testing backend..."
cd backend
if source venv/bin/activate && pytest tests/ -v; then
    echo "✓ backend tests passed"
else
    echo "✗ backend tests failed"
    FAILED=1
fi
deactivate
cd ..

echo ""

# Test frontend
if command -v npm &> /dev/null && [ -d "frontend/node_modules" ]; then
    echo "Testing frontend..."
    cd frontend
    if npm test; then
        echo "✓ frontend tests passed"
    else
        echo "✗ frontend tests failed"
        FAILED=1
    fi
    cd ..
    echo ""
fi

# Summary
echo "===== Test Summary ====="
if [ $FAILED -eq 0 ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi
