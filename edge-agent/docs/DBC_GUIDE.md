# DBC File Guide

## What is a DBC File?

A **DBC (Database CAN)** file describes how to decode raw CAN bus frames into
human-readable signals.  It maps:

- CAN arbitration IDs → message names
- Bit positions and lengths → signal names, units, scaling factors

Without a DBC file, the edge agent captures raw frames (arb_id + data bytes)
which must be decoded separately.  With a DBC file you get:

```
[1706140234.123] MotorController.MotorRPM = 2350.0 rpm
[1706140234.123] BatteryManagement.StateOfCharge = 87.5 %
```

---

## Obtaining a DBC File

### Option 1 — Manufacturer-provided (OEM)
Most OEMs provide DBC files to Tier-1 suppliers and authorised partners under
NDA.  Contact your vehicle manufacturer or CAN tool vendor
(Vector Informatik, PEAK System, etc.).

### Option 2 — OpenDBC (open-source, community-maintained)
The [commaai/opendbc](https://github.com/commaai/opendbc) project hosts
community-sourced DBC files for many popular vehicles.

Install using the provided helper script:
```bash
# List all available files
bash edge-agent/scripts/download-opendbc.sh --list

# Copy a specific file into the project
bash edge-agent/scripts/download-opendbc.sh --copy toyota_corolla_e210
```

### Option 3 — Reverse engineer with SavvyCAN
1. Capture raw frames: `candump can0 -l capture.log`
2. Open `capture.log` in [SavvyCAN](https://www.savvycan.com/) (free, cross-platform)
3. Use the flow view and message comparator to identify signals
4. Export as DBC once signals are identified

---

## Configuring the DBC Path

Edit `config-rpi.yaml`:

```yaml
dbc:
  path: "/home/pi/telemetry-platform/sample-data/dbc/toyota_corolla_e210.dbc"
```

The path must be **absolute** on the Pi.

---

## Raw Capture Mode (no DBC)

Set `dbc.path` to `null` to capture raw frames without decoding.
The Parquet files will contain `arb_id` and raw `data` bytes which
can be decoded later:

```yaml
dbc:
  path: null   # raw capture — no decoding
```

To decode stored raw Parquet files later:

```python
import pyarrow.parquet as pq
import cantools

db = cantools.database.load_file("my_vehicle.dbc")
table = pq.read_table("path/to/raw.parquet")

for row in table.to_pydict()["arb_id"], table.to_pydict()["data"]:
    try:
        msg = db.get_message_by_frame_id(arb_id)
        decoded = msg.decode(data_bytes)
        print(decoded)
    except Exception:
        pass  # Frame not in DBC
```

---

## Using the Included Sample DBC

`sample-data/dbc/ev_powertrain.dbc` is a **synthetic** file created for
simulation and testing.  It does NOT match any real vehicle.  Use it to:

- Test the simulation mode: `python -m src.main --config config.yaml --simulate`
- Verify the pipeline end-to-end before connecting to a real vehicle
- Understand the Parquet → Athena → API data flow

---

## Verifying a DBC File

Use `--decode-live` to immediately verify decoded signal values look correct
before committing to a recording session:

```bash
python -m src.main --config config-rpi.yaml --decode-live
```

Example output (check that values are physically plausible):
```
[1706140234.123] EngineControl.EngineSpeed = 850.0 rpm
[1706140234.125] EngineControl.CoolantTemp = 88.5 degC
[1706140234.201] TransmissionControl.GearPosition = 0.0
```

If signals decode to nonsense values, the DBC may be for a different vehicle
variant or the bitrate may be wrong.
