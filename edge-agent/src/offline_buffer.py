"""Offline buffer management for handling network outages."""

import logging
import shutil
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class OfflineBuffer:
    """Manages offline buffering with disk space monitoring."""

    def __init__(
        self,
        pending_dir: str = "./data/pending",
        max_disk_gb: float = 10.0,
        max_queue_size: int = 100,
    ):
        """
        Initialize offline buffer.

        Args:
            pending_dir: Directory for pending files
            max_disk_gb: Maximum disk usage in GB
            max_queue_size: Maximum number of pending files
        """
        self.pending_dir = Path(pending_dir)
        self.max_disk_bytes = int(max_disk_gb * 1024 * 1024 * 1024)
        self.max_queue_size = max_queue_size

        self.pending_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized offline buffer: dir={pending_dir}, "
            f"max_disk={max_disk_gb}GB, max_queue={max_queue_size}"
        )

    def get_pending_files(self) -> List[Path]:
        """
        Get list of pending files, sorted by modification time (oldest first).

        Returns:
            List of pending file paths
        """
        files = list(self.pending_dir.glob("*.parquet"))
        files.sort(key=lambda p: p.stat().st_mtime)
        return files

    def get_disk_usage(self) -> int:
        """
        Calculate total disk usage of pending files.

        Returns:
            Total bytes used
        """
        total = 0
        for file_path in self.pending_dir.glob("*.parquet"):
            total += file_path.stat().st_size
        return total

    def check_disk_space(self) -> bool:
        """
        Check if disk usage is within limits.

        Returns:
            True if within limits, False if over
        """
        usage = self.get_disk_usage()
        usage_gb = usage / (1024 * 1024 * 1024)

        if usage > self.max_disk_bytes:
            logger.warning(
                f"Disk usage ({usage_gb:.2f} GB) exceeds limit "
                f"({self.max_disk_bytes / (1024**3):.2f} GB)"
            )
            return False

        return True

    def evict_oldest(self, count: int = 1) -> int:
        """
        Evict oldest files to free up space.

        Args:
            count: Number of files to evict

        Returns:
            Number of files actually evicted
        """
        pending_files = self.get_pending_files()

        if not pending_files:
            return 0

        evicted = 0
        for file_path in pending_files[:count]:
            try:
                size_mb = file_path.stat().st_size / (1024 * 1024)
                file_path.unlink()
                logger.warning(
                    f"Evicted old file: {file_path.name} ({size_mb:.2f} MB)"
                )
                evicted += 1
            except Exception as e:
                logger.error(f"Failed to evict file {file_path}: {e}")

        return evicted

    def enforce_limits(self) -> None:
        """Enforce disk space and queue size limits by evicting oldest files."""
        # Check queue size
        pending_files = self.get_pending_files()
        if len(pending_files) > self.max_queue_size:
            overflow = len(pending_files) - self.max_queue_size
            logger.warning(
                f"Queue size ({len(pending_files)}) exceeds limit "
                f"({self.max_queue_size}), evicting {overflow} oldest files"
            )
            self.evict_oldest(overflow)

        # Check disk space
        while not self.check_disk_space():
            pending_files = self.get_pending_files()
            if not pending_files:
                logger.error("Disk limit exceeded but no files to evict!")
                break

            # Evict oldest 10% or at least 1 file
            evict_count = max(1, len(pending_files) // 10)
            logger.warning(f"Disk limit exceeded, evicting {evict_count} files")
            evicted = self.evict_oldest(evict_count)

            if evicted == 0:
                logger.error("Failed to evict any files!")
                break

    def add_to_pending(self, file_path: Path) -> bool:
        """
        Add a file to the pending queue.

        Args:
            file_path: File to add

        Returns:
            True if successfully added, False otherwise
        """
        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            return False

        try:
            # Move to pending directory
            pending_path = self.pending_dir / file_path.name
            shutil.move(str(file_path), str(pending_path))

            logger.info(f"Added to pending queue: {pending_path.name}")

            # Enforce limits after adding
            self.enforce_limits()

            return True

        except Exception as e:
            logger.error(f"Failed to add file to pending: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Get buffer statistics.

        Returns:
            Dictionary with stats
        """
        pending_files = self.get_pending_files()
        disk_usage = self.get_disk_usage()

        return {
            "pending_count": len(pending_files),
            "disk_usage_bytes": disk_usage,
            "disk_usage_gb": disk_usage / (1024 * 1024 * 1024),
            "disk_limit_gb": self.max_disk_bytes / (1024 * 1024 * 1024),
            "queue_limit": self.max_queue_size,
            "oldest_file": pending_files[0].name if pending_files else None,
            "newest_file": pending_files[-1].name if pending_files else None,
        }
