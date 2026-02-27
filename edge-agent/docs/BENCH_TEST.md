# First Vehicle Connection — Bench Test Procedure

Follow these steps the first time you connect the Raspberry Pi to a real vehicle CAN bus.
Work through them in order; do not skip ahead.

---

## Prerequisites

- [ ] `rpi-setup.sh` has been run and the Pi has been rebooted
- [ ] `can-diagnostics.sh` passes all checks (or only warnings remain)
- [ ] `config-rpi.yaml` has been edited with the correct `vehicle_id` and `dbc.path`

---

## Step 1 — Power on Pi, verify CAN interface

```bash
ip link show can0
```

Expected output (state must be **UP**):
```
3: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP ...
    link/can
```

If state is **UNKNOWN** or **DOWN**:
```bash
sudo systemctl start can0-setup.service
sudo systemctl status can0-setup.service
```

---

## Step 2 — Run diagnostics

```bash
bash edge-agent/scripts/can-diagnostics.sh
```

All items should show **[PASS]** (warnings about no live traffic are expected before connecting to the vehicle).

---

## Step 3 — Connect to vehicle (ignition ON, engine OFF)

Wire CAN-H and CAN-L from the OBD-II port to the HAT terminal block.
See `WIRING_GUIDE.md` for pinouts.

**Always test with ignition ON and engine OFF first.**
This produces lower frame rates and makes it easier to verify the setup before dealing with full engine-running traffic.

---

## Step 4 — Verify raw frames are visible

```bash
candump can0 -t d
```

You should see a stream of frames like:
```
(0.000000) can0  7DF#0201050000000000
(0.005032) can0  7E8#0641050000000000
(0.010248) can0  1A0#3412A00000000000
```

If you see no output:
- Verify ignition is ON
- Check CAN-H and CAN-L are not swapped
- Try `candump can0 -t d --bitrate 250000` (J1939 / truck buses use 250 kbps)
- Check termination jumper on the HAT

---

## Step 5 — Dry-run (read frames, no writes)

```bash
cd edge-agent
source venv/bin/activate
python -m src.main --config config-rpi.yaml --dry-run
```

You should see frames logged to the console:
```
FRAME arb_id=0x1A0 dlc=8 data=3412a00000000000 ts=1706140234.123456
```

Press `Ctrl+C` to stop.

---

## Step 6 — Decode-live (verify DBC decoding)

```bash
python -m src.main --config config-rpi.yaml --decode-live
```

You should see decoded signal values:
```
[1706140234.123] EngineControl.EngineSpeed = 850.0 rpm
[1706140234.125] EngineControl.CoolantTemp = 88.5 degC
```

Check that values are physically plausible for ignition-on / engine-off:
- Engine RPM should be 0 (engine off)
- Temperatures should be ambient or pre-warmed
- Gear should be neutral / park

If signals show `Unknown frame` for all IDs, your DBC file may not match this vehicle.
Try a different DBC from opendbc or capture in raw mode for reverse engineering.

---

## Step 7 — Full capture (engine running)

Start the engine and run a full capture session:

```bash
python -m src.main --config config-rpi.yaml
```

After one batch interval (default 60 s), you should see:
```
INFO Batch 1 written: /home/pi/telemetry-platform/data/raw/vehicle_id=.../...parquet
```

---

## Step 8 — Verify data in dashboard

If S3 upload is enabled and Athena is configured, the data should appear in the
dashboard at https://your-cloudfront-url within a few minutes of the Lambda decoder
processing the Parquet file.

If running in local mode (`upload.enabled: false`), use the local stack:
```bash
bash edge-agent/scripts/start-local-stack.sh
```
Then open `http://<pi-ip>:8000/docs` from your laptop.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ip link` shows DOWN | can0-setup.service not started | `sudo systemctl start can0-setup.service` |
| `ip link` shows UP but `candump` shows nothing | Bitrate mismatch | Try 250000 for trucks |
| High error count in `ip -statistics link show can0` | Termination / wiring | Toggle termination jumper |
| DBC decoding shows no messages | Wrong DBC file | Try opendbc or use `--dry-run` to check raw IDs first |
| Lambda not triggering | S3 event not configured | Check Lambda S3 trigger in AWS Console |
| Dashboard shows "no vehicles" | Lambda decode error | Check Lambda CloudWatch logs |
