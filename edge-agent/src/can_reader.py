"""CAN bus reader implementations for real hardware and simulation."""

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Generator, Optional, Protocol

import can
import cantools

logger = logging.getLogger(__name__)


@dataclass
class CANFrame:
    """Represents a single CAN frame with timestamp."""

    timestamp: float  # Unix timestamp in seconds (UTC, with microsecond precision)
    arb_id: int  # CAN arbitration ID
    dlc: int  # Data length code (0-8 for classic CAN, 0-64 for CAN-FD)
    data: bytes  # Raw CAN data bytes
    is_error: bool = False  # True if this is a CAN error frame
    is_fd: bool = False  # True if this is a CAN-FD frame
    channel: str = "can0"  # Source CAN interface name


class CANReader(Protocol):
    """Protocol for CAN frame readers."""

    def read_frames(self) -> Generator[CANFrame, None, None]:
        """Yield CAN frames as they arrive."""
        ...

    def close(self) -> None:
        """Clean up resources."""
        ...


class RealCANReader:
    """
    Reads CAN frames from real hardware (SocketCAN) with automatic reconnection,
    hardware-level filters, and per-session statistics.
    """

    def __init__(self, config: dict) -> None:
        """
        Initialize from the full configuration dict.

        Args:
            config: Full config dict; reads the ``can`` section:
                interface (str): python-can backend, e.g. "socketcan"
                channel  (str): Linux interface name, e.g. "can0"
                bitrate  (int): Bus bitrate in bps, e.g. 500000
                fd       (bool, optional): Enable CAN-FD mode (default False)
                receive_own_messages (bool, optional): Echo own TX (default False)
                filters  (list, optional): python-can filter dicts:
                    [{"can_id": 0x1A0, "can_mask": 0x7FF, "extended": False}]
        """
        can_cfg = config["can"]
        self.interface: str = can_cfg["interface"]
        self.channel: str = can_cfg["channel"]
        self.bitrate: int = can_cfg["bitrate"]
        self.fd: bool = bool(can_cfg.get("fd", False))
        self.filters: Optional[list] = can_cfg.get("filters")
        self.receive_own: bool = bool(can_cfg.get("receive_own_messages", False))

        self.bus: Optional[can.Bus] = None
        self._running: bool = False
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 30.0

        # Cumulative counters
        self._stats: dict[str, int] = {"frames": 0, "errors": 0, "bus_off": 0}

        # Rolling deque for frames-per-second calculation (last 10 s)
        self._frame_times: deque = deque()
        self._fps_window: float = 10.0

        logger.info(
            "Initializing RealCANReader: interface=%s channel=%s bitrate=%d fd=%s",
            self.interface,
            self.channel,
            self.bitrate,
            self.fd,
        )

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Open the CAN interface.

        Returns:
            True if the bus was opened successfully, False otherwise.
        """
        try:
            kwargs: dict = {
                "interface": self.interface,
                "channel": self.channel,
                "bitrate": self.bitrate,
                "receive_own_messages": self.receive_own,
                "fd": self.fd,
            }
            if self.filters:
                kwargs["can_filters"] = self.filters

            self.bus = can.Bus(**kwargs)
            self._reconnect_delay = 1.0  # reset backoff on success
            logger.info("Connected to %s at %d bps", self.channel, self.bitrate)
            return True
        except can.CanError as exc:
            logger.error("Failed to connect to %s: %s", self.channel, exc)
            return False

    def reconnect(self) -> bool:
        """
        Shut down the current bus (if any) and try to reconnect with exponential
        backoff (1 s -> 2 s -> 4 s ... up to 30 s).

        Returns:
            True if reconnection succeeded, False otherwise.
        """
        if self.bus is not None:
            try:
                self.bus.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self.bus = None

        logger.warning(
            "Reconnecting to %s in %.1f s...", self.channel, self._reconnect_delay
        )
        time.sleep(self._reconnect_delay)
        self._reconnect_delay = min(
            self._reconnect_delay * 2, self._max_reconnect_delay
        )
        return self.connect()

    # ------------------------------------------------------------------
    # Frame reading
    # ------------------------------------------------------------------

    def read_frames(self) -> Generator[CANFrame, None, None]:
        """
        Yield CAN frames from the bus indefinitely.

        Automatically reconnects on bus-off or OS errors.
        Call ``stop()`` (or close the context manager) to end the loop.
        Error frames are counted in stats but NOT yielded.
        """
        self._running = True

        if not self.connect():
            while self._running and not self.reconnect():
                pass

        while self._running:
            try:
                msg = self.bus.recv(timeout=1.0)  # type: ignore[union-attr]
                if msg is None:
                    # recv() timed out — check _running flag and loop back
                    continue

                if msg.is_error_frame:
                    self._stats["errors"] += 1
                    logger.debug("Error frame on %s: %s", self.channel, msg)
                    continue

                # Prefer hardware timestamp from SocketCAN, fall back to wall clock
                t: float = float(msg.timestamp) if msg.timestamp else time.time()

                self._stats["frames"] += 1
                self._frame_times.append(t)

                # Prune stale entries from the rolling window
                cutoff = t - self._fps_window
                while self._frame_times and self._frame_times[0] < cutoff:
                    self._frame_times.popleft()

                yield CANFrame(
                    timestamp=t,
                    arb_id=msg.arbitration_id,
                    dlc=msg.dlc,
                    data=bytes(msg.data),
                    is_error=False,
                    is_fd=bool(getattr(msg, "is_fd", False)),
                    channel=self.channel,
                )

            except can.CanOperationError as exc:
                logger.error("CAN bus-off / operation error on %s: %s", self.channel, exc)
                self._stats["bus_off"] += 1
                while self._running and not self.reconnect():
                    pass

            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error reading CAN: %s", exc)
                time.sleep(0.1)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the read loop to exit on next iteration."""
        self._running = False

    def close(self) -> None:
        """Stop reading and shut down the CAN bus."""
        self.stop()
        if self.bus is not None:
            try:
                self.bus.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self.bus = None
            logger.info("CAN bus %s closed", self.channel)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """
        Return a snapshot of current statistics.

        Returns:
            Dict with keys: frames, errors, bus_off, frames_per_sec
        """
        now = time.time()
        recent = sum(1 for t in self._frame_times if now - t <= self._fps_window)
        fps = round(recent / self._fps_window, 1)
        return {**self._stats, "frames_per_sec": fps}

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "RealCANReader":
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: object,
    ) -> None:
        self.close()


