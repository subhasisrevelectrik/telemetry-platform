#!/bin/bash
# ============================================================
# can-diagnostics.sh — CAN hardware and bus diagnostic tool
#
# Runs a series of checks and prints a colour-coded pass/fail
# summary.  Run this on the Pi after rpi-setup.sh and reboot.
#
# Usage:  bash can-diagnostics.sh [--interface can0]
# ============================================================
set -euo pipefail

INTERFACE="${1:-}"
if [[ "${INTERFACE}" == "--interface" ]]; then
    INTERFACE="$2"
elif [[ -z "${INTERFACE}" ]]; then
    INTERFACE="can0"
fi

PROJECT_DIR="/home/pi/telemetry-platform"
EDGE_AGENT_DIR="${PROJECT_DIR}/edge-agent"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $*"; ((PASS++)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $*"; ((WARN++)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $*"; ((FAIL++)); }
section() { echo ""; echo -e "${CYAN}=== $* ===${NC}"; }

echo ""
echo "============================================================"
echo " CAN Diagnostics — interface: ${INTERFACE}"
echo " $(date)"
echo "============================================================"

# ---- 1. Kernel modules -------------------------------------------- #
section "Kernel modules"
if lsmod | grep -qE "mcp251|gs_usb"; then
    pass "CAN driver module loaded: $(lsmod | grep -E 'mcp251|gs_usb' | awk '{print $1}' | head -1)"
elif lsmod | grep -q "can_dev"; then
    pass "can_dev module loaded (generic CAN driver)"
else
    fail "No CAN driver module found. Check dtoverlay in $(ls /boot/firmware/config.txt 2>/dev/null || echo /boot/config.txt)"
fi

if lsmod | grep -q "spi"; then
    pass "SPI module loaded"
else
    warn "SPI module not visible in lsmod — may be built into kernel"
fi

# ---- 2. SPI device ------------------------------------------------ #
section "SPI device"
if ls /dev/spidev* 2>/dev/null | grep -q spidev; then
    pass "SPI device found: $(ls /dev/spidev*)"
elif [[ "${INTERFACE}" == *"usb"* ]] || lsmod 2>/dev/null | grep -q "gs_usb"; then
    pass "USB CAN adapter (gs_usb) — no SPI device needed"
else
    warn "No /dev/spidev* found — SPI may not be enabled. Check: dtparam=spi=on in config.txt"
fi

# ---- 3. CAN interface existence ----------------------------------- #
section "CAN interface"
if ip link show "${INTERFACE}" &>/dev/null; then
    pass "Interface ${INTERFACE} exists"
else
    fail "Interface ${INTERFACE} not found. Verify dtoverlay and reboot."
    echo ""
    echo " Run: ip link show  (to see all interfaces)"
fi

# ---- 4. CAN interface state --------------------------------------- #
if ip link show "${INTERFACE}" &>/dev/null; then
    STATE=$(ip -details link show "${INTERFACE}" | grep -oE 'state [A-Z]+' | awk '{print $2}' || echo "UNKNOWN")
    if [[ "${STATE}" == "UP" ]]; then
        pass "Interface ${INTERFACE} is UP"
    else
        fail "Interface ${INTERFACE} state is ${STATE} (expected UP)"
        echo "       Try: sudo ip link set ${INTERFACE} up type can bitrate 500000"
        echo "       Or:  sudo systemctl start ${INTERFACE}-setup.service"
    fi
fi

# ---- 5. CAN statistics -------------------------------------------- #
section "CAN statistics"
if ip link show "${INTERFACE}" &>/dev/null; then
    STATS=$(ip -details -statistics link show "${INTERFACE}" 2>&1)
    echo "${STATS}" | grep -E "RX|TX|errors|dropped|bus_off|restart" || true

    RX_ERRORS=$(echo "${STATS}" | grep -oE 'errors [0-9]+' | head -1 | awk '{print $2}' || echo "0")
    BUS_OFF=$(echo "${STATS}" | grep -oE 'bus_off [0-9]+' | awk '{print $2}' || echo "0")

    if [[ "${BUS_OFF:-0}" -gt 0 ]]; then
        fail "Bus-off detected (${BUS_OFF} events). Check bitrate and wiring."
    elif [[ "${RX_ERRORS:-0}" -gt 100 ]]; then
        warn "High RX error count (${RX_ERRORS}). Check termination resistor and wiring."
    else
        pass "CAN statistics look normal"
    fi
fi

# ---- 6. Live traffic test ----------------------------------------- #
section "Live traffic test (5 s)"
if ip link show "${INTERFACE}" &>/dev/null && [[ "$(ip -brief link show "${INTERFACE}" | awk '{print $2}')" == "UP" ]]; then
    echo "  Attempting to capture up to 10 frames in 5 seconds..."
    CAPTURED=$(timeout 5 candump "${INTERFACE}" -n 10 2>/dev/null | wc -l || true)
    if [[ "${CAPTURED}" -ge 1 ]]; then
        pass "Received ${CAPTURED} frame(s) — CAN bus is active"
    else
        warn "No frames received in 5 s. Possible causes:"
        echo "       - Vehicle ignition is OFF"
        echo "       - Bitrate mismatch (try 250000 for J1939 trucks)"
        echo "       - CAN-H / CAN-L wiring incorrect"
        echo "       - Termination resistor missing"
    fi
else
    warn "Skipping live test — interface is not UP"
fi

# ---- 7. System health --------------------------------------------- #
section "System health"

# CPU temperature
CPU_TEMP_RAW=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "")
if [[ -n "${CPU_TEMP_RAW}" ]]; then
    CPU_TEMP=$(echo "scale=1; ${CPU_TEMP_RAW} / 1000" | bc)
    if (( $(echo "${CPU_TEMP} > 80" | bc -l) )); then
        warn "CPU temperature is high: ${CPU_TEMP}°C (consider heatsink)"
    else
        pass "CPU temperature: ${CPU_TEMP}°C"
    fi
