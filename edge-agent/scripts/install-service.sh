#!/bin/bash
# ============================================================
# install-service.sh — Install and enable the telemetry-agent
# systemd service on the Raspberry Pi.
#
# Run as root (or with sudo) after rpi-setup.sh has completed.
# Safe to run multiple times.
# ============================================================
set -euo pipefail

PROJECT_DIR="/home/pi/telemetry-platform"
EDGE_AGENT_DIR="${PROJECT_DIR}/edge-agent"
SCRIPTS_DIR="${EDGE_AGENT_DIR}/scripts"
SERVICE_NAME="telemetry-agent"
SERVICE_SRC="${SCRIPTS_DIR}/${SERVICE_NAME}.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

# ---- Pre-flight checks -------------------------------------------- #
[[ -f "${SERVICE_SRC}" ]] || err "Service file not found: ${SERVICE_SRC}. Run from project directory."
[[ -f "${EDGE_AGENT_DIR}/pyproject.toml" ]] || err "Edge agent not found at ${EDGE_AGENT_DIR}"
[[ -f "${EDGE_AGENT_DIR}/config-rpi.yaml" ]] || warn "config-rpi.yaml not found — create it before starting the service"

# ---- Required directories ----------------------------------------- #
DATA_DIRS=(
    "${PROJECT_DIR}/data/raw"
    "${PROJECT_DIR}/data/pending"
    "${PROJECT_DIR}/data/archive"
    "${PROJECT_DIR}/data/decoded"
    "${PROJECT_DIR}/logs"
)
for d in "${DATA_DIRS[@]}"; do
    mkdir -p "${d}"
    chown pi:pi "${d}" 2>/dev/null || true
done
log "Data directories verified"

# ---- Install service file ----------------------------------------- #
cp "${SERVICE_SRC}" "${SERVICE_DEST}"
chmod 644 "${SERVICE_DEST}"
log "Installed ${SERVICE_DEST}"

systemctl daemon-reload
log "systemd daemon reloaded"

systemctl enable "${SERVICE_NAME}.service"
log "Service enabled (will start on next boot)"

# ---- Summary ------------------------------------------------------ #
echo ""
echo "============================================================"
echo " telemetry-agent service installed"
echo "============================================================"
echo ""
echo " Management commands:"
echo "   sudo systemctl start   ${SERVICE_NAME}"
echo "   sudo systemctl stop    ${SERVICE_NAME}"
echo "   sudo systemctl restart ${SERVICE_NAME}"
echo "   sudo systemctl status  ${SERVICE_NAME}"
echo "   journalctl -u ${SERVICE_NAME} -f"
echo ""
echo " Config file:"
echo "   ${EDGE_AGENT_DIR}/config-rpi.yaml"
echo ""
warn "Edit config-rpi.yaml (set vehicle_id, s3_bucket) before starting."
echo ""
read -r -p "Start the service now? [y/N] " answer
if [[ "${answer}" =~ ^[Yy]$ ]]; then
    systemctl start "${SERVICE_NAME}.service"
    log "Service started"
    sleep 2
    systemctl status "${SERVICE_NAME}.service" --no-pager || true
fi