class SimulatedCANReader:
    """Simulates CAN frames using a DBC file to generate realistic data."""

    def __init__(
        self,
        dbc_path: str,
        frequency: int = 100,
        duration_sec: Optional[float] = None,
    ) -> None:
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
        self.db: Optional[cantools.database.Database] = None

        logger.info(
            "Initializing simulated CAN reader: dbc=%s frequency=%dHz",
            dbc_path,
            frequency,
        )

    def __enter__(self) -> "SimulatedCANReader":
        """Context manager entry."""
        try:
            self.db = cantools.database.load_file(self.dbc_path)
            logger.info(
                "Loaded DBC file: %d messages, %d signals",
                len(self.db.messages),
                sum(len(msg.signals) for msg in self.db.messages),
            )
        except Exception as exc:
            logger.error("Failed to load DBC file: %s", exc)
            raise
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: object,
    ) -> None:
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

        signal_name = signal.name.lower()

        # Temperature signals: slow rise with noise
        if "temp" in signal_name:
            base = (signal.minimum + signal.maximum) / 2
            rise = (signal.maximum - signal.minimum) * 0.3 * math.tanh(t / 300)
            noise = random.gauss(0, (signal.maximum - signal.minimum) * 0.02)
            return min(signal.maximum, max(signal.minimum, base + rise + noise))

        # RPM: sinusoidal with ramps
        elif "rpm" in signal_name:
            if t < 60:
                base = signal.minimum + (signal.maximum - signal.minimum) * (t / 60)
            elif t < 300:
                base = signal.maximum * 0.8
            elif t < 360:
                base = signal.maximum * 0.8 * (1 - (t - 300) / 60)
            else:
                base = signal.minimum
            noise = random.gauss(0, signal.maximum * 0.02)
            return min(signal.maximum, max(signal.minimum, base + noise))

        # SOC: linear decrease
        elif "soc" in signal_name:
            rate = (signal.maximum - signal.minimum) / 3600
            value = signal.maximum - rate * t
            return max(signal.minimum, value)

        # Voltage: stable with small noise
        elif "voltage" in signal_name or "volt" in signal_name:
            base = (
                (signal.minimum + signal.maximum) / 2
                + (signal.maximum - signal.minimum) * 0.2
            )
            noise = random.gauss(0, (signal.maximum - signal.minimum) * 0.01)
            return min(signal.maximum, max(signal.minimum, base + noise))

        # Current: correlated with RPM pattern
        elif "current" in signal_name:
            if t < 60:
                base = (
                    signal.minimum
                    + (signal.maximum - signal.minimum) * 0.3 * (t / 60)
                )
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
            period = 30.0
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

                if self.duration_sec is not None and elapsed >= self.duration_sec:
                    logger.info(
                        "Simulation duration reached: %.1f s, %d frames",
                        elapsed,
                        frame_count,
                    )
                    break

                for message in self.db.messages:
                    signal_data = {}
                    for signal in message.signals:
                        signal_data[signal.name] = self._generate_signal_value(
                            signal, elapsed
                        )

                    try:
                        data = message.encode(signal_data)
                        frame_count += 1
                        yield CANFrame(
                            timestamp=current_time,
                            arb_id=message.frame_id,
                            dlc=message.length,
                            data=bytes(data),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to encode message %s: %s", message.name, exc
                        )

                if frame_count % 1000 == 0:
                    logger.debug(
                        "Simulated %d frames, elapsed=%.1f s", frame_count, elapsed
                    )

                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            logger.info("Simulation stopped. Total frames: %d", frame_count)
        except Exception as exc:
            logger.error("Error in simulation: %s", exc)
            raise

    def close(self) -> None:
        """Clean up resources."""
        logger.info("Simulation reader closed")
