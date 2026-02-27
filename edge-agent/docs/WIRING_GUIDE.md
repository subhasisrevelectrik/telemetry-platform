# CAN Bus Wiring Guide

## OBD-II to CAN HAT Connection

Most passenger vehicles (post-2008) expose an ISO 15765-4 CAN bus through the OBD-II port.

```
Vehicle OBD-II (J1962)         CAN HAT Terminal Block
──────────────────────         ──────────────────────
Pin 6  CAN-H  ─────────────── CAN-H  (or CANH)
Pin 14 CAN-L  ─────────────── CAN-L  (or CANL)
Pin 5  Signal GND ──────────── GND
```

### OBD-II Connector Pinout (J1962)

```
    ┌─────────────────────┐
    │ 1  2  3  4  5  6  7 │
    │  8  9 10 11 12 13 14 │
    └─────────────────────┘

Pin 4  = Chassis Ground
Pin 5  = Signal Ground       ← Connect to HAT GND
Pin 6  = CAN-H (ISO 15765-4) ← Connect to HAT CAN-H
Pin 14 = CAN-L (ISO 15765-4) ← Connect to HAT CAN-L
Pin 16 = Battery +12V        (use for power only with proper regulator)
```

### J1939 (Heavy-Duty Trucks — 9-pin Deutsch Connector)

```
Deutsch J1939 9-pin         CAN HAT Terminal Block
───────────────────         ──────────────────────
Pin C  CAN-H ────────────── CAN-H
Pin D  CAN-L ────────────── CAN-L
Pin A/B GND  ────────────── GND
```

---

## Termination Resistance

CAN bus requires **120 Ω termination at each end** of the bus.

- Most vehicles already have built-in 120 Ω termination at both ends of the factory harness.
- Adding the Raspberry Pi via the OBD-II port creates a **stub**, not a new bus endpoint — usually no additional termination is needed.
- If you see a high error rate (`ip -details -statistics link show can0` shows many errors), try **toggling the termination jumper** on the CAN HAT:
  - Jumper ON  → 120 Ω added between CAN-H and CAN-L
  - Jumper OFF → no termination (default for mid-bus tap)
- Diagnostic: if the error rate drops after toggling, you had an impedance mismatch.

---

## Power Supply

| Method | Recommendation |
|--------|---------------|
| OBD-II Pin 16 (+12 V) | Use only with a high-quality automotive buck converter (9–36 V input → 5 V / 3 A output) |
| Separate 12 V tap | Preferred for permanent installs |
| USB power bank | Fine for bench testing |
| Pi internal GPIO 5V pin | **Never use for automotive** — no voltage regulation or reverse polarity protection |

### Safe Shutdown Circuit
For permanent installations, wire a GPIO input to the vehicle ignition signal.
When ignition goes LOW, trigger a graceful shutdown:

```python
# Example: monitor ignition on GPIO pin 17
import RPi.GPIO as GPIO, subprocess
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(17, GPIO.FALLING,
    callback=lambda ch: subprocess.run(["sudo", "shutdown", "-h", "now"]),
    bouncetime=5000)
```

---

## Common CAN Bus Bitrates

| Vehicle Type | Bitrate |
|-------------|---------|
| OBD-II passenger cars (ISO 15765-4) | **500 kbps** |
| J1939 heavy-duty trucks | **250 kbps** |
| CAN-FD arbitration phase | **500 kbps** |
| CAN-FD data phase | **2 Mbps** |
| Body / comfort CAN | 125 or 250 kbps |
| Tesla (proprietary) | 500 kbps |

To change the bitrate, edit `can0-setup.service` **and** `config-rpi.yaml`:
```bash
# /etc/systemd/system/can0-setup.service
ExecStart=/sbin/ip link set can0 up type can bitrate 250000 restart-ms 100
```

---

## CAN HAT Selection Guide

| HAT | Chip | Interface | Max bitrate | Notes |
|-----|------|-----------|-------------|-------|
| Waveshare RS485 CAN HAT | MCP2515 | SPI | 1 Mbps | Most common, 12 MHz or 8 MHz crystal — check your board |
| Seeed 2-Ch CAN-FD Shield | MCP2518FD | SPI | 8 Mbps | CAN-FD support, two channels |
| InnoMaker USB2CAN | GS_USB | USB | 1 Mbps | Plug-and-play, no dtoverlay needed |

### Checking Crystal Frequency (Waveshare)

Look at the small silver can component on your HAT labelled "Y1" or similar.
- `12.000` or `12M` → use `oscillator=12000000` (default in rpi-setup.sh)
- `8.000` or `8M`  → change to `oscillator=8000000` in `/boot/firmware/config.txt`

---

## Quick Wiring Checklist

- [ ] CAN-H connected to HAT CAN-H terminal
- [ ] CAN-L connected to HAT CAN-L terminal
- [ ] Signal GND connected to HAT GND terminal
- [ ] CAN-H and CAN-L are NOT swapped (common mistake — no damage but causes bus errors)
- [ ] Wires are as short as practical (< 30 cm for the stub from OBD-II to Pi)
- [ ] Termination jumper position matches your topology
- [ ] Bitrate in config matches the vehicle bus bitrate
