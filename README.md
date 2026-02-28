# CAN Bus Telemetry Platform

A complete, production-ready platform for capturing, processing, and visualizing CAN bus telemetry data from vehicles. Runs on a Raspberry Pi with a CAN HAT for real vehicle data, or on any machine in simulation mode.

**Live dashboard**: https://d3ub59umz6yzfo.cloudfront.net

## Architecture

```
CAN Bus (vehicle)
      │
      ▼
┌─────────────────────────────────┐
│  Raspberry Pi + CAN HAT         │
│  edge-agent (Python)            │
│  • SocketCAN → Parquet batches  │
│  • Auto-reconnect, HW filters   │
│  • Offline buffer               │
└──────────────┬──────────────────┘
               │ S3 PutObject (raw Parquet)
               ▼
┌─────────────────────────────────┐
│  AWS S3  (raw/)                 │
└──────────────┬──────────────────┘
               │ S3 event trigger
               ▼
┌─────────────────────────────────┐
│  Lambda Decoder                 │
│  cantools + DBC → decoded/      │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  S3 (decoded/) + Glue + Athena  │
│  Hive-partitioned data lake     │
└──────────────┬──────────────────┘
               │ SQL
               ▼
┌─────────────────────────────────┐
│  FastAPI (Lambda + Mangum)      │
│  LTTB downsampling, gap detect  │
│  API Gateway + Cognito          │
└──────────────┬──────────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────────┐
│  React Dashboard (CloudFront)   │
│  Plotly.js time-series charts   │
└─────────────────────────────────┘
```

## Features

- **Raspberry Pi CAN HAT support**: SocketCAN with auto-reconnect, hardware filters, health monitoring, systemd service for unattended capture
- **Simulation mode**: Realistic signal generation from DBC files — no hardware needed
- **Offline buffering**: Captures to local Parquet when S3 is unreachable, retries automatically
- **Serverless processing**: Lambda decodes raw CAN frames using DBC files on every S3 upload
- **Partition-pruned queries**: Athena WHERE clause uses zero-padded Hive partitions (year/month/day) to skip irrelevant S3 prefixes
- **Automatic downsampling**: LTTB algorithm reduces any query result to ≤ 10,000 display points, preserving signal shape
- **Gap detection**: Chart shows proportional time gaps between data chunks (no false connecting lines)
- **Interactive dashboard**: Plotly.js with zoom, pan, rangeslider, CSV/PNG export, per-signal statistics
- **Local development**: Complete local mode (no AWS) — Pi + laptop on the same network

## Prerequisites

| Component | Requirement |
|-----------|-------------|
| Python | 3.12+ |
| Node.js | 20+ |
| AWS CLI | Configured (for cloud deployment) |
| Raspberry Pi | Pi 4 + CAN HAT (for real vehicle capture) |
| Docker | Optional — for containerised local dev |

## Quick Start

### Option A — Laptop simulation (no hardware)

