"""
Integration tests for RealCANReader using a virtual CAN interface (vcan0).

These tests require Linux with the vcan kernel module loaded.
They do NOT require physical CAN hardware.

Setup (run once per boot):
    sudo modprobe vcan
    sudo ip link add dev vcan0 type vcan
    sudo ip link set up vcan0

The tests create and tear down vcan0 automatically if they have sudo access,
or skip gracefully if vcan0 is not available.

Run:
    pytest tests/test_real_can_vcan.py -v
"""

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import pytest

# Guard: skip entire module on non-Linux platforms
if sys.platform != "linux":
    pytest.skip("vcan tests only run on Linux", allow_module_level=True)

try:
    import can
except ImportError:
    pytest.skip("python-can not installed", allow_module_level=True)

try:
    import pyarrow.parquet as pq
except ImportError:
    pytest.skip("pyarrow not installed", allow_module_level=True)

from src.batcher import CANFrameBatcher
from src.can_reader import CANFrame, RealCANReader

VCAN_IFACE = "vcan0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vcan_available() -> bool:
    """Return True if vcan0 already exists and is UP."""
    result = subprocess.run(
        ["ip", "link", "show", VCAN_IFACE],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "UP" in result.stdout


def _setup_vcan() -> bool:
    """Try to create vcan0.  Returns True on success."""
    try:
        subprocess.run(["sudo", "modprobe", "vcan"], check=True, capture_output=True)
        subprocess.run(
            ["sudo", "ip", "link", "add", "dev", VCAN_IFACE, "type", "vcan"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["sudo", "ip", "link", "set", "up", VCAN_IFACE],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _teardown_vcan() -> None:
    """Remove vcan0 if we created it."""
    subprocess.run(
        ["sudo", "ip", "link", "delete", VCAN_IFACE],
        capture_output=True,
    )


def _send_frames(
    iface: str,
    frames: list[tuple[int, bytes]],
    delay: float = 0.01,
) -> None:
    """Send (arb_id, data) tuples to the given CAN interface."""
    bus = can.Bus(interface="socketcan", channel=iface, bitrate=500000)
    try:
        for arb_id, data in frames:
            msg = can.Message(
                arbitration_id=arb_id,
                data=data,
                is_extended_id=False,
            )
            bus.send(msg)
            time.sleep(delay)
    finally:
        bus.shutdown()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def vcan_interface():
    """Create vcan0 for the test module, tear it down afterwards."""
    already_existed = _vcan_available()
    if not already_existed:
        if not _setup_vcan():
            pytest.skip(
                "Cannot create vcan0 — run: sudo modprobe vcan && "
                "sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0"
            )
    yield VCAN_IFACE
    if not already_existed:
        _teardown_vcan()


def _make_config(iface: str = VCAN_IFACE) -> dict:
    """Build a minimal config dict for RealCANReader."""
    return {
        "can": {
            "interface": "socketcan",
            "channel": iface,
            "bitrate": 500000,
            "fd": False,
            "receive_own_messages": True,  # echo TX so we can receive what we send
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRealCANReaderWithVCAN:
    """Integration tests using the virtual CAN interface."""

    def test_connect_and_disconnect(self):
        """RealCANReader connects to vcan0 and disconnects cleanly."""
        reader = RealCANReader(_make_config())
        assert reader.connect(), "connect() should return True for vcan0"
        reader.close()
        assert reader.bus is None

    def test_receive_known_frames(self):
        """Frames sent on vcan0 are received by the reader."""
        KNOWN_FRAMES = [
            (0x1A0, bytes([0x01, 0x02, 0x03, 0x04])),
            (0x2B0, bytes([0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x00, 0x00, 0x00])),
            (0x3C0, bytes([0xFF] * 8)),
        ]

        received: list[CANFrame] = []
        stop_flag = threading.Event()

        config = _make_config()
        reader = RealCANReader(config)

        def read_worker():
            with reader:
                for frame in reader.read_frames():
                    received.append(frame)
                    if len(received) >= len(KNOWN_FRAMES):
                        reader.stop()
                        break
                    if stop_flag.is_set():
                        reader.stop()
                        break

        read_thread = threading.Thread(target=read_worker, daemon=True)
        read_thread.start()

        # Give the reader time to connect
        time.sleep(0.2)

        # Send known frames
        _send_frames(VCAN_IFACE, KNOWN_FRAMES)

        # Wait up to 3 s for all frames to be received
        read_thread.join(timeout=3.0)
        stop_flag.set()
        reader.stop()

        assert len(received) >= len(KNOWN_FRAMES), (
            f"Expected at least {len(KNOWN_FRAMES)} frames, got {len(received)}"
        )

        received_ids = {f.arb_id for f in received}
        for arb_id, _ in KNOWN_FRAMES:
            assert arb_id in received_ids, f"arb_id 0x{arb_id:03X} not received"

    def test_frame_data_integrity(self):
        """Frame data bytes are received unmodified."""
        TEST_DATA = bytes([0x12, 0x34, 0x56, 0x78, 0xAB, 0xCD, 0xEF, 0x00])
        TEST_ARB_ID = 0x555

        received: list[CANFrame] = []
        reader = RealCANReader(_make_config())

        def read_worker():
            with reader:
                for frame in reader.read_frames():
                    if frame.arb_id == TEST_ARB_ID:
                        received.append(frame)
                        reader.stop()
                        break

        thread = threading.Thread(target=read_worker, daemon=True)
        thread.start()
        time.sleep(0.2)

        _send_frames(VCAN_IFACE, [(TEST_ARB_ID, TEST_DATA)])
        thread.join(timeout=3.0)
        reader.stop()

        assert len(received) == 1
        assert received[0].data == TEST_DATA
        assert received[0].dlc == len(TEST_DATA)

    def test_stats_accumulate(self):
        """get_stats() returns increasing frame count as frames arrive."""
        FRAME_COUNT = 20
        reader = RealCANReader(_make_config())
        received = 0
        stop_flag = threading.Event()

        def read_worker():
            nonlocal received
            with reader:
                for frame in reader.read_frames():
                    received += 1
                    if received >= FRAME_COUNT or stop_flag.is_set():
                        reader.stop()
                        break

        thread = threading.Thread(target=read_worker, daemon=True)
        thread.start()
        time.sleep(0.2)

        frames = [(0x100 + i, bytes([i] * 4)) for i in range(FRAME_COUNT)]
        _send_frames(VCAN_IFACE, frames, delay=0.005)
        thread.join(timeout=5.0)
        stop_flag.set()
        reader.stop()

        stats = reader.get_stats()
        assert stats["frames"] >= FRAME_COUNT, (
            f"Expected >= {FRAME_COUNT} frames in stats, got {stats['frames']}"
        )
        assert "frames_per_sec" in stats
        assert stats["errors"] == 0

    def test_stop_breaks_read_loop(self):
        """Calling stop() terminates the read_frames generator promptly."""
        reader = RealCANReader(_make_config())
        loop_ran = threading.Event()
        stopped = threading.Event()

        def read_worker():
            with reader:
                for _ in reader.read_frames():
                    loop_ran.set()
                    break  # stop after first frame
            stopped.set()

        thread = threading.Thread(target=read_worker, daemon=True)
        thread.start()
        time.sleep(0.2)

        # Send one frame to trigger the loop
        _send_frames(VCAN_IFACE, [(0x7FF, b"\x00")], delay=0)
        reader.stop()
        stopped.wait(timeout=3.0)

        assert stopped.is_set(), "read loop did not stop after stop() was called"

    def test_context_manager(self):
        """RealCANReader works as a context manager."""
        with RealCANReader(_make_config()) as reader:
            assert reader.bus is not None or reader.connect()
        # After context exit, bus should be closed
        assert reader.bus is None


class TestBatcherWithVCAN:
    """End-to-end: RealCANReader -> CANFrameBatcher -> Parquet files."""

    def test_parquet_written_with_correct_schema(self, tmp_path: Path):
        """Frames from vcan0 are batched and written as valid Parquet."""
        BATCH_FRAMES = 30

        config = _make_config()
        reader = RealCANReader(config)
        batcher = CANFrameBatcher(
            vehicle_id="TEST_VEH",
            window_sec=60,   # large window — we'll flush manually
            max_frames=BATCH_FRAMES,  # flush after BATCH_FRAMES frames
            output_dir=str(tmp_path),
        )

        parquet_paths: list[Path] = []
        stop_flag = threading.Event()

        def capture_worker():
            with reader:
                for frame in reader.read_frames():
                    result = batcher.add_frame(frame)
                    if result is not None:
                        parquet_paths.append(result)
                        reader.stop()
                        break
                    if stop_flag.is_set():
                        reader.stop()
                        break

        thread = threading.Thread(target=capture_worker, daemon=True)
        thread.start()
        time.sleep(0.2)

        # Send enough frames to trigger a batch flush
        frames = [(0x200 + i % 8, bytes([i % 256] * 8)) for i in range(BATCH_FRAMES + 5)]
        _send_frames(VCAN_IFACE, frames, delay=0.005)

        thread.join(timeout=10.0)
        stop_flag.set()
        reader.stop()

        # Flush any remaining frames
        remaining = batcher.flush()
        if remaining:
            parquet_paths.append(remaining)

        assert len(parquet_paths) >= 1, "No Parquet file was written"

        # Validate schema
        table = pq.read_table(str(parquet_paths[0]))
        required_cols = {"timestamp", "arb_id", "dlc", "data", "vehicle_id"}
        assert required_cols.issubset(set(table.schema.names)), (
            f"Missing columns: {required_cols - set(table.schema.names)}"
        )
        assert table.num_rows > 0

        # Check vehicle_id is propagated
        vids = set(table.column("vehicle_id").to_pylist())
        assert vids == {"TEST_VEH"}

        # Check timestamps are in nanoseconds (large positive integers)
        timestamps = table.column("timestamp").to_pylist()
        assert all(t > 0 for t in timestamps)
