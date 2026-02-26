"""Tests for CAN reader implementations."""

import tempfile
from pathlib import Path

import cantools
import pytest

from src.can_reader import CANFrame, SimulatedCANReader


@pytest.fixture
def sample_dbc():
    """Create a minimal sample DBC file."""
    dbc_content = """VERSION ""

NS_ :
    NS_DESC_
    CM_
    BA_DEF_
    BA_
    VAL_
    CAT_DEF_
    CAT_
    FILTER
    BA_DEF_DEF_
    EV_DATA_
    ENVVAR_DATA_
    SGTYPE_
    SGTYPE_VAL_
    BA_DEF_SGTYPE_
    BA_SGTYPE_
    SIG_TYPE_REF_
    VAL_TABLE_
    SIG_GROUP_
    SIG_VALTYPE_
    SIGTYPE_VALTYPE_
    BO_TX_BU_
    BA_DEF_REL_
    BA_REL_
    BA_SGTYPE_REL_
    SG_MUL_VAL_

BS_:

BU_: TestECU

BO_ 256 TestMessage: 8 TestECU
 SG_ TestSignal : 0|16@1+ (0.1,0) [0|100] "degC" TestECU

"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.dbc', delete=False) as f:
        f.write(dbc_content)
        return f.name


def test_simulated_reader_initialization(sample_dbc):
    """Test simulated reader can load DBC file."""
    reader = SimulatedCANReader(dbc_path=sample_dbc, frequency=10)

    with reader:
        assert reader.db is not None
        assert len(reader.db.messages) == 1
        assert reader.db.messages[0].name == "TestMessage"


def test_simulated_reader_generates_frames(sample_dbc):
    """Test simulated reader generates valid CAN frames."""
    reader = SimulatedCANReader(dbc_path=sample_dbc, frequency=10, duration_sec=1)

    frames = []
    with reader:
        for frame in reader.read_frames():
            frames.append(frame)

    # Should generate at least 5 frames in 1 second at 10Hz
    assert len(frames) >= 5

    # Verify frame structure
    for frame in frames:
        assert isinstance(frame, CANFrame)
        assert isinstance(frame.timestamp, float)
        assert frame.timestamp > 0
        assert isinstance(frame.arb_id, int)
        assert 0 <= frame.arb_id <= 0x1FFFFFFF
        assert isinstance(frame.dlc, int)
        assert 0 <= frame.dlc <= 8
        assert isinstance(frame.data, bytes)
        assert len(frame.data) == frame.dlc


def test_simulated_reader_arb_ids_match_dbc(sample_dbc):
    """Test simulated frames use arbitration IDs from DBC."""
    reader = SimulatedCANReader(dbc_path=sample_dbc, frequency=10, duration_sec=0.5)

    frames = []
    with reader:
        for frame in reader.read_frames():
            frames.append(frame)

    # All frames should have arb_id=256 (TestMessage)
    assert all(frame.arb_id == 256 for frame in frames)


def test_simulated_reader_signal_generation(sample_dbc):
    """Test signal values are within DBC ranges."""
    reader = SimulatedCANReader(dbc_path=sample_dbc, frequency=10, duration_sec=0.5)

    with reader:
        db = cantools.database.load_file(sample_dbc)
        message = db.get_message_by_name("TestMessage")

        for frame in reader.read_frames():
            # Decode the frame
            decoded = message.decode(frame.data)

            # Check signal value is within range [0, 100]
            assert 0 <= decoded["TestSignal"] <= 100


def test_simulated_reader_timestamp_progression(sample_dbc):
    """Test timestamps progress monotonically."""
    reader = SimulatedCANReader(dbc_path=sample_dbc, frequency=10, duration_sec=0.5)

    timestamps = []
    with reader:
        for frame in reader.read_frames():
            timestamps.append(frame.timestamp)

    # Timestamps should be strictly increasing
    for i in range(1, len(timestamps)):
        assert timestamps[i] >= timestamps[i-1]


def test_simulated_reader_respects_duration(sample_dbc):
    """Test simulation stops after specified duration."""
    duration_sec = 1.0
    reader = SimulatedCANReader(dbc_path=sample_dbc, frequency=10, duration_sec=duration_sec)

    start_time = None
    end_time = None

    with reader:
        for frame in reader.read_frames():
            if start_time is None:
                start_time = frame.timestamp
            end_time = frame.timestamp

    # Duration should be approximately as specified (within 20% tolerance)
    actual_duration = end_time - start_time
    assert 0.8 * duration_sec <= actual_duration <= 1.2 * duration_sec


@pytest.mark.parametrize("frequency", [10, 50, 100])
def test_simulated_reader_frequency(sample_dbc, frequency):
    """Test simulation respects configured frequency."""
    duration_sec = 0.5
    reader = SimulatedCANReader(
        dbc_path=sample_dbc,
        frequency=frequency,
        duration_sec=duration_sec
    )

    frame_count = 0
    with reader:
        for _ in reader.read_frames():
            frame_count += 1

    # Expected frames = frequency * duration * num_messages
    # With tolerance for timing variations
    expected = frequency * duration_sec * 1  # 1 message in DBC
    assert 0.5 * expected <= frame_count <= 1.5 * expected
