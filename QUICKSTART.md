# Quick Start Guide - CAN Telemetry Platform

Get the platform running locally in **5 minutes** without AWS credentials.

## Prerequisites

- **Python 3.12+**: Check with `python3 --version`
- **pip**: Package manager (usually included with Python)

## Step 1: Generate Sample Data

```bash
cd sample-data/scripts

# Install dependencies
pip install cantools pyarrow

# Generate 20 minutes of realistic CAN data
python3 generate_sample_data.py --duration_min 20

cd ../..
```

**Output**: Creates Parquet files in `sample-data/raw/` and `sample-data/decoded/`

## Step 2: Setup Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

cd ..
```

## Step 3: Copy Data

```bash
# Create data directory
mkdir -p data/decoded

# Copy sample data
cp -r sample-data/decoded/* data/decoded/
```

## Step 4: Run Backend

```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Set local mode
export LOCAL_MODE=true  # On Windows: set LOCAL_MODE=true

# Start server
python local_dev.py
```

**Output**: Backend running at http://localhost:8000

## Step 5: Test the API

Open a new terminal and try these commands:

### List Vehicles
```bash
curl http://localhost:8000/vehicles
```

**Expected Output**:
```json
[
  {
    "vehicle_id": "VIN_TEST01",
    "first_seen": "2025-02-12T14:00:00Z",
    "last_seen": "2025-02-12T14:20:00Z",
    "frame_count": 60000
  }
]
```

### Get Available Messages
```bash
curl http://localhost:8000/vehicles/VIN_TEST01/messages
```

**Expected Output**:
```json
[
  {"message_name": "BMS_CellVoltages", "sample_count": 12000},
  {"message_name": "BMS_PackStatus", "sample_count": 12000},
  {"message_name": "MotorCtrl_Status", "sample_count": 12000},
  {"message_name": "MotorCtrl_Thermal", "sample_count": 12000},
  {"message_name": "CoolantLoop", "sample_count": 12000}
]
```

### Get Signals for a Message
```bash
curl http://localhost:8000/vehicles/VIN_TEST01/messages/BMS_PackStatus/signals
```

**Expected Output**:
```json
[
  {
    "signal_name": "Pack_Current",
    "unit": "A",
    "min_value": -400.0,
    "max_value": 0.0,
    "avg_value": -125.5
  },
  {
    "signal_name": "Pack_SOC",
    "unit": "%",
    "min_value": 83.0,
    "max_value": 100.0,
    "avg_value": 91.5
  },
  {
    "signal_name": "Pack_Voltage",
    "unit": "V",
    "min_value": 580.0,
    "max_value": 700.0,
    "avg_value": 640.0
  }
]
```

### Query Time-Series Data
```bash
curl -X POST http://localhost:8000/vehicles/VIN_TEST01/query \
  -H "Content-Type: application/json" \
  -d '{
    "signals": [
      {"message_name": "BMS_PackStatus", "signal_name": "Pack_SOC"},
      {"message_name": "MotorCtrl_Status", "signal_name": "Motor_RPM"}
    ],
    "start_time": "2025-02-12T14:00:00Z",
    "end_time": "2025-02-12T14:20:00Z",
    "max_points": 100
  }'
```

**Expected Output**:
```json
{
  "signals": [
    {
      "name": "Pack_SOC",
      "unit": "%",
      "data": [
        {"t": 1707746400000, "v": 100.0},
        {"t": 1707746412000, "v": 99.8},
        ...
      ]
    },
    {
      "name": "Motor_RPM",
      "unit": "rpm",
      "data": [
        {"t": 1707746400000, "v": 0.0},
        {"t": 1707746412000, "v": 1200.5},
        ...
      ]
    }
  ],
  "query_stats": {
    "rows_scanned": 24000,
    "bytes_scanned": 245760,
    "duration_ms": 125
  }
}
```

## Step 6: Explore API Docs

Open http://localhost:8000/docs in your browser to see interactive Swagger UI.

Try the endpoints directly from the browser!

---

## Next Steps

### Option 1: Simulate CAN Data Capture

```bash
cd edge-agent
source venv/bin/activate

# Run in simulation mode
python -m src.main --config config.yaml --simulate
```

This will generate live CAN frames and write Parquet files to `./data/`

### Option 2: Process Real CAN Data

If you have a CAN interface (SocketCAN, PCAN):

1. Edit `edge-agent/config.yaml`:
   ```yaml
   can:
     interface: "socketcan"
     channel: "can0"
     bitrate: 500000
   ```

2. Run without `--simulate`:
   ```bash
   python -m src.main --config config.yaml
   ```

### Option 3: Build the Frontend

Follow instructions in [PROJECT_STATUS.md](PROJECT_STATUS.md) to create the React dashboard.

### Option 4: Deploy to AWS

1. Complete the CDK infrastructure code (see [PROJECT_STATUS.md](PROJECT_STATUS.md))
2. Run `cdk deploy` to create cloud resources
3. Update edge agent config with S3 bucket
4. Start uploading data!

---

## Troubleshooting

### "No data found"

Make sure you copied sample data:
```bash
ls data/decoded/vehicle_id=VIN_TEST01/
```

Should show: `year=2025/month=02/day=12/` directories

### "Module not found"

Activate virtual environment:
```bash
cd backend
source venv/bin/activate
```

### Backend won't start

Check Python version:
```bash
python3 --version  # Must be 3.12+
```

### Different sample data timestamps

Re-generate with current timestamp:
```bash
cd sample-data/scripts
python3 generate_sample_data.py --duration_min 20
```

---

## Architecture Overview

```
┌─────────────┐
│  CAN Bus    │ → Real vehicle data
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Edge Agent  │ → Batches to Parquet files
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Local Files │ → data/decoded/*.parquet
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Backend   │ → FastAPI queries Parquet files
│ (LOCAL MODE)│
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   HTTP API  │ → REST endpoints at :8000
└─────────────┘
```

**Local Mode**: No AWS required, perfect for development and testing!

---

## Sample Data Details

The generated sample data simulates a **20-minute electric vehicle drive cycle**:

### Drive Cycle Pattern
- **0-1 min**: Acceleration (RPM 0 → 8000)
- **1-5 min**: Highway cruise (RPM ~7000, varying)
- **5-6 min**: Deceleration (RPM 8000 → 0)
- **6-20 min**: Idle (RPM 0)

### Signals Included
- **BMS_CellVoltages**: Cell 1-3 voltages, voltage delta
- **BMS_PackStatus**: Pack voltage, current, SOC
- **MotorCtrl_Status**: RPM, torque, power
- **MotorCtrl_Thermal**: Stator, rotor, bearing temps
- **CoolantLoop**: Inlet/outlet temps, flow rate, pump duty

### Realistic Behaviors
- ✅ SOC decreases over time (100% → 83%)
- ✅ Temperatures rise with thermal lag
- ✅ Current correlates with motor load
- ✅ Cell voltage delta increases slightly
- ✅ Coolant flow follows power demand

---

**Total Time to Working System**: ~5 minutes

**No AWS Account Required**: Runs entirely locally

**Ready for Production**: Just add frontend and deploy infrastructure!
