"""Time-windowed batching of CAN frames to Parquet files."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from .can_reader import CANFrame

logger = logging.getLogger(__name__)


class CANFrameBatcher:
    """Batches CAN frames into time windows and writes Parquet files."""

    def __init__(
        self,
        vehicle_id: str,
        window_sec: int = 60,
        max_frames: int = 100000,
        output_dir: str = "./data",
    ):
        """
        Initialize batcher.

        Args:
            vehicle_id: Vehicle identifier
            window_sec: Batch window size in seconds
            max_frames: Maximum frames per batch (safety limit)
            output_dir: Directory for output files
        """
        self.vehicle_id = vehicle_id
        self.window_sec = window_sec
        self.max_frames = max_frames
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Batch state
        self.current_batch: list[CANFrame] = []
        self.batch_start_time: float | None = None

        logger.info(
            f"Initialized batcher: vehicle={vehicle_id}, "
            f"window={window_sec}s, max_frames={max_frames}"
        )

    def _get_parquet_schema(self) -> pa.Schema:
        """
        Get PyArrow schema for raw CAN data.

        Returns:
            PyArrow schema
        """
        return pa.schema([
            ("timestamp", pa.timestamp("ns")),
            ("arb_id", pa.uint32()),
            ("dlc", pa.uint8()),
            ("data", pa.binary()),
            ("vehicle_id", pa.string()),
        ])

    def _frames_to_table(self, frames: list[CANFrame]) -> pa.Table:
        """
        Convert CAN frames to PyArrow table.

        Args:
            frames: List of CAN frames

        Returns:
            PyArrow table
        """
        # Convert frames to column arrays
        timestamps = [int(f.timestamp * 1e9) for f in frames]  # Convert to nanoseconds
        arb_ids = [f.arb_id for f in frames]
        dlcs = [f.dlc for f in frames]
        data_bytes = [f.data for f in frames]
        vehicle_ids = [self.vehicle_id] * len(frames)

        # Create table
        table = pa.table({
            "timestamp": pa.array(timestamps, type=pa.timestamp("ns")),
            "arb_id": pa.array(arb_ids, type=pa.uint32()),
            "dlc": pa.array(dlcs, type=pa.uint8()),
            "data": pa.array(data_bytes, type=pa.binary()),
            "vehicle_id": pa.array(vehicle_ids, type=pa.string()),
        }, schema=self._get_parquet_schema())

        return table

    def _get_output_path(self, timestamp: float) -> Path:
        """
        Generate Hive-partitioned output path.

        Args:
            timestamp: Batch start timestamp

        Returns:
            Output file path
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        # Create Hive partitioning: vehicle_id=X/year=Y/month=M/day=D/
        partition_dir = (
            self.output_dir
            / f"vehicle_id={self.vehicle_id}"
            / f"year={dt.year}"
            / f"month={dt.month:02d}"
            / f"day={dt.day:02d}"
        )
        partition_dir.mkdir(parents=True, exist_ok=True)

        # Filename: timestamp_raw.parquet
        filename = f"{dt.strftime('%Y%m%dT%H%M%S')}Z_raw.parquet"
        return partition_dir / filename

    def _write_batch(self, frames: list[CANFrame], start_time: float) -> Path:
        """
        Write batch to Parquet file.

        Args:
            frames: List of CAN frames
            start_time: Batch start timestamp

        Returns:
            Path to written file
        """
        # Convert to table
        table = self._frames_to_table(frames)

        # Get output path
        output_path = self._get_output_path(start_time)

        # Write Parquet with compression
        pq.write_table(
            table,
            output_path,
            compression="zstd",
            compression_level=3,
            use_dictionary=True,
            write_statistics=True,
        )

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(
            f"Wrote batch: {len(frames)} frames, "
            f"{file_size_mb:.2f} MB, path={output_path}"
        )

        return output_path

    def should_flush(self, current_time: float) -> bool:
        """
        Check if current batch should be flushed.

        Args:
            current_time: Current timestamp

        Returns:
            True if batch should be flushed
        """
        if not self.current_batch:
            return False

        if self.batch_start_time is None:
            return False

        # Check window time
        if current_time - self.batch_start_time >= self.window_sec:
            return True

        # Check max frames
        if len(self.current_batch) >= self.max_frames:
            logger.warning(
                f"Batch reached max frames ({self.max_frames}), flushing early"
            )
            return True

        return False

    def add_frame(self, frame: CANFrame) -> Path | None:
        """
        Add a frame to the current batch.

        Args:
            frame: CAN frame to add

        Returns:
            Path to written file if batch was flushed, None otherwise
        """
        # Initialize batch if empty
        if not self.current_batch:
            self.batch_start_time = frame.timestamp

        # Add frame
        self.current_batch.append(frame)

        # Check if we should flush
        if self.should_flush(frame.timestamp):
            return self.flush()

        return None

    def flush(self) -> Path | None:
        """
        Flush current batch to file.

        Returns:
            Path to written file, or None if batch is empty
        """
        if not self.current_batch:
            return None

        if self.batch_start_time is None:
            logger.warning("Batch start time not set, using first frame timestamp")
            self.batch_start_time = self.current_batch[0].timestamp

        # Write batch
        output_path = self._write_batch(self.current_batch, self.batch_start_time)

        # Reset batch
        self.current_batch = []
        self.batch_start_time = None

        return output_path

    def process_frames(self, frames: Iterator[CANFrame]) -> Iterator[Path]:
        """
        Process CAN frames and yield paths to written files.

        Args:
            frames: Iterator of CAN frames

        Yields:
            Paths to written Parquet files
        """
        try:
            for frame in frames:
                output_path = self.add_frame(frame)
                if output_path is not None:
                    yield output_path

        except Exception as e:
            logger.error(f"Error processing frames: {e}")
            raise
        finally:
            # Flush any remaining frames
            final_path = self.flush()
            if final_path is not None:
                yield final_path
