#!/bin/bash
# ============================================================
# download-opendbc.sh — OpenDBC helper
#
# Clones or updates the commaai/opendbc repository and helps
# you find and install a DBC file for your vehicle.
#
# Usage:
#   bash download-opendbc.sh [--list] [--copy <dbc-name>]
#
# Examples:
#   bash download-opendbc.sh --list
#   bash download-opendbc.sh --copy toyota_prius_2017
# ============================================================
set -euo pipefail

OPENDBC_REPO="https://github.com/commaai/opendbc.git"
OPENDBC_DIR="/home/pi/opendbc"
PROJECT_DBC_DIR="$(cd "$(dirname "$0")/../.." && pwd)/sample-data/dbc"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

LIST_MODE=false
COPY_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list)            LIST_MODE=true; shift ;;
        --copy)            COPY_NAME="$2"; shift 2 ;;
        *) err "Unknown argument: $1. Usage: $0 [--list] [--copy <name>]" ;;
    esac
done

# ---- Clone / update opendbc --------------------------------------- #
if [[ -d "${OPENDBC_DIR}/.git" ]]; then
    log "Updating opendbc repository..."
    git -C "${OPENDBC_DIR}" pull --quiet
else
    log "Cloning opendbc from ${OPENDBC_REPO}..."
    git clone --depth 1 "${OPENDBC_REPO}" "${OPENDBC_DIR}"
fi
log "opendbc is at: ${OPENDBC_DIR}"

# ---- List mode ---------------------------------------------------- #
if [[ "${LIST_MODE}" == true ]]; then
    echo ""
    echo "Available DBC files in opendbc:"
    echo "------------------------------------------------"
    find "${OPENDBC_DIR}" -name "*.dbc" | sort | while read -r f; do
        make=$(basename "$(dirname "${f}")")
        name=$(basename "${f}" .dbc)
        echo "  ${make}/${name}"
    done
    echo ""
    echo "To install a DBC file:"
    echo "  bash download-opendbc.sh --copy <name>"
    echo ""
    echo "Example:"
    echo "  bash download-opendbc.sh --copy toyota_prius_2017"
    exit 0
fi

# ---- Copy mode ---------------------------------------------------- #
if [[ -n "${COPY_NAME}" ]]; then
    FOUND=$(find "${OPENDBC_DIR}" -name "${COPY_NAME}.dbc" 2>/dev/null | head -1)
    if [[ -z "${FOUND}" ]]; then
        err "DBC not found: ${COPY_NAME}.dbc. Run --list to see available files."
    fi

    mkdir -p "${PROJECT_DBC_DIR}"
    cp "${FOUND}" "${PROJECT_DBC_DIR}/${COPY_NAME}.dbc"
    log "Copied: ${PROJECT_DBC_DIR}/${COPY_NAME}.dbc"
    echo ""
    echo " Update config-rpi.yaml:"
    echo "   dbc:"
    echo "     path: \"${PROJECT_DBC_DIR}/${COPY_NAME}.dbc\""
    exit 0
fi

# ---- Default: show summary ---------------------------------------- #
echo ""
echo " opendbc is ready at: ${OPENDBC_DIR}"
echo " $(find "${OPENDBC_DIR}" -name "*.dbc" | wc -l) DBC files available"
echo ""
echo " Commands:"
echo "   List all DBC files:"
echo "     bash $0 --list"
echo ""
echo "   Copy a DBC file to the project:"
echo "     bash $0 --copy <name>"
echo ""
echo "   Common files to try:"
echo "     toyota_corolla_e210"
echo "     honda_civic_ex_2022_can"
echo "     bmw_e46"
echo "     ford_fiesta_st"