fi

# Disk space
DISK_FREE=$(df -h "${PROJECT_DIR}" 2>/dev/null | tail -1 | awk '{print $4}' || echo "unknown")
DISK_PCT=$(df "${PROJECT_DIR}" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%' || echo "0")
if [[ "${DISK_PCT:-0}" -gt 90 ]]; then
    fail "Disk usage is ${DISK_PCT}% — only ${DISK_FREE} free. Evict old data."
elif [[ "${DISK_PCT:-0}" -gt 75 ]]; then
    warn "Disk usage is ${DISK_PCT}% — ${DISK_FREE} free"
else
    pass "Disk: ${DISK_FREE} free (${DISK_PCT}% used)"
fi

# Memory
MEM_FREE=$(free -m | grep Mem | awk '{print $7}')
if [[ "${MEM_FREE:-0}" -lt 100 ]]; then
    warn "Low available memory: ${MEM_FREE} MB"
else
    pass "Available memory: ${MEM_FREE} MB"
fi

# Python venv
if [[ -f "${EDGE_AGENT_DIR}/venv/bin/python" ]]; then
    PYVER=$("${EDGE_AGENT_DIR}/venv/bin/python" --version 2>&1)
    pass "Python venv OK: ${PYVER}"
else
    fail "Python venv not found at ${EDGE_AGENT_DIR}/venv/. Run rpi-setup.sh"
fi

# ---- Summary ------------------------------------------------------ #
echo ""
echo "============================================================"
echo -e " Results: ${GREEN}${PASS} passed${NC}  ${YELLOW}${WARN} warnings${NC}  ${RED}${FAIL} failed${NC}"
echo "============================================================"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
    echo " Fix the FAIL items above before running the edge agent."
    exit 1
elif [[ "${WARN}" -gt 0 ]]; then
    echo " Review the WARN items above — they may cause issues."
    exit 0
else
    echo " All checks passed! The Pi is ready for CAN data capture."
fi
