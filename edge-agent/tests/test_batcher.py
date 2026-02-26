"""Tests for CAN frame batcher."""

import tempfile
import time
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from src.batcher import CANFrameBatcher
from src.can_reader import CANFrame


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_frames():
    """Generate sample CAN frames."""
    base_time = time.time()
    frames = []
    for i in range(100):
        frame = CANFrame(
            timestamp=base_time + i * 0.01,  # 10ms intervals
            arb_id=0x100 + (i % 3),
            dlc=8,
            data=bytes([i % 256, (i*2) % 256, 0, 0, 0, 0, 0, 0]),
        )
        frames.append(frame)
    return frames


def test_batcher_initialization(temp_output_dir):
    """Test batcher initialization."""
    batcher = CANFrameBatcher(
        vehicle_id="TEST123",
        window_sec=60,
        max_frames=10000,
        output_dir=temp_output_dir,
    )

    assert batcher.vehicle_id == "TEST123"
    assert batcher.window_sec == 60
    assert batcher.max_frames == 10000
    assert batcher.output_dir.exists()


def test_batcher_creates_parquet(temp_output_dir, sample_frames):
    """Test batcher creates valid Parquet files."""
    batcher = CANFrameBatcher(
        vehicle_id="TEST123",
        window_sec=1,  # 1 second window for quick test
        output_dir=temp_output_dir,
    )

    # Add frames and trigger flush
    for frame in sample_frames[:50]:
        batcher.add_frame(frame)

    # Force flush
    output_path = batcher.flush()

    assert output_path is not None
    assert output_path.exists()
    assert output_path.suffix == ".parquet"

    # Read and verify Parquet file
    table = pq.read_table(output_path)
    assert len(table) == 50
    assert "timestamp" in table.column_names
    assert "arb_id" in table.column_names
    assert "dlc" in table.column_names
    assert "data" in table.column_names
    assert "vehicle_id" in table.column_names


def test_batcher_schema(temp_output_dir, sample_frames):
    """Test Parquet schema is correct."""
    batcher = CANFrameBatcher(
        vehicle_id="TEST123",
        output_dir=temp_output_dir,
    )

    for frame in sample_frames[:10]:
        batcher.add_frame(frame)

    output_path = batcher.flush()
    table = pq.read_table(output_path)

    # Verify schema
    assert str(table.schema.field("timestamp").type) == "timestamp[ns]"
    assert str(table.schema.field("arb_id").type) == "uint32"
    assert str(table.schema.field("dlc").type) == "uint8"
    assert str(table.schema.field("data").type) == "binary"
    assert str(table.schema.field("vehicle_id").type) == "string"


def test_batcher_window_timing(temp_output_dir):
    """Test batching window triggers flush."""
    batcher = CANFrameBatcher(
        vehicle_id="TEST123",
        window_sec=2,
        output_dir=temp_output_dir,
    )

    base_time = time.time()

    # Add frames at t=0
    for i in range(10):
        frame = CANFrame(
            timestamp=base_time + i * 0.1,
            arb_id=0x100,
            dlc=8,
            data=b"\x00\x01\x02\x03\x04\x05\x06\x07",
        )
        result = batcher.add_frame(frame)
        assert result is None  # Should not flush yet

    # Add frame at t=3 (exceeds window)
    frame = CANFrame(
        timestamp=base_time + 3.0,
        arb_id=0x100,
        dlc=8,
        data=b"\x00\x01\x02\x03\x04\x05\x06\x07",
    )
    result = batcher.add_frame(frame)

    # Should have flushed the first batch
    assert result is not None
    assert result.exists()


def test_batcher_max_frames(temp_output_dir):
    """Test max frames limit triggers flush."""
    max_frames = 50
    batcher = CANFrameBatcher(
        vehicle_id="TEST123",
        window_sec=1000,  # Very long window
        max_frames=max_frames,
        output_dir=temp_output_dir,
    )

    base_time = time.time()
    result = None

    # Add frames up to limit
    for i in range(max_frames + 1):
        frame = CANFrame(
            timestamp=base_time + i * 0.01,
            arb_id=0x100,
            dlc=8,
            data=b"\x00" * 8,
        )
        result = batcher.add_frame(frame)

        if i < max_frames - 1:
            assert result is None  # Should not flush yet
        else:
            assert result is not None  # Should flush at max_frames


def test_batcher_hive_partitioning(temp_output_dir, sample_frames):
    """Test output uses Hive partitioning."""
    batcher = CANFrameBatcher(
        vehicle_id="VIN12345",
        output_dir=temp_output_dir,
    )

    for frame in sample_frames[:10]:
        batcher.add_frame(frame)

    output_path = batcher.flush()

    # Verify path structure: vehicle_id=X/year=Y/month=M/day=D/file.parquet
    path_str = str(output_path)
    assert "vehicle_id=VIN12345" in path_str
    assert "year=" in path_str
    assert "month=" in path_str
    assert "day=" in path_str


def test_batcher_process_frames(temp_output_dir, sample_frames):
    """Test process_frames generator."""
    batcher = CANFrameBatcher(
        vehicle_id="TEST123",
        window_sec=0.5,  # Short window for testing
        output_dir=temp_output_dir,
    )

    def frame_generator():
        base_time = time.time()
        for i in range(100):
            yield CANFrame(
                timestamp=base_time + i * 0.01,
                arb_id=0x100,
                dlc=8,
                data=bytes([i % 256]) * 8,
            )

    output_paths = list(batcher.process_frames(frame_generator()))

    # Should have created at least one file
    assert len(output_paths) >= 1

    # All paths should be valid Parquet files
    for path in output_paths:
        assert path.exists()
        assert path.suffix == ".parquet"
        table = pq.read_table(path)
        assert len(table) > 0


def test_batcher_vehicle_id_in_data(temp_output_dir, sample_frames):
    """Test vehicle_id is written to each row."""
    vehicle_id = "TESTVIN123"
    batcher = CANFrameBatcher(
        vehicle_id=vehicle_id,
        output_dir=temp_output_dir,
    )

    for frame in sample_frames[:10]:
        batcher.add_frame(frame)

    output_path = batcher.flush()
    table = pq.read_table(output_path)

    # Verify all rows have correct vehicle_id
    vehicle_ids = table.column("vehicle_id").to_pylist()
    assert all(vid == vehicle_id for vid in vehicle_ids)
