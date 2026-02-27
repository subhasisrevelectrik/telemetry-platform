# Safety Notes

## Electrical Safety

### CAN Bus Voltage Levels
- The CAN bus is a **low-voltage differential signal** (typically 2.5 V ± 1 V)
- CAN-H sits at ~3.5 V (dominant) and CAN-L at ~1.5 V (dominant)
- These are safe to touch but **never short CAN-H to CAN-L** — it will cause bus errors and may damage the CAN transceiver

### High-Voltage CAN Buses (EVs)
- **Do NOT connect to the high-voltage CAN bus** found inside the HV battery pack of EVs
- Most CAN HATs have **no galvanic isolation** — connecting to a HV-side bus can destroy the Pi and cause electrocution
- Only connect to the OBD-II port (12 V chassis CAN) or the low-voltage side powertrain CAN
- If you need HV-side CAN access: use a **certified isolated CAN transceiver** (e.g., ISO1042, ADM3054) and work with qualified EV technicians

### GPIO and Level Shifting
- The Raspberry Pi GPIO operates at **3.3 V logic** — do not apply 5 V signals to GPIO pins
- All recommended CAN HATs include the necessary level-shifting CAN transceiver (MCP2551, TJA1050, etc.)

### Wiring
- Always **connect signal GND** between the Pi and the vehicle CAN bus before CAN-H / CAN-L
- Double-check CAN-H and CAN-L polarity before powering on — swapping them causes bus errors but will **not damage hardware** in most cases
- Keep CAN bus wires short (< 30 cm stub from OBD-II to HAT) to minimise reflections

---

## Vehicle Safety

### Read-Only Mode
- The edge agent **does not transmit** CAN frames by default
- SocketCAN does not enable TX unless you explicitly call `bus.send()`
- Passive monitoring is read-only and will not interfere with ECU operation under normal conditions

### Never Send Frames Without Understanding the Consequences
- Sending arbitrary CAN frames can:
  - Activate actuators (throttle, brakes, windows, locks)
  - Clear or set Diagnostic Trouble Codes (DTCs)
  - Put ECUs into unexpected states
- Only use `bus.send()` in a controlled bench environment with the vehicle safely immobilised

### Diagnostic Trouble Codes (DTCs)
- Some ECUs detect additional CAN nodes and may set a U-code DTC
- This is harmless and clears itself when the Pi is disconnected
- If DTCs concern you, use a code reader to clear them after removing the Pi

### Testing Protocol
1. Always test with **ignition ON, engine OFF** first
2. Move to **engine running, vehicle stationary** once basic capture is confirmed
3. **Never drive** the vehicle while modifying or debugging the CAN capture setup

---

## Data Privacy

### Personal Data in CAN Frames
CAN bus data can contain:
- GPS coordinates (via telematics ECUs)
- Vehicle Identification Number (VIN)
- Driver behaviour patterns (acceleration, braking, speed)
- Time and date information

### Compliance
- Ensure compliance with applicable data protection regulations (GDPR, CCPA, etc.)
- The `vehicle_id` field in S3 paths should be pseudonymised where required
- Restrict S3 bucket access with appropriate IAM policies

### AWS Credential Security
- **Never commit AWS credentials** (access keys, secrets) to git — use the `.env` exclusion in `deploy_backend.bat` and the pre-commit hook
- Prefer IAM roles (EC2 / IoT Greengrass) over static credentials for production deployments
- Rotate credentials regularly if static keys must be used
- Use the principle of least privilege: the IAM user should only have `s3:PutObject` on the target bucket prefix

---

## Operational Safety Checklist

Before any vehicle connection:

- [ ] Read WIRING_GUIDE.md and verify correct pinout for your vehicle
- [ ] Verify the edge agent is in read-only mode (no `bus.send()` calls)
- [ ] Confirm bitrate matches the target CAN bus
- [ ] Run `can-diagnostics.sh` with all checks passing
- [ ] Have a way to quickly disconnect (OBD-II connector pulls out easily)
- [ ] Ensure `config-rpi.yaml` does NOT contain hardcoded AWS credentials
