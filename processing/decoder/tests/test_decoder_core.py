"""Tests for decoder core logic."""

import time
from pathlib import Path

import cantools
import pyarrow as pa
import pytest

from decoder_core import decode_raw_table


@pytest.fixture
def sample_dbc():
    """Load sample DBC file."""
    dbc_path = Path(__file__).parent / "fixtures" / "sample.dbc"
    return cantools.database.load_file(str(dbc_path))


@pytest.fixture
def sample_raw_table(sample_dbc):
    """Create sample raw CAN frames table."""
    message = sample_dbc.get_message_by_name("TestMessage")

    # Encode some test frames
    frames = []
    base_time = time.time()

    for i in range(10):
        data = message.encode({
            "TestSignal": 25.0 + i,
            "TestSignal2": 1000 + i * 10,
        })

        frames.append({
            "timestamp": int((base_time + i) * 1e9),
            "arb_id": message.frame_id,
            "dlc": message.length,
            "data": bytes(data),
            "vehicle_id": "TEST01",
        })

    table = pa.table({
        "timestamp": pa.array([f["timestamp"] for f in frames], type=pa.timestamp("ns")),
        "arb_id": pa.array([f["arb_id"] for f in frames], type=pa.uint32()),
        "dlc": pa.array([f["dlc"] for f in frames], type=pa.uint8()),
        "data": pa.array([f["data"] for f in frames], type=pa.binary()),
        "vehicle_id": pa.array([f["vehicle_id"] for f in frames], type=pa.string()),
    })

    return table


def test_decode_raw_table(sample_raw_table, sample_dbc):
    """Test decoding raw frames to signals."""
    decoded = decode_raw_table(sample_raw_table, sample_dbc)

    # Should have 2 signals per frame, 10 frames = 20 rows
    assert len(decoded) == 20

    # Check schema
    assert "timestamp" in decoded.column_names
    assert "vehicle_id" in decoded.column_names
    assert "message_name" in decoded.column_names
    assert "signal_name" in decoded.column_names
    assert "value" in decoded.column_names
    assert "unit" in decoded.column_names


def test_decode_preserves_timestamps(sample_raw_table, sample_dbc):
    """Test timestamps are preserved during decoding."""
    decoded = decode_raw_table(sample_raw_table, sample_dbc)

    raw_timestamps = set(sample_raw_table.column("timestamp").to_pylist())
    decoded_timestamps = set(decoded.column("timestamp").to_pylist())

    assert raw_timestamps == decoded_timestamps


def test_decode_extracts_signal_values(sample_raw_table, sample_dbc):
    """Test signal values are correctly extracted."""
    decoded = decode_raw_table(sample_raw_table, sample_dbc)

    signal_names = decoded.column("signal_name").to_pylist()
    values = decoded.column("value").to_pylist()

    # Check TestSignal values
    test_signal_values = [
        v for n, v in zip(signal_names, values) if n == "TestSignal"
    ]
    assert len(test_signal_values) == 10
    assert 25.0 <= min(test_signal_values) <= 35.0
    assert 25.0 <= max(test_signal_values) <= 35.0


def test_decode_unknown_arb_id(sample_dbc):
    """Test handling of unknown arbitration IDs."""
    # Create table with unknown arb_id
    table = pa.table({
        "timestamp": pa.array([int(time.time() * 1e9)], type=pa.timestamp("ns")),
        "arb_id": pa.array([0xFFF], type=pa.uint32()),  # Unknown ID
        "dlc": pa.array([8], type=pa.uint8()),
        "data": pa.array([b"\x00" * 8], type=pa.binary()),
        "vehicle_id": pa.array(["TEST01"], type=pa.string()),
    })

    decoded = decode_raw_table(table, sample_dbc)

    # Should return empty table (unknown ID skipped)
    assert len(decoded) == 0
