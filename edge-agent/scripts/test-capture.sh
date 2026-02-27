#!/bin/bash
# ============================================================
# test-capture.sh — Integration test using virtual CAN (vcan0)
#
# Creates a vcan0 virtual interface, generates random CAN traffic,
# runs the edge agent against it for 30 seconds, then validates
# the output Parquet files.
#
# Requires: Linux with vcan kernel module, cangen (can-utils)
# Run on Pi or any Linux machine — no real CAN hardware needed.
#
# Usage:  bash test-capture.sh
# ============================================================
set -euo pipefail

VCAN_IFACE="vcan0"
TEST_DIR="/tmp/can-test-$$"
TEST_DURATION=30
EDGE_AGENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${EDGE_AGENT_DIR}/venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $*"; ((PASS++)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $*"; ((FAIL++)); }
info() { echo "       $*"; }

cleanup() {
    echo ""
    echo "Cleaning up..."
    kill "${CANGEN_PID:-}" 2>/dev/null || true
    kill "${AGENT_PID:-}"  2>/dev/null || true
    sudo ip link set "${VCAN_IFACE}" down 2>/dev/null || true
    sudo ip link delete "${VCAN_IFACE}" 2>/dev/null || true
    rm -rf "${TEST_DIR}"
    echo "Done."
}
trap cleanup EXIT

echo ""
echo "============================================================"
echo " CAN Edge Agent Integration Test (vcan)"
echo "============================================================"
echo ""

# ---- Pre-flight --------------------------------------------------- #
if [[ ! -f "${VENV}/bin/python" ]]; then
    echo "Python venv not found at ${VENV}"
    echo "Run rpi-setup.sh or: python3 -m venv venv && pip install -e ."
    exit 1
fi

# ---- Set up virtual CAN interface --------------------------------- #
echo "Setting up ${VCAN_IFACE}..."
sudo modprobe vcan
sudo ip link add dev "${VCAN_IFACE}" type vcan
sudo ip link set up "${VCAN_IFACE}"
echo "  ${VCAN_IFACE} created"

# ---- Prepare test config ------------------------------------------ #
mkdir -p "${TEST_DIR}"/{raw,pending,archive,logs}

cat > "${TEST_DIR}/config.yaml" <<YAML
vehicle_id: "TEST_VEHICLE"

can:
  interface: "socketcan"
  channel: "${VCAN_IFACE}"
  bitrate: 500000

dbc:
  path: "${EDGE_AGENT_DIR}/../sample-data/dbc/ev_powertrain.dbc"

batch:
  interval_sec: 10
  max_frames: 50000

storage:
  data_dir: "${TEST_DIR}/raw"
  archive_dir: "${TEST_DIR}/archive"
  pending_dir: "${TEST_DIR}/pending"
  max_disk_gb: 1.0

s3:
  bucket: "test-bucket"
  region: "us-east-1"
  prefix: "raw"

upload:
  enabled: false
  max_retries: 1
  initial_backoff_sec: 1
  max_backoff_sec: 5

offline:
  check_interval_sec: 60
  max_queue_size: 10

logging:
  level: "WARNING"
  file: "${TEST_DIR}/logs/agent.log"
YAML

echo "  Test config written to ${TEST_DIR}/config.yaml"

# ---- Start cangen (random CAN traffic) ---------------------------- #
echo "Starting cangen (random CAN traffic on ${VCAN_IFACE})..."
cangen "${VCAN_IFACE}" -g 5 -I r -L r &
CANGEN_PID=$!
echo "  cangen PID: ${CANGEN_PID}"

# Give cangen a moment to start
sleep 1

# ---- Start edge agent -------------------------------------------- #
echo "Starting edge agent for ${TEST_DURATION} seconds..."
timeout "${TEST_DURATION}" \
    "${VENV}/bin/python" -m src.main \
    --config "${TEST_DIR}/config.yaml" \
    >> "${TEST_DIR}/logs/agent.log" 2>&1 &
AGENT_PID=$!
echo "  Edge agent PID: ${AGENT_PID}"

# Wait for the agent to finish (timeout will kill it)
wait "${AGENT_PID}" 2>/dev/null || true
echo "  Edge agent finished"

# Stop cangen
kill "${CANGEN_PID}" 2>/dev/null || true

# ---- Validate output ---------------------------------------------- #
echo ""
echo "=== Validation ==="

# Check Parquet files were created
PARQUET_FILES=$(find "${TEST_DIR}/raw" -name "*.parquet" 2>/dev/null | wc -l)
if [[ "${PARQUET_FILES}" -gt 0 ]]; then
    pass "${PARQUET_FILES} Parquet file(s) created"
else
    fail "No Parquet files found in ${TEST_DIR}/raw"
fi

# Validate schema using Python
if [[ "${PARQUET_FILES}" -gt 0 ]]; then
    SCHEMA_RESULT=$("${VENV}/bin/python" - <<PYEOF 2>&1
import pyarrow.parquet as pq
import pathlib, sys

files = list(pathlib.Path("${TEST_DIR}/raw").rglob("*.parquet"))
errors = []

required_cols = {"timestamp", "arb_id", "dlc", "data", "vehicle_id"}

for f in files:
    try:
        table = pq.read_table(str(f))
        missing = required_cols - set(table.schema.names)
        if missing:
            errors.append(f"{f.name}: missing columns {missing}")
        elif table.num_rows == 0:
            errors.append(f"{f.name}: empty table")
        else:
            print(f"OK {f.name}: {table.num_rows} rows, schema={table.schema.names}")
    except Exception as e:
        errors.append(f"{f.name}: {e}")

if errors:
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)
    if echo "${SCHEMA_RESULT}" | grep -q "^OK"; then
        pass "Parquet schema valid: timestamp, arb_id, dlc, data, vehicle_id"
        echo "${SCHEMA_RESULT}" | grep "^OK" | while read -r line; do
            info "${line}"
        done
    else
        fail "Parquet schema validation failed"
        echo "${SCHEMA_RESULT}"
    fi

    # Check vehicle_id is correct
    VID_RESULT=$("${VENV}/bin/python" - <<PYEOF 2>&1
import pyarrow.parquet as pq, pathlib
files = list(pathlib.Path("${TEST_DIR}/raw").rglob("*.parquet"))
t = pq.read_table(str(files[0]))
ids = t.column("vehicle_id").to_pylist()
assert all(v == "TEST_VEHICLE" for v in ids), f"Expected TEST_VEHICLE, got {set(ids)}"
print("vehicle_id correct")
PYEOF
)
    if echo "${VID_RESULT}" | grep -q "vehicle_id correct"; then
        pass "vehicle_id = TEST_VEHICLE (correct)"
    else
        fail "vehicle_id mismatch: ${VID_RESULT}"
    fi

    # Total frame count
    TOTAL_ROWS=$("${VENV}/bin/python" - <<PYEOF
import pyarrow.parquet as pq, pathlib
files = list(pathlib.Path("${TEST_DIR}/raw").rglob("*.parquet"))
total = sum(pq.read_table(str(f)).num_rows for f in files)
print(total)
PYEOF
)
    if [[ "${TOTAL_ROWS}" -gt 0 ]]; then
        pass "Total frames captured: ${TOTAL_ROWS}"
    else
        fail "No frames in Parquet files"
    fi
fi

# ---- Result ------------------------------------------------------- #
echo ""
echo "============================================================"
echo -e " Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}"
echo "============================================================"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
    echo "Agent log:"
    cat "${TEST_DIR}/logs/agent.log" | tail -30
    exit 1
fi
echo "Integration test passed!"
