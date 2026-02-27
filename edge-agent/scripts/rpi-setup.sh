#!/bin/bash
# ============================================================
# rpi-setup.sh — Raspberry Pi OS setup for CAN HAT
#
# Configures a fresh Raspberry Pi OS (Bookworm, 64-bit) with:
#   - System dependencies and kernel modules
#   - SPI interface and CAN HAT device tree overlay
#   - systemd service to bring up the CAN interface on boot
#   - Python virtual environment for the edge agent
#
# Usage:
#   sudo bash rpi-setup.sh [OPTIONS]
#
# Options:
#   --hat-type   waveshare | seeed-2ch | innomaker   (default: waveshare)
#   --bitrate    CAN bitrate in bps                  (default: 500000)
#   --canfd      Enable CAN-FD mode
#   --interface  CAN interface name                  (default: can0)
#   --skip-reboot  Skip reboot prompt at end
#
# Run as root (or with sudo). Safe to run multiple times.
# ============================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOG_FILE="/var/log/rpi-can-setup.log"
PROJECT_DIR="/home/pi/telemetry-platform"
EDGE_AGENT_DIR="${PROJECT_DIR}/edge-agent"

# Detect config.txt location (Bookworm = /boot/firmware, older = /boot)
if [[ -d /boot/firmware ]]; then
    CONFIG_TXT="/boot/firmware/config.txt"
else
    CONFIG_TXT="/boot/config.txt"
fi

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

log()  { echo -e "${GREEN}[OK]${NC}  $*"    | tee -a "${LOG_FILE}"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"  | tee -a "${LOG_FILE}"; }
err()  { echo -e "${RED}[ERR]${NC}  $*"     | tee -a "${LOG_FILE}"; }
info() { echo -e "      $*"                 | tee -a "${LOG_FILE}"; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
HAT_TYPE="waveshare"
BITRATE="500000"
CANFD=false
INTERFACE="can0"
SKIP_REBOOT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hat-type)   HAT_TYPE="$2";  shift 2 ;;
        --bitrate)    BITRATE="$2";   shift 2 ;;
        --canfd)      CANFD=true;     shift ;;
        --interface)  INTERFACE="$2"; shift 2 ;;
        --skip-reboot) SKIP_REBOOT=true; shift ;;
        *) err "Unknown argument: $1"; exit 1 ;;
    esac
done

# Validate hat type
case "${HAT_TYPE}" in
    waveshare|seeed-2ch|innomaker) ;;
    *) err "Unknown --hat-type '${HAT_TYPE}'. Choose: waveshare, seeed-2ch, innomaker"; exit 1 ;;
esac

# ---------------------------------------------------------------------------
# Initialise log
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "${LOG_FILE}")"
echo "" >> "${LOG_FILE}"
echo "============================================================" >> "${LOG_FILE}"
echo " rpi-setup.sh started: $(date)" >> "${LOG_FILE}"
echo " hat=${HAT_TYPE} bitrate=${BITRATE} canfd=${CANFD} iface=${INTERFACE}" >> "${LOG_FILE}"
echo "============================================================" >> "${LOG_FILE}"

info ""
echo "============================================================"
echo " Raspberry Pi CAN HAT Setup"
echo "============================================================"
info " HAT type  : ${HAT_TYPE}"
info " Bitrate   : ${BITRATE} bps"
info " CAN-FD    : ${CANFD}"
info " Interface : ${INTERFACE}"
info " Log file  : ${LOG_FILE}"
echo "============================================================"
info ""

# ---------------------------------------------------------------------------
# Phase 1.1 — System updates and dependencies
# ---------------------------------------------------------------------------
info ">>> Phase 1: System dependencies"
log "Updating package lists..."
apt-get update -y >> "${LOG_FILE}" 2>&1

log "Upgrading installed packages (this may take a while)..."
apt-get upgrade -y >> "${LOG_FILE}" 2>&1

log "Installing required packages..."
apt-get install -y \
    python3-pip python3-venv python3-dev \
    can-utils git \
    build-essential libffi-dev \
    >> "${LOG_FILE}" 2>&1

log "System dependencies installed"

# ---------------------------------------------------------------------------
# Phase 1.2 — Enable SPI
# ---------------------------------------------------------------------------
info ""
info ">>> Phase 2: SPI interface"

if grep -q "^dtparam=spi=on" "${CONFIG_TXT}" 2>/dev/null; then
    log "SPI already enabled in ${CONFIG_TXT}"
else
    log "Enabling SPI in ${CONFIG_TXT}..."
    if command -v raspi-config &>/dev/null; then
        raspi-config nonint do_spi 0 >> "${LOG_FILE}" 2>&1
        log "SPI enabled via raspi-config"
    else
        echo "dtparam=spi=on" >> "${CONFIG_TXT}"
        log "SPI enabled by editing ${CONFIG_TXT} directly"
    fi
fi

# ---------------------------------------------------------------------------
# Phase 1.3 — CAN HAT device tree overlay
# ---------------------------------------------------------------------------
info ""
info ">>> Phase 3: CAN HAT overlay (${HAT_TYPE})"

REBOOT_NEEDED=false

add_overlay_if_missing() {
    local overlay_line="$1"
    if grep -qF "${overlay_line}" "${CONFIG_TXT}" 2>/dev/null; then
        log "Overlay already present: ${overlay_line}"
    else
        echo "${overlay_line}" >> "${CONFIG_TXT}"
        log "Added overlay: ${overlay_line}"
        REBOOT_NEEDED=true
    fi
}

