#!/usr/bin/env python3
"""Generate sample CAN telemetry data with realistic drive cycle patterns."""

import argparse
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cantools
import pyarrow as pa
import pyarrow.parquet as pq


def generate_signal_value(signal_name: str, signal: cantools.database.Signal, t: float) -> float:
    """
    Generate realistic signal value based on drive cycle.

    Args:
        signal_name: Signal name
        signal: DBC signal definition
        t: Time in seconds from start

    Returns:
        Physical signal value
    """
    signal_lower = signal_name.lower()

    # Battery cell voltages: stable with small variations
    if "cell" in signal_lower and "voltage" in signal_lower:
        base = 3.7  # Nominal cell voltage
        discharge = -0.3 * (t / 600)  # Slow discharge over 10 minutes
        noise = random.gauss(0, 0.01)
        return max(signal.minimum, min(signal.maximum, base + discharge + noise))

    # Cell voltage delta: increases slightly over time
    elif "delta" in signal_lower:
        base = 5.0  # Small initial delta
        increase = (t / 600) * 15  # Gradual increase
        noise = random.gauss(0, 1.0)
        return max(signal.minimum, min(signal.maximum, base + increase + noise))

    # Pack voltage: follows SOC
    elif "pack" in signal_lower and "voltage" in signal_lower:
        soc_fraction = 1.0 - (t / 1200)  # Discharge over 20 minutes
        soc_fraction = max(0.2, soc_fraction)  # Don't go below 20%
        voltage = 300 + (400 * soc_fraction)  # 300-700V range
        noise = random.gauss(0, 2.0)
        return max(signal.minimum, min(signal.maximum, voltage + noise))

    # Pack current: follows motor power
    elif "pack" in signal_lower and "current" in signal_lower:
        if t < 60:  # Ramp up
            base = -50 - (t / 60) * 150
        elif t < 300:  # High load
            base = -200 + random.gauss(0, 20)
        elif t < 360:  # Ramp down
            base = -200 + ((t - 300) / 60) * 180
        else:  # Low load
            base = -20 + random.gauss(0, 5)
        return max(signal.minimum, min(signal.maximum, base))

    # State of charge: linear decrease
    elif "soc" in signal_lower:
        rate = 100 / 1200  # 100% to 0% in 20 minutes
        soc = 100 - (rate * t)
        return max(signal.minimum, soc)

    # Motor RPM: drive cycle pattern
    elif "rpm" in signal_lower:
        if t < 60:  # Acceleration
            base = (t / 60) * 8000
        elif t < 300:  # Highway cruise
            base = 7000 + 1000 * math.sin(2 * math.pi * t / 30)
        elif t < 360:  # Deceleration
            base = 8000 * (1 - (t - 300) / 60)
        else:  # Idle
            base = 0
        noise = random.gauss(0, 100)
        return max(signal.minimum, min(signal.maximum, base + noise))

    # Motor torque: follows RPM pattern
    elif "torque" in signal_lower:
        if t < 60:  # High torque during acceleration
            base = 200 + 100 * math.sin(2 * math.pi * t / 10)
        elif t < 300:  # Moderate torque at cruise
            base = 80 + 40 * math.sin(2 * math.pi * t / 30)
        elif t < 360:  # Regenerative braking
            base = 150 * (1 - (t - 300) / 60)
        else:  # Zero torque at idle
            base = 0
        noise = random.gauss(0, 5)
        return max(signal.minimum, min(signal.maximum, base + noise))

    # Motor power: RPM * Torque relationship
    elif "power" in signal_lower:
        if t < 60:
            base = (t / 60) * 150
        elif t < 300:
            base = 120 + 30 * math.sin(2 * math.pi * t / 30)
        elif t < 360:
            base = 150 * (1 - (t - 300) / 60)
        else:
            base = 0
        noise = random.gauss(0, 3)
        return max(signal.minimum, min(signal.maximum, base + noise))

    # Temperatures: thermal lag, gradual rise
    elif "temp" in signal_lower:
        ambient = 25.0  # Ambient temperature
        if "stator" in signal_lower:
            thermal_rise = 80 * (1 - math.exp(-t / 300))  # Slow rise to 80°C above ambient
        elif "rotor" in signal_lower:
            thermal_rise = 60 * (1 - math.exp(-t / 250))
        elif "bearing" in signal_lower:
            thermal_rise = 40 * (1 - math.exp(-t / 200))
        elif "inlet" in signal_lower:
            thermal_rise = 15 * (1 - math.exp(-t / 180))
        elif "outlet" in signal_lower:
            thermal_rise = 25 * (1 - math.exp(-t / 180))
        else:
            thermal_rise = 30 * (1 - math.exp(-t / 200))

        temp = ambient + thermal_rise
        noise = random.gauss(0, 1.0)
        return max(signal.minimum, min(signal.maximum, temp + noise))

    # Flow rate: correlates with motor power
    elif "flow" in signal_lower:
        if t < 60:
            base = 5 + (t / 60) * 10
        elif t < 300:
            base = 12 + 3 * math.sin(2 * math.pi * t / 30)
        elif t < 360:
            base = 15 * (1 - (t - 300) / 90)
        else:
            base = 5
        noise = random.gauss(0, 0.3)
        return max(signal.minimum, min(signal.maximum, base + noise))

    # Pump duty: correlates with flow rate
    elif "pump" in signal_lower or "duty" in signal_lower:
        if t < 60:
            base = 30 + (t / 60) * 40
        elif t < 300:
            base = 65 + 10 * math.sin(2 * math.pi * t / 30)
        elif t < 360:
            base = 70 * (1 - (t - 300) / 90)
        else:
            base = 30
        noise = random.gauss(0, 2)
        return max(signal.minimum, min(signal.maximum, base + noise))

    # Default: sinusoidal pattern
    else:
        mid = (signal.minimum + signal.maximum) / 2
        amplitude = (signal.maximum - signal.minimum) * 0.3
        value = mid + amplitude * math.sin(2 * math.pi * t / 60)
        noise = random.gauss(0, amplitude * 0.05)
        return max(signal.minimum, min(signal.maximum, value + noise))


