"""Main entry point for CAN telemetry edge agent."""

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import NoReturn

import yaml

from .batcher import CANFrameBatcher
from .can_reader import RealCANReader, SimulatedCANReader
from .offline_buffer import OfflineBuffer
from .uploader import S3Uploader

# Global flag for graceful shutdown
shutdown_event = threading.Event()


def signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals."""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


def setup_logging(config: dict) -> None:
    """
    Configure logging from config.

    Args:
        config: Configuration dictionary
    """
    log_config = config.get("logging", {})
    level = log_config.get("level", "INFO")
    format_str = log_config.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_file = log_config.get("file")

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level),
        format=format_str,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(format_str))
        logging.getLogger().addHandler(file_handler)


def load_config(config_path: str) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def retry_pending_worker(uploader: S3Uploader, interval_sec: int) -> None:
    """
    Background worker that periodically retries pending uploads.

    Args:
        uploader: S3Uploader instance
        interval_sec: Retry interval in seconds
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Started pending retry worker (interval={interval_sec}s)")

    while not shutdown_event.is_set():
        try:
            # Wait for interval or shutdown
            if shutdown_event.wait(timeout=interval_sec):
                break

            # Retry pending uploads
            logger.debug("Running pending upload retry...")
            success, failed = uploader.retry_pending()

            if success > 0 or failed > 0:
                logger.info(
                    f"Pending retry: {success} succeeded, {failed} failed"
                )

        except Exception as e:
            logger.error(f"Error in retry worker: {e}")

    logger.info("Pending retry worker stopped")


def run_agent(config: dict, simulate: bool) -> NoReturn:
    """
    Main agent loop.

    Args:
        config: Configuration dictionary
        simulate: Whether to run in simulation mode
    """
    logger = logging.getLogger(__name__)

    # Extract configuration
    vehicle_id = config["vehicle_id"]
    s3_config = config["s3"]
    can_config = config["can"]
    dbc_config = config["dbc"]
    batch_config = config["batch"]
    storage_config = config["storage"]
    upload_config = config["upload"]
    offline_config = config["offline"]

    logger.info(f"Starting CAN telemetry edge agent for vehicle: {vehicle_id}")
    logger.info(f"Mode: {'SIMULATION' if simulate else 'REAL CAN INTERFACE'}")

    # Initialize components
    batcher = CANFrameBatcher(
        vehicle_id=vehicle_id,
        window_sec=batch_config["interval_sec"],
        max_frames=batch_config["max_frames"],
        output_dir=storage_config["data_dir"],
    )

    uploader = S3Uploader(
        bucket=s3_config["bucket"],
        region=s3_config["region"],
        prefix=s3_config["prefix"],
        max_retries=upload_config["max_retries"],
        initial_backoff_sec=upload_config["initial_backoff_sec"],
        max_backoff_sec=upload_config["max_backoff_sec"],
        archive_dir=storage_config["archive_dir"],
        pending_dir=storage_config["pending_dir"],
    )

    offline_buffer = OfflineBuffer(
        pending_dir=storage_config["pending_dir"],
        max_disk_gb=storage_config["max_disk_gb"],
        max_queue_size=offline_config["max_queue_size"],
    )

    # Start background retry worker
    retry_thread = threading.Thread(
        target=retry_pending_worker,
        args=(uploader, offline_config["check_interval_sec"]),
        daemon=True,
    )
    retry_thread.start()

    # Initialize CAN reader
    if simulate:
        logger.info(f"Using simulated CAN with DBC: {dbc_config['path']}")
        reader = SimulatedCANReader(
            dbc_path=dbc_config["path"],
            frequency=100,  # 100 Hz simulation
        )
    else:
        logger.info(
            f"Using real CAN interface: {can_config['interface']} "
            f"{can_config['channel']}"
        )
        reader = RealCANReader(
            interface=can_config["interface"],
            channel=can_config["channel"],
            bitrate=can_config["bitrate"],
        )

    # Main processing loop
    try:
        with reader:
            logger.info("CAN reader initialized, starting frame capture...")

            frame_count = 0
            batch_count = 0
            upload_success = 0
            upload_failed = 0

            for parquet_path in batcher.process_frames(reader.read_frames()):
                # Check for shutdown
                if shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping capture...")
                    break

                batch_count += 1
                logger.info(f"Batch {batch_count} written: {parquet_path}")

                # Attempt upload
                if uploader.upload(parquet_path):
                    upload_success += 1
                else:
                    upload_failed += 1
                    logger.warning(
                        f"Upload failed for batch {batch_count}, "
                        f"file moved to pending"
                    )

                # Log statistics periodically
                if batch_count % 10 == 0:
                    buffer_stats = offline_buffer.get_stats()
                    logger.info(
                        f"Stats: batches={batch_count}, "
                        f"upload_ok={upload_success}, "
                        f"upload_fail={upload_failed}, "
                        f"pending={buffer_stats['pending_count']}, "
                        f"disk={buffer_stats['disk_usage_gb']:.2f}GB"
                    )

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error in agent loop: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Graceful shutdown
        logger.info("Shutting down edge agent...")
        shutdown_event.set()

        # Wait for retry worker to finish
        retry_thread.join(timeout=5)

        # Final statistics
        buffer_stats = offline_buffer.get_stats()
        logger.info(
            f"Final stats: batches={batch_count}, "
            f"upload_ok={upload_success}, "
            f"upload_fail={upload_failed}, "
            f"pending={buffer_stats['pending_count']}"
        )

        logger.info("Edge agent stopped")
        sys.exit(0)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CAN telemetry edge agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with real CAN interface
  python -m src.main --config config.yaml

  # Run in simulation mode
  python -m src.main --config config.yaml --simulate

  # Custom config path
  python -m src.main --config /path/to/config.yaml --simulate
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to configuration YAML file",
    )

    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulation mode (generate fake CAN data)",
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    setup_logging(config)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run agent
    run_agent(config, args.simulate)


if __name__ == "__main__":
    main()