case "${HAT_TYPE}" in
    waveshare)
        # MCP2515-based SPI CAN HAT (most common Waveshare variant)
        # NOTE: Some Waveshare HATs use an 8 MHz oscillator instead of 12 MHz.
        #       Check the crystal markings on your HAT and adjust if needed.
        add_overlay_if_missing "dtparam=spi=on"
        add_overlay_if_missing "dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25,spimaxfrequency=2000000"
        ;;
    seeed-2ch)
        # MCP2518FD-based 2-channel CAN-FD HAT from Seeed Studio
        add_overlay_if_missing "dtparam=spi=on"
        add_overlay_if_missing "dtoverlay=seeed-can-fd-hat-v2"
        ;;
    innomaker)
        # USB-based CAN adapter — auto-detected as gs_usb, no overlay needed
        log "InnoMaker USB adapter detected — no dtoverlay required"
        log "The gs_usb kernel module will be loaded automatically when plugged in"
        ;;
esac

if [[ "${REBOOT_NEEDED}" == true ]]; then
    warn "Overlay added to ${CONFIG_TXT} — reboot required for it to take effect"
fi

# ---------------------------------------------------------------------------
# Phase 1.4 — systemd service for CAN interface bring-up
# ---------------------------------------------------------------------------
info ""
info ">>> Phase 4: systemd CAN interface service"

# Build ExecStart command
if [[ "${CANFD}" == true ]]; then
    EXEC_START="/sbin/ip link set ${INTERFACE} up type can bitrate ${BITRATE} dbitrate 2000000 fd on restart-ms 100"
else
    EXEC_START="/sbin/ip link set ${INTERFACE} up type can bitrate ${BITRATE} restart-ms 100"
fi

SERVICE_FILE="/etc/systemd/system/${INTERFACE}-setup.service"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Bring up ${INTERFACE} CAN interface
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=${EXEC_START}
ExecStop=/sbin/ip link set ${INTERFACE} down

[Install]
WantedBy=multi-user.target
EOF

log "Created ${SERVICE_FILE}"

systemctl daemon-reload >> "${LOG_FILE}" 2>&1
systemctl enable "${INTERFACE}-setup.service" >> "${LOG_FILE}" 2>&1
log "Enabled ${INTERFACE}-setup.service"

# ---------------------------------------------------------------------------
# Phase 1.6 — Python venv and edge agent installation
# ---------------------------------------------------------------------------
info ""
info ">>> Phase 5: Python virtual environment"

if [[ ! -d "${EDGE_AGENT_DIR}" ]]; then
    warn "${EDGE_AGENT_DIR} not found — skipping venv setup."
    warn "Clone the repo first: git clone https://github.com/subhasisrevelectrik/telemetry-platform.git ${PROJECT_DIR}"
else
    VENV_DIR="${EDGE_AGENT_DIR}/venv"

    if [[ -d "${VENV_DIR}" ]]; then
        log "Virtual environment already exists at ${VENV_DIR}"
    else
        log "Creating virtual environment..."
        python3 -m venv "${VENV_DIR}" >> "${LOG_FILE}" 2>&1
        log "Virtual environment created"
    fi

    log "Installing/upgrading edge-agent dependencies..."
    "${VENV_DIR}/bin/pip" install --upgrade pip >> "${LOG_FILE}" 2>&1
    "${VENV_DIR}/bin/pip" install \
        "python-can[socketcan]" cantools pyarrow boto3 pyyaml pydantic pydantic-settings mangum fastapi \
        >> "${LOG_FILE}" 2>&1

    # Install the package itself in editable mode if pyproject.toml is present
    if [[ -f "${EDGE_AGENT_DIR}/pyproject.toml" ]]; then
        "${VENV_DIR}/bin/pip" install -e "${EDGE_AGENT_DIR}" >> "${LOG_FILE}" 2>&1
        log "Edge agent installed in editable mode"
    fi
fi

# ---------------------------------------------------------------------------
# Create required directories
# ---------------------------------------------------------------------------
info ""
info ">>> Phase 6: Creating data directories"
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
log "Data directories created under ${PROJECT_DIR}/data/"

# ---------------------------------------------------------------------------
# Summary and next steps
# ---------------------------------------------------------------------------
info ""
echo "============================================================"
echo " Setup complete!"
echo "============================================================"
info ""
info " NEXT STEPS:"
info ""
info " 1. Reboot the Pi for hardware overlays to take effect:"
info "      sudo reboot"
info ""
info " 2. After reboot, verify the CAN interface is UP:"
info "      ip link show ${INTERFACE}"
info "    Expected: ... UP  ... (state UP)"
info ""
info " 3. Run hardware diagnostics:"
info "      bash ${EDGE_AGENT_DIR}/scripts/can-diagnostics.sh"
info ""
info " 4. Connect CAN-H and CAN-L to the vehicle (ignition ON, engine OFF)."
info "    Test with:"
info "      candump ${INTERFACE} -n 10"
info ""
info " 5. Edit the config:"
info "      nano ${EDGE_AGENT_DIR}/config-rpi.yaml"
info "    Set vehicle_id, s3_bucket, and (if needed) dbc.path"
info ""
info " 6. Dry-run to verify everything works:"
info "      cd ${EDGE_AGENT_DIR}"
info "      source venv/bin/activate"
info "      python -m src.main --config config-rpi.yaml --dry-run"
info ""

if [[ "${SKIP_REBOOT}" == false && "${REBOOT_NEEDED}" == true ]]; then
    warn "A reboot is required for the CAN HAT overlay to take effect."
    read -r -p "Reboot now? [y/N] " answer
    if [[ "${answer}" =~ ^[Yy]$ ]]; then
        log "Rebooting..."
        reboot
    else
        warn "Remember to run: sudo reboot"
    fi
fi
