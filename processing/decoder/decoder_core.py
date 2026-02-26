"""Core CAN frame decoding logic (AWS-independent)."""

import logging
from typing import Any

import cantools
import pyarrow as pa

logger = logging.getLogger(__name__)


def decode_raw_table(table: pa.Table, dbc: cantools.database.Database) -> pa.Table:
    """
    Decode raw CAN frames to signal values.

    Args:
        table: PyArrow table with raw CAN frames
        dbc: Loaded cantools database

    Returns:
        PyArrow table with decoded signals
    """
    # Extract columns
    timestamps = table.column("timestamp").to_pylist()
    arb_ids = table.column("arb_id").to_pylist()
    data_bytes_list = table.column("data").to_pylist()
    vehicle_ids = table.column("vehicle_id").to_pylist()

    # Decode each frame
    decoded_rows: list[dict[str, Any]] = []
    decode_errors = 0
    unknown_ids = set()

    for i, (timestamp, arb_id, data_bytes, vehicle_id) in enumerate(
        zip(timestamps, arb_ids, data_bytes_list, vehicle_ids)
    ):
        try:
            # Find message by arbitration ID
            message = dbc.get_message_by_frame_id(arb_id)

            # Decode message
            try:
                decoded = message.decode(data_bytes)

                # Extract each signal
                for signal_name, value in decoded.items():
                    signal = message.get_signal_by_name(signal_name)

                    # Validate against DBC ranges
                    if value < signal.minimum or value > signal.maximum:
                        logger.warning(
                            f"Signal {signal_name} value {value} out of range "
                            f"[{signal.minimum}, {signal.maximum}]"
                        )

                    # Store decoded signal
                    decoded_rows.append({
                        "timestamp": timestamp,
                        "vehicle_id": vehicle_id,
                        "message_name": message.name,
                        "signal_name": signal_name,
                        "value": float(value),
                        "unit": signal.unit if signal.unit else "",
                    })

            except Exception as e:
                decode_errors += 1
                if decode_errors <= 10:  # Log first 10 errors
                    logger.warning(
                        f"Failed to decode message {message.name} "
                        f"(ID 0x{arb_id:X}): {e}"
                    )

        except KeyError:
            # Unknown arbitration ID
            if arb_id not in unknown_ids:
                unknown_ids.add(arb_id)
                logger.warning(f"Unknown arbitration ID: 0x{arb_id:X}")

    # Log statistics
    logger.info(
        f"Decoded {len(table)} frames -> {len(decoded_rows)} signals "
        f"({decode_errors} decode errors, {len(unknown_ids)} unknown IDs)"
    )

    if not decoded_rows:
        logger.warning("No signals decoded! Returning empty table")
        # Return empty table with correct schema
        return pa.table({
            "timestamp": pa.array([], type=pa.timestamp("ns")),
            "vehicle_id": pa.array([], type=pa.string()),
            "message_name": pa.array([], type=pa.string()),
            "signal_name": pa.array([], type=pa.string()),
            "value": pa.array([], type=pa.float64()),
            "unit": pa.array([], type=pa.string()),
        })

    # Convert to PyArrow table
    decoded_table = pa.table({
        "timestamp": pa.array([r["timestamp"] for r in decoded_rows], type=pa.timestamp("ns")),
        "vehicle_id": pa.array([r["vehicle_id"] for r in decoded_rows], type=pa.string()),
        "message_name": pa.array([r["message_name"] for r in decoded_rows], type=pa.string()),
        "signal_name": pa.array([r["signal_name"] for r in decoded_rows], type=pa.string()),
        "value": pa.array([r["value"] for r in decoded_rows], type=pa.float64()),
        "unit": pa.array([r["unit"] for r in decoded_rows], type=pa.string()),
    })

    return decoded_table


def validate_signal_ranges(
    table: pa.Table,
    dbc: cantools.database.Database
) -> dict[str, dict[str, int]]:
    """
    Validate decoded signal values against DBC ranges.

    Args:
        table: Decoded signals table
        dbc: Loaded cantools database

    Returns:
        Dictionary of validation statistics per signal
    """
    stats: dict[str, dict[str, int]] = {}

    message_names = table.column("message_name").to_pylist()
    signal_names = table.column("signal_name").to_pylist()
    values = table.column("value").to_pylist()

    for message_name, signal_name, value in zip(message_names, signal_names, values):
        key = f"{message_name}.{signal_name}"

        if key not in stats:
            stats[key] = {"total": 0, "out_of_range": 0}

        stats[key]["total"] += 1

        try:
            message = dbc.get_message_by_name(message_name)
            signal = message.get_signal_by_name(signal_name)

            if value < signal.minimum or value > signal.maximum:
                stats[key]["out_of_range"] += 1

        except Exception:
            pass  # Signal not in DBC (shouldn't happen)

    return stats