```bash
# 1. Set up dev environment
./scripts/dev-setup.sh

# 2. Generate sample data
cd sample-data/scripts && python generate_sample_data.py && cd ../..

# 3. Run full local stack
./scripts/run-local.sh
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

### Option B — Raspberry Pi with real CAN bus

```bash
# On the Pi
git clone https://github.com/subhasisrevelectrik/telemetry-platform.git
cd telemetry-platform
chmod +x edge-agent/scripts/*.sh
sudo bash edge-agent/scripts/rpi-setup.sh --hat-type waveshare --bitrate 500000
sudo reboot

# After reboot
bash edge-agent/scripts/can-diagnostics.sh
cp edge-agent/config-rpi.yaml.example edge-agent/config-rpi.yaml
# Edit: vehicle_id, s3_bucket, dbc.path
python -m src.main --config config-rpi.yaml --dry-run      # verify
python -m src.main --config config-rpi.yaml --decode-live  # verify DBC
python -m src.main --config config-rpi.yaml                # full capture
```

See [edge-agent/docs/BENCH_TEST.md](edge-agent/docs/BENCH_TEST.md) for the full step-by-step procedure.

## Project Structure

```
can-telemetry-platform/
├── edge-agent/
│   ├── src/
│   │   ├── main.py          # Entry point (--simulate, --dry-run, --decode-live)
│   │   ├── can_reader.py    # RealCANReader + SimulatedCANReader
│   │   ├── batcher.py       # Time-windowed Parquet batching
│   │   ├── uploader.py      # S3 upload with retry
│   │   └── offline_buffer.py
│   ├── scripts/
│   │   ├── rpi-setup.sh          # Pi OS setup + CAN HAT config
│   │   ├── telemetry-agent.service # systemd service
│   │   ├── install-service.sh    # Service installer
│   │   ├── can-diagnostics.sh    # Hardware pass/fail checks
│   │   ├── start-local-stack.sh  # Pi + laptop local mode
│   │   ├── test-capture.sh       # vcan0 integration test
│   │   └── download-opendbc.sh   # Community DBC helper
│   ├── docs/
│   │   ├── WIRING_GUIDE.md  # OBD-II/J1939 pinouts, termination, power
│   │   ├── DBC_GUIDE.md     # Obtaining and configuring DBC files
│   │   ├── BENCH_TEST.md    # First vehicle connection procedure
│   │   └── SAFETY.md        # Electrical and vehicle safety
│   ├── config.yaml          # Simulation / development config
│   ├── config-rpi.yaml.example  # Pi production config template
│   └── docker-compose.rpi.yml   # Pi Docker stack
├── backend/             # FastAPI REST API (Lambda + local modes)
├── frontend/            # React + TypeScript dashboard
├── processing/          # Lambda decoder (cantools DBC decode)
├── infra/               # AWS CDK infrastructure
├── sample-data/         # DBC files + sample Parquet
└── scripts/             # Dev utilities
```

## Component Details

### Edge Agent

Runs on a Raspberry Pi (or any Linux machine). Reads CAN frames, batches to Parquet, uploads to S3.

**Real hardware features (new):**
- SocketCAN auto-reconnect with exponential backoff (1 s → 30 s max)
- Hardware-level CAN filters — filter by arbitration ID in kernel, reducing CPU load
- Rolling frames/sec stats, error frame counter, bus-off event counter
- Background health monitor thread — logs fps, disk usage, and CPU temperature every 60 s
- `--dry-run` — reads frames and logs to console, no writes, no uploads
- `--decode-live` — real-time DBC decode printed to stdout for verifying signal values

**Supported CAN HATs:**

| HAT | Chip | `--hat-type` |
|-----|------|-------------|
| Waveshare RS485 CAN HAT | MCP2515 (SPI) | `waveshare` |
| Seeed 2-Ch CAN-FD Shield | MCP2518FD (SPI) | `seeed-2ch` |
| InnoMaker USB2CAN | gs_usb (USB) | `innomaker` |

```bash
# Simulation
python -m src.main --config config.yaml --simulate

# Real hardware — verify first
python -m src.main --config config-rpi.yaml --dry-run
python -m src.main --config config-rpi.yaml --decode-live

# Real hardware — full capture
python -m src.main --config config-rpi.yaml
```

**Run as systemd service (unattended):**
```bash
sudo bash edge-agent/scripts/install-service.sh
sudo systemctl start telemetry-agent
journalctl -u telemetry-agent -f
```

### Backend

FastAPI deployed as a Lambda function via Mangum. Supports both cloud (Athena) and local (Parquet) modes.

**Key optimisations:**
- Athena partition pruning — `WHERE (year,month,day) IN (...)` with zero-padded VARCHAR values matching S3 Hive paths, letting Athena skip entire S3 prefixes
- No `ORDER BY` in SQL — Python sorts after fetching, which is faster
- Fetch cap of 100k rows; LTTB reduces to `max_points` (default 10,000) before returning

**API Endpoints:**
- `GET /vehicles` — List all vehicles
- `GET /vehicles/{id}/sessions` — Recording sessions
- `GET /vehicles/{id}/messages` — CAN message names
- `GET /vehicles/{id}/messages/{msg}/signals` — Signals in a message
- `POST /vehicles/{id}/query` — Time-series data with automatic LTTB downsampling

**Run locally:**
```bash
cd backend
LOCAL_MODE=true python local_dev.py
```

**Deploy to Lambda (Windows):**
```bat
scripts\deploy_backend.bat
```

### Frontend

React + TypeScript dashboard deployed to CloudFront.

**Stack:** React 19, TypeScript 5.8, Vite 7, Tailwind CSS, Plotly.js, Zustand, TanStack Query, Axios

**Features:**
- Automatic downsampling — backend returns exactly `max_points` (10,000) LTTB-downsampled points; no manual stride or sampling controls
- Gap detection — inserts `null` at midpoints of time gaps > 5× median inter-sample interval; Plotly renders proportional visual breaks
- Plotly.js charts with zoom, pan, rangeslider, hover tooltips, CSV/PNG export
- Per-signal statistics (min, max, avg, std dev)
- Dark theme optimised for data visualisation

**Run dev server:**
```bash
cd frontend
npm install
npm run dev
```

**Deploy to CloudFront:**
```bat
cd frontend
deploy.bat
```

### Infrastructure

AWS CDK (Python) deploys the complete cloud stack:

```bash
cd infra
cdk deploy
```

Resources: S3 data lake, Lambda (decoder + API), API Gateway, Cognito, Glue crawler + catalog, Athena workgroup, CloudFront + S3 website bucket.

## Local Development (No AWS)

Two options for running locally without AWS credentials:

### 1 — Laptop only (simulation)
```bash
./scripts/run-local.sh
```
Edge agent runs `--simulate`, backend runs `LOCAL_MODE=true` reading `./data/decoded/`.

### 2 — Pi + laptop (real CAN, no cloud)
```bash
# On the Pi
bash edge-agent/scripts/start-local-stack.sh
```
Edge agent captures real CAN data to `/home/pi/telemetry-platform/data/raw/`.
FastAPI backend serves it on `:8000`.
From your laptop: `http://<pi-ip>:8000/docs`

### Docker (Pi)
```bash
docker compose -f edge-agent/docker-compose.rpi.yml up
```
Uses `network_mode: host` so the edge-agent container can access the host SocketCAN interface.

## Deployment

### Full cloud deploy
```bash
cd infra && cdk deploy
aws s3 cp sample-data/dbc/ev_powertrain.dbc s3://DATA_BUCKET/dbc/
cd frontend && npm run build && deploy.bat
```

### Backend-only update (no CDK)
```bat
scripts\deploy_backend.bat
```
Packages `backend/src/` (excluding `.env`) and calls `aws lambda update-function-code`.

## API Example

```bash
curl -X POST https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/vehicles/VIN_TEST01/query \
  -H "Content-Type: application/json" \
  -d '{
    "signals": [
      {"message_name": "BMS_PackStatus", "signal_name": "Pack_SOC"},
      {"message_name": "MotorCtrl_Status", "signal_name": "Motor_RPM"}
    ],
    "start_time": "2026-02-23T00:00:00Z",
    "end_time": "2026-02-25T00:00:00Z"
  }'
```

Returns up to 10,000 LTTB-downsampled points per signal in ~12 seconds.

## Testing

```bash
# All tests
./scripts/run-tests.sh

# Edge agent unit tests
cd edge-agent && pytest tests/

# Edge agent integration test (requires Linux + vcan kernel module)
bash edge-agent/scripts/test-capture.sh

# vcan pytest suite
cd edge-agent && pytest tests/test_real_can_vcan.py -v

# Backend tests
cd backend && pytest tests/
```

## DBC Files

The included `sample-data/dbc/ev_powertrain.dbc` is synthetic (simulation only). For real vehicles:

```bash
# Browse community DBC files (commaai/opendbc)
bash edge-agent/scripts/download-opendbc.sh --list

# Install one
bash edge-agent/scripts/download-opendbc.sh --copy toyota_corolla_e210
```

See [edge-agent/docs/DBC_GUIDE.md](edge-agent/docs/DBC_GUIDE.md) for full details.

## Performance

| Layer | Metric |
|-------|--------|
| Edge Agent | 1,000+ frames/sec; 60 s default batch window |
| Decoder Lambda | ~2 s for 10 MB Parquet |
| API Query | ~12 s for a 2-day window (Athena partition pruning + 100k row cap) |
| Frontend | Plotly.js renders 10,000 points interactively |

## Safety

Read [edge-agent/docs/SAFETY.md](edge-agent/docs/SAFETY.md) before connecting to a vehicle, especially:
- Most CAN HATs have **no galvanic isolation** — never connect to an EV high-voltage CAN bus
- The edge agent is **read-only** by default — it does not transmit CAN frames
- CAN bus data may contain personally identifiable information (GPS, VIN, driver behaviour)

## Security

- AWS credentials are **never hardcoded** — use `aws login` (IAM Identity Center) or env vars
- `.env` files are excluded from Lambda deployment packages and from git
- Pre-commit hook (`scripts/install-hooks.sh`) scans staged files for credential patterns
- S3 bucket access restricted by IAM role — Lambda has only the minimum required permissions

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `can0` interface not found | Reboot after adding dtoverlay; run `rpi-setup.sh` |
| `candump` shows no frames | Check bitrate (try 250000 for trucks); check CAN-H/L wiring |
| API returns 503 | Lambda timeout — check CloudWatch logs for duration > 29 s |
| API returns 500 TYPE_MISMATCH | Athena partition type issue — partition values must be quoted strings |
| Query returns 0 rows | Check S3 path padding: `month=02` not `month=2` |
| Dashboard shows "No data" | Check backend health: `GET /health` should return `mode: cloud` |
| `mode: local` in health response | `.env` with `LOCAL_MODE=true` bundled in Lambda zip — redeploy with `deploy_backend.bat` |

## Architecture Decisions

**Why Parquet?** Columnar format with zstd compression (~10× vs CSV), native Athena/Glue support, schema evolution.

**Why Lambda for decoding?** Event-driven on S3 upload, scales automatically, stateless (DBC cached in /tmp).

**Why Athena?** Serverless, pay-per-query, standard SQL, integrates with Glue catalog — no cluster to manage.

**Why LTTB?** Preserves visual shape of signals (peaks, troughs) deterministically. O(n) — fast enough to run per-query on Lambda.

**Why Plotly.js over uPlot?** Richer interactivity (rangeslider, multi-axis, export), better React integration, acceptable performance at 10k points.

**Why SocketCAN?** Linux kernel-native CAN support — no vendor drivers needed; works with SPI HATs (MCP2515), USB adapters (gs_usb), and virtual interfaces (vcan) with the same python-can API.

## Roadmap

- [ ] Real-time streaming with Kinesis Data Streams
- [ ] Alert rules based on signal thresholds
- [ ] Fleet-wide analytics and vehicle comparison
- [ ] OTA DBC updates pushed to edge agents
- [ ] Anomaly detection with SageMaker
- [ ] Video synchronisation with telemetry
- [ ] Mobile app for remote monitoring

---

**Built for the automotive telemetry community**