def generate_raw_can_data(
    dbc_path: str,
    duration_min: int,
    vehicle_id: str,
    frequency_hz: int = 100,
) -> tuple[list[dict], list[dict]]:
    """
    Generate raw CAN frames and corresponding decoded signals.

    Args:
        dbc_path: Path to DBC file
        duration_min: Duration in minutes
        vehicle_id: Vehicle identifier
        frequency_hz: CAN frame generation frequency

    Returns:
        Tuple of (raw_frames, decoded_signals) as lists of dicts
    """
    db = cantools.database.load_file(dbc_path)
    print(f"Loaded DBC: {len(db.messages)} messages, "
          f"{sum(len(msg.signals) for msg in db.messages)} signals")

    duration_sec = duration_min * 60
    interval_sec = 1.0 / frequency_hz
    start_time = time.time()

    raw_frames = []
    decoded_signals = []

    print(f"Generating {duration_min} minutes of data at {frequency_hz} Hz...")

    for step in range(int(duration_sec / interval_sec)):
        t = step * interval_sec
        timestamp_sec = start_time + t

        # Generate frames for each message
        for message in db.messages:
            # Build signal values
            signal_data = {}
            for signal in message.signals:
                value = generate_signal_value(signal.name, signal, t)
                signal_data[signal.name] = value

            # Encode to CAN frame
            try:
                data_bytes = message.encode(signal_data)

                # Store raw frame
                raw_frames.append({
                    'timestamp': int(timestamp_sec * 1e9),  # nanoseconds
                    'arb_id': message.frame_id,
                    'dlc': message.length,
                    'data': bytes(data_bytes),
                    'vehicle_id': vehicle_id,
                })

                # Store decoded signals
                for signal_name, value in signal_data.items():
                    signal = message.get_signal_by_name(signal_name)
                    unit = signal.unit if signal.unit else ""

                    decoded_signals.append({
                        'timestamp': int(timestamp_sec * 1e9),
                        'vehicle_id': vehicle_id,
                        'message_name': message.name,
                        'signal_name': signal_name,
                        'value': float(value),
                        'unit': unit,
                    })

            except Exception as e:
                print(f"Warning: Failed to encode {message.name}: {e}")

        # Progress indicator
        if step % (frequency_hz * 60) == 0:  # Every minute
            elapsed_min = step / (frequency_hz * 60)
            print(f"  Generated {elapsed_min:.1f} / {duration_min} minutes...")

    print(f"Generated {len(raw_frames)} raw frames, {len(decoded_signals)} decoded signals")
    return raw_frames, decoded_signals


