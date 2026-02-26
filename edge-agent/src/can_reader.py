"""CAN bus reader implementations for real hardware and simulation."""

import logging
import time
from dataclasses import dataclass
from typing import Generator, Protocol

import can
import cantools

logger = logging.getLogger(__name__)


@dataclass
class CANFrame:
    """Represents a single CAN frame with timestamp."""

    timestamp: float  # Unix timestamp in seconds (with microsecond precision)
    arb_id: int  # CAN arbitration ID
    dlc: int  # Data length code (0-8)
    data: bytes  # Raw CAN data bytes


class CANReader(Protocol):
    """Protocol for CAN frame readers."""

    def read_frames(self) -> Generator[CANFrame, None, None]:
        """Yield CAN frames as they arrive."""
        ...

    def close(self) -> None:
        """Clean up resources."""
        ...


class RealCANReader:
    """Reads CAN frames from a real hardware interface."""

    def __init__(self, interface: str, channel: str, bitrate: int):
        """
        Initialize real CAN reader.

        Args:
            interface: Interface type (socketcan, pcan, etc.)
            channel: Channel name (can0, PCAN_USBBUS1, etc.)
            bitrate: CAN bus bitrate in bps
        """
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.bus: can.Bus | None = None

        logger.info(
            f"Initializing CAN reader: interface={interface}, "
            f"channel={channel}, bitrate={bitrate}"
        )

    def __enter__(self) -> "RealCANReader":
        """Context manager entry."""
        try:
            self.bus = can.Bus(
                interface=self.interface,
                channel=self.channel,
                bitrate=self.bitrate,
            )
            logger.info(f"CAN bus opened successfully on {self.channel}")
        except Exception as e:
            logger.error(f"Failed to open CAN bus: {e}")
            raise
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: type) -> None:
        """Context manager exit."""
        self.close()

    def read_frames(self) -> Generator[CANFrame, None, None]:
        """
        Read CAN frames from the bus.

        Yields:
            CANFrame objects as they arrive
        """
        if self.bus is None:
            raise RuntimeError("CAN bus not initialized. Use context manager.")

        logger.info("Starting CAN frame capture...")
        frame_count = 0

        try:
            while True:
                msg = self.bus.recv(timeout=1.0)
                if msg is not None:
                    frame = CANFrame(
                        timestamp=msg.timestamp,
                        arb_id=msg.arbitration_id,
                        dlc=msg.dlc,
                        data=bytes(msg.data),
                    )
                    frame_count += 1
                    if frame_count % 1000 == 0:
                        logger.debug(f"Captured {frame_count} frames")
                    yield frame
        except KeyboardInterrupt:
            logger.info(f"CAN capture stopped. Total frames: {frame_count}")
        except Exception as e:
            logger.error(f"Error reading CAN frame: {e}")
            raise

    def close(self) -> None:
        """Close the CAN bus connection."""
        if self.bus is not None:
            self.bus.shutdown()
            logger.info("CAN bus closed")


