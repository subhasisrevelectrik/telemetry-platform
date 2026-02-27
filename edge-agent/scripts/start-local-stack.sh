#!/bin/bash
# ============================================================
# start-local-stack.sh — Start a local-only (no AWS) capture
# and API stack on the Raspberry Pi.
#
# Starts:
#   1. Edge agent reading real CAN data  (no S3 upload)
#   2. FastAPI backend in LOCAL_MODE     (reads the Parquet files)
#
# Laptop users: open http://<pi-ip>:8000/docs to explore the API
# or point the React frontend at http://<pi-ip>:8000
# ============================================================
set -euo pipefail

PROJECT_DIR="/home/pi/telemetry-platform"
EDGE_AGENT_DIR="${PROJECT_DIR}/edge-agent"
BACKEND_DIR="${PROJECT_DIR}/backend"
DATA_DIR="${PROJECT_DIR}/data/raw"
LOG_DIR="${PROJECT_DIR}/logs"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

mkdir -p "${LOG_DIR}" "${DATA_DIR}"

# ---- Detect Pi IP address ----------------------------------------- #
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

# ---- Pre-flight checks -------------------------------------------- #
[[ -f "${EDGE_AGENT_DIR}/config-rpi.yaml" ]] \
    || err "config-rpi.yaml not found. Run rpi-setup.sh first."
[[ -f "${EDGE_AGENT_DIR}/venv/bin/python" ]] \
    || err "Python venv not found. Run rpi-setup.sh first."

# ---- Override upload.enabled to false in a temp config ------------ #
TEMP_CONFIG="/tmp/config-local.yaml"
python3 - <<PYEOF
import yaml, copy

with open("${EDGE_AGENT_DIR}/config-rpi.yaml") as f:
    cfg = yaml.safe_load(f)

# Disable S3 upload for local-only mode
if "upload" in cfg:
    cfg["upload"]["enabled"] = False
else:
    cfg["upload"] = {"enabled": False}

# Point batching output to data/raw
if "batching" in cfg:
    cfg["batching"]["output_dir"] = "${DATA_DIR}"
else:
    cfg["batch"] = cfg.get("batch", {})
    cfg["batch"]["interval_sec"] = cfg.get("batch", {}).get("interval_sec", 60)
    cfg["storage"] = cfg.get("storage", {})
    cfg["storage"]["data_dir"] = "${DATA_DIR}"

with open("${TEMP_CONFIG}", "w") as f:
    yaml.dump(cfg, f)

print("Local config written to ${TEMP_CONFIG}")
PYEOF

# ---- Start edge agent in background ------------------------------- #
echo ""
log "Starting edge agent (local mode, no upload)..."
"${EDGE_AGENT_DIR}/venv/bin/python" \
    -m src.main \
    --config "${TEMP_CONFIG}" \
    >> "${LOG_DIR}/edge-agent-local.log" 2>&1 &
EDGE_PID=$!
log "Edge agent PID: ${EDGE_PID} (logs: ${LOG_DIR}/edge-agent-local.log)"

# ---- Start FastAPI backend in LOCAL_MODE -------------------------- #
if [[ -d "${BACKEND_DIR}" ]] && [[ -f "${BACKEND_DIR}/lambda_handler.py" ]]; then
    echo ""
    log "Starting FastAPI backend in LOCAL_MODE..."

    # Install uvicorn in backend venv if not present
    BACKEND_VENV="${BACKEND_DIR}/venv"
    if [[ ! -d "${BACKEND_VENV}" ]]; then
        python3 -m venv "${BACKEND_VENV}"
        "${BACKEND_VENV}/bin/pip" install --upgrade pip -q
        "${BACKEND_VENV}/bin/pip" install fastapi uvicorn pydantic pydantic-settings pyarrow -q
    fi

    LOCAL_MODE=true \
    LOCAL_DATA_DIR="${DATA_DIR}" \
    "${BACKEND_VENV}/bin/uvicorn" \
        src.app:app \
        --host 0.0.0.0 \
        --port 8000 \
        --app-dir "${BACKEND_DIR}" \
        >> "${LOG_DIR}/backend-local.log" 2>&1 &
    BACKEND_PID=$!
    log "Backend PID: ${BACKEND_PID} (logs: ${LOG_DIR}/backend-local.log)"
else
    warn "Backend not found at ${BACKEND_DIR} — skipping backend startup."
    warn "Run the frontend/backend on your laptop and point it at this Pi's data."
    BACKEND_PID=""
fi

# ---- Print access info -------------------------------------------- #
echo ""
echo "============================================================"
echo " Local stack running"
echo "============================================================"
echo ""
echo "  Edge agent : PID ${EDGE_PID} — capturing to ${DATA_DIR}"
if [[ -n "${BACKEND_PID:-}" ]]; then
echo "  Backend    : PID ${BACKEND_PID}"
echo ""
echo "  From your laptop, open:"
echo "    API docs : http://${PI_IP}:8000/docs"
echo "    Health   : http://${PI_IP}:8000/health"
fi
echo ""
echo "  Logs:"
echo "    tail -f ${LOG_DIR}/edge-agent-local.log"
echo "    tail -f ${LOG_DIR}/backend-local.log"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

# ---- Wait and clean up -------------------------------------------- #
cleanup() {
    echo ""
    log "Stopping processes..."
    kill "${EDGE_PID}" 2>/dev/null || true
    [[ -n "${BACKEND_PID:-}" ]] && kill "${BACKEND_PID}" 2>/dev/null || true
    rm -f "${TEMP_CONFIG}"
    log "Stopped."
}
trap cleanup INT TERM

wait "${EDGE_PID}" 2>/dev/null || true