def write_parquet_files(
    raw_frames: list[dict],
    decoded_signals: list[dict],
    vehicle_id: str,
    output_dir: Path,
) -> None:
    """
    Write raw and decoded Parquet files with Hive partitioning.

    Args:
        raw_frames: List of raw frame dicts
        decoded_signals: List of decoded signal dicts
        vehicle_id: Vehicle identifier
        output_dir: Output directory
    """
    # Use first timestamp for partitioning
    first_ts_ns = raw_frames[0]['timestamp']
    dt = datetime.fromtimestamp(first_ts_ns / 1e9, tz=timezone.utc)

    # Create partition directories
    raw_partition = (
        output_dir / "raw" /
        f"vehicle_id={vehicle_id}" /
        f"year={dt.year}" /
        f"month={dt.month:02d}" /
        f"day={dt.day:02d}"
    )
    raw_partition.mkdir(parents=True, exist_ok=True)

    decoded_partition = (
        output_dir / "decoded" /
        f"vehicle_id={vehicle_id}" /
        f"year={dt.year}" /
        f"month={dt.month:02d}" /
        f"day={dt.day:02d}"
    )
    decoded_partition.mkdir(parents=True, exist_ok=True)

    # Write raw CAN frames
    raw_filename = f"{dt.strftime('%Y%m%dT%H%M%S')}Z_raw.parquet"
    raw_path = raw_partition / raw_filename

    raw_table = pa.table({
        'timestamp': pa.array([f['timestamp'] for f in raw_frames], type=pa.timestamp('ns')),
        'arb_id': pa.array([f['arb_id'] for f in raw_frames], type=pa.uint32()),
        'dlc': pa.array([f['dlc'] for f in raw_frames], type=pa.uint8()),
        'data': pa.array([f['data'] for f in raw_frames], type=pa.binary()),
        'vehicle_id': pa.array([f['vehicle_id'] for f in raw_frames], type=pa.string()),
    })

    pq.write_table(raw_table, raw_path, compression='zstd', compression_level=3)
    print(f"Wrote raw data: {raw_path} ({raw_path.stat().st_size / 1024:.1f} KB)")

    # Write decoded signals
    decoded_filename = f"{dt.strftime('%Y%m%dT%H%M%S')}Z_decoded.parquet"
    decoded_path = decoded_partition / decoded_filename

    decoded_table = pa.table({
        'timestamp': pa.array([s['timestamp'] for s in decoded_signals], type=pa.timestamp('ns')),
        'vehicle_id': pa.array([s['vehicle_id'] for s in decoded_signals], type=pa.string()),
        'message_name': pa.array([s['message_name'] for s in decoded_signals], type=pa.string()),
        'signal_name': pa.array([s['signal_name'] for s in decoded_signals], type=pa.string()),
        'value': pa.array([s['value'] for s in decoded_signals], type=pa.float64()),
        'unit': pa.array([s['unit'] for s in decoded_signals], type=pa.string()),
    })

    pq.write_table(decoded_table, decoded_path, compression='zstd', compression_level=3)
    print(f"Wrote decoded data: {decoded_path} ({decoded_path.stat().st_size / 1024:.1f} KB)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate sample CAN telemetry data with realistic drive cycle"
    )
    parser.add_argument(
        "--duration_min",
        type=int,
        default=20,
        help="Duration in minutes (default: 20)",
    )
    parser.add_argument(
        "--vehicle_id",
        type=str,
        default="VIN_TEST01",
        help="Vehicle ID (default: VIN_TEST01)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="..",
        help="Output directory (default: ..)",
    )
    parser.add_argument(
        "--frequency_hz",
        type=int,
        default=100,
        help="CAN frame frequency in Hz (default: 100)",
    )

    args = parser.parse_args()

    # Get paths
    script_dir = Path(__file__).parent
    dbc_path = script_dir.parent / "dbc" / "ev_powertrain.dbc"
    output_dir = Path(args.output_dir)

    if not dbc_path.exists():
        print(f"Error: DBC file not found: {dbc_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Generating sample data:")
    print(f"  DBC: {dbc_path}")
    print(f"  Vehicle ID: {args.vehicle_id}")
    print(f"  Duration: {args.duration_min} minutes")
    print(f"  Frequency: {args.frequency_hz} Hz")
    print(f"  Output: {output_dir}")
    print()

    # Generate data
    raw_frames, decoded_signals = generate_raw_can_data(
        dbc_path=str(dbc_path),
        duration_min=args.duration_min,
        vehicle_id=args.vehicle_id,
        frequency_hz=args.frequency_hz,
    )

    # Write Parquet files
    write_parquet_files(
        raw_frames=raw_frames,
        decoded_signals=decoded_signals,
        vehicle_id=args.vehicle_id,
        output_dir=output_dir,
    )

    print("\nSample data generation complete!")


if __name__ == "__main__":
    main()