class SimulatedCANReader:
    """Simulates CAN frames using a DBC file to generate realistic data."""

    def __init__(self, dbc_path: str, frequency: int = 100, duration_sec: float | None = None):
        """
        Initialize simulated CAN reader.

        Args:
            dbc_path: Path to DBC file
            frequency: Simulation frequency in Hz (frames per second)
            duration_sec: Optional duration to run simulation (None = infinite)
        """
        self.dbc_path = dbc_path
        self.frequency = frequency
        self.duration_sec = duration_sec
        self.db: cantools.database.Database | None = None

        logger.info(
            f"Initializing simulated CAN reader: "
            f"dbc={dbc_path}, frequency={frequency}Hz"
        )

    def __enter__(self) -> "SimulatedCANReader":
        """Context manager entry."""
        try:
            self.db = cantools.database.load_file(self.dbc_path)
            logger.info(
                f"Loaded DBC file: {len(self.db.messages)} messages, "
                f"{sum(len(msg.signals) for msg in self.db.messages)} signals"
            )
        except Exception as e:
            logger.error(f"Failed to load DBC file: {e}")
            raise
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: type) -> None:
        """Context manager exit."""
        self.close()

    def _generate_signal_value(
        self, signal: cantools.database.Signal, t: float
    ) -> float:
        """
        Generate a realistic signal value based on its characteristics.

        Args:
            signal: DBC signal definition
            t: Current simulation time in seconds

        Returns:
            Generated physical value
        """
        import math
        import random

        # Use signal name to determine pattern
        signal_name = signal.name.lower()

        # Temperature signals: slow rise with noise
        if "temp" in signal_name:
            base = (signal.minimum + signal.maximum) / 2
            rise = (signal.maximum - signal.minimum) * 0.3 * math.tanh(t / 300)
            noise = random.gauss(0, (signal.maximum - signal.minimum) * 0.02)
            return min(signal.maximum, max(signal.minimum, base + rise + noise))

        # RPM: sinusoidal with ramps
        elif "rpm" in signal_name:
            if t < 60:  # Ramp up
                base = signal.minimum + (signal.maximum - signal.minimum) * (t / 60)
            elif t < 300:  # Hold high
                base = signal.maximum * 0.8
            elif t < 360:  # Ramp down
                base = signal.maximum * 0.8 * (1 - (t - 300) / 60)
            else:  # Idle
                base = signal.minimum
            noise = random.gauss(0, signal.maximum * 0.02)
            return min(signal.maximum, max(signal.minimum, base + noise))

        # SOC: linear decrease
        elif "soc" in signal_name:
            rate = (signal.maximum - signal.minimum) / 3600  # 1 hour to empty
            value = signal.maximum - rate * t
            return max(signal.minimum, value)

        # Voltage: stable with small noise
        elif "voltage" in signal_name or "volt" in signal_name:
            base = (signal.minimum + signal.maximum) / 2 + (signal.maximum - signal.minimum) * 0.2
            noise = random.gauss(0, (signal.maximum - signal.minimum) * 0.01)
            return min(signal.maximum, max(signal.minimum, base + noise))

        # Current: correlated with RPM pattern
        elif "current" in signal_name:
            if t < 60:
                base = signal.minimum + (signal.maximum - signal.minimum) * 0.3 * (t / 60)
            elif t < 300:
                base = (signal.maximum - signal.minimum) * 0.4
            else:
                base = signal.minimum
            noise = random.gauss(0, abs(signal.maximum - signal.minimum) * 0.05)
            return min(signal.maximum, max(signal.minimum, base + noise))

        # Default: sinusoidal pattern
        else:
            mid = (signal.minimum + signal.maximum) / 2
            amplitude = (signal.maximum - signal.minimum) * 0.3
            period = 30  # 30 second period
            value = mid + amplitude * math.sin(2 * math.pi * t / period)
            noise = random.gauss(0, amplitude * 0.05)
            return min(signal.maximum, max(signal.minimum, value + noise))

    def read_frames(self) -> Generator[CANFrame, None, None]:
        """
        Generate simulated CAN frames.

        Yields:
            CANFrame objects at the configured frequency
        """
        if self.db is None:
            raise RuntimeError("DBC not loaded. Use context manager.")

        logger.info("Starting CAN frame simulation...")
        start_time = time.time()
        frame_count = 0
        sleep_interval = 1.0 / self.frequency

        try:
            while True:
                current_time = time.time()
                elapsed = current_time - start_time

                # Check duration limit
                if self.duration_sec is not None and elapsed >= self.duration_sec:
                    logger.info(
                        f"Simulation duration reached: {elapsed:.1f}s, "
                        f"{frame_count} frames"
                    )
                    break

                # Generate frames for each message in the DBC
                for message in self.db.messages:
                    # Build signal dictionary with generated values
                    signal_data = {}
                    for signal in message.signals:
                        signal_data[signal.name] = self._generate_signal_value(
                            signal, elapsed
                        )

                    # Encode message using cantools
                    try:
                        data = message.encode(signal_data)
                        frame = CANFrame(
                            timestamp=current_time,
                            arb_id=message.frame_id,
                            dlc=message.length,
                            data=bytes(data),
                        )
                        frame_count += 1
                        yield frame
                    except Exception as e:
                        logger.warning(
                            f"Failed to encode message {message.name}: {e}"
                        )

                # Log progress
                if frame_count % 1000 == 0:
                    logger.debug(
                        f"Simulated {frame_count} frames, elapsed={elapsed:.1f}s"
                    )

                # Sleep to maintain frequency
                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            logger.info(f"Simulation stopped. Total frames: {frame_count}")
        except Exception as e:
            logger.error(f"Error in simulation: {e}")
            raise

    def close(self) -> None:
        """Clean up resources."""
        logger.info("Simulation reader closed")
