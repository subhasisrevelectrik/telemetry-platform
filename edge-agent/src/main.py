"""Main entry point for CAN telemetry edge agent."""

import argparse
import logging
import shutil
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import NoReturn, Optional

import cantools
import yaml

from .batcher import CANFrameBatcher
from .can_reader import RealCANReader, SimulatedCANReader
from .offline_buffer import OfflineBuffer
from .uploader import S3Uploader

# Global flag for graceful shutdown
shutdown_event = threading.Event()

# Module-level logger (configured later by setup_logging)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------


def signal_handler(signum: int, frame: object) -> None:
    """Handle SIGINT / SIGTERM for graceful shutdown."""
    logger.info("Received signal %d, initiating graceful shutdown...", signum)
    shutdown_event.set()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging(config: dict) -> None:
    """
    Configure root logger from the ``logging`` section of config.

    Args:
        config: Full configuration dictionary
    """
    log_cfg = config.get("logging", {})
    level_name: str = log_cfg.get("level", "INFO")
    fmt: str = log_cfg.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_file: Optional[str] = log_cfg.get("file")
    max_bytes: int = int(log_cfg.get("max_bytes", 10 * 1024 * 1024))  # 10 MB
    backup_count: int = int(log_cfg.get("backup_count", 5))

    level = getattr(logging, level_name.upper(), logging.INFO)
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # Rotating file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)


# ---------------------------------------------------------------------------
# Config normalisation (supports both config.yaml and config-rpi.yaml schemas)
# ---------------------------------------------------------------------------


def _normalize_config(raw: dict) -> dict:
    """
    Return a canonical config dict regardless of which YAML schema was loaded.

    Supports:
      * **Old schema** (config.yaml)  — keys: s3, batch, storage, upload, offline
      * **New RPi schema** (config-rpi.yaml) — keys: batching, upload.s3_bucket,
        offline_buffer, monitoring

    The canonical form uses the old-schema key names so existing code paths
    work without modification.  New-only keys (monitoring, can.fd, can.filters)
    are preserved as-is.
    """
    cfg = dict(raw)

    # Detect schema: rpi-schema uses "batching" or "offline_buffer" top-level keys
    is_rpi_schema = "batching" in cfg or "offline_buffer" in cfg
    if not is_rpi_schema:
        return cfg  # already canonical

    # ---- batching -> batch + storage ----------------------------------- #
    batching = cfg.get("batching", {})
    if "batch" not in cfg:
        cfg["batch"] = {
            "interval_sec": int(batching.get("interval_seconds", 60)),
            "max_frames": int(batching.get("max_frames_per_batch", 100000)),
        }
    if "storage" not in cfg:
        output_dir = batching.get("output_dir", "./data/raw")
        base_dir = str(Path(output_dir).parent)
        ob = cfg.get("offline_buffer", {})
        cfg["storage"] = {
            "data_dir": output_dir,
            "archive_dir": ob.get("archive_dir", str(Path(base_dir) / "archive")),
            "pending_dir": ob.get("pending_dir", str(Path(base_dir) / "pending")),
            "max_disk_gb": float(ob.get("max_disk_usage_mb", 5000)) / 1024,
        }

    # ---- upload (rpi) -> s3 + upload (canonical) ----------------------- #
    upload = cfg.get("upload", {})
    if "s3" not in cfg and "s3_bucket" in upload:
        cfg["s3"] = {
            "bucket": upload.get("s3_bucket", ""),
            "region": upload.get("region", "us-east-1"),
            "prefix": upload.get("s3_prefix", "raw"),
        }
        cfg["upload"] = {
            "enabled": bool(upload.get("enabled", True)),
            "max_retries": int(upload.get("max_retries", 5)),
            "initial_backoff_sec": float(upload.get("retry_backoff_base", 2.0)),
            "max_backoff_sec": 300,
        }

    # ---- offline_buffer -> offline -------------------------------------- #
    ob = cfg.get("offline_buffer", {})
    if "offline" not in cfg and ob:
        cfg["offline"] = {
            "check_interval_sec": int(ob.get("retry_interval_seconds", 300)),
            "max_queue_size": 100,
        }

    return cfg


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_config(config_path: str) -> dict:
    """
    Load and normalise configuration from a YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Normalised configuration dictionary
    """
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return _normalize_config(raw)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------


def retry_pending_worker(uploader: S3Uploader, interval_sec: int) -> None:
    """
    Background worker that periodically retries pending S3 uploads.

    Args:
        uploader: S3Uploader instance
        interval_sec: Retry interval in seconds
    """
    logger.info("Started pending retry worker (interval=%d s)", interval_sec)

    while not shutdown_event.is_set():
        try:
            if shutdown_event.wait(timeout=interval_sec):
                break
            logger.debug("Running pending upload retry...")
            success, failed = uploader.retry_pending()
            if success > 0 or failed > 0:
                logger.info(
                    "Pending retry: %d succeeded, %d failed", success, failed
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in retry worker: %s", exc)

    logger.info("Pending retry worker stopped")


def _read_cpu_temp() -> Optional[float]:
    """Read Raspberry Pi CPU temperature in degrees Celsius."""
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        return int(raw) / 1000.0
    except Exception:  # noqa: BLE001
        return None


def health_monitor_worker(
    reader: RealCANReader,
    pending_dir: str,
    data_dir: str,
    interval_sec: int,
) -> None:
    """
    Background thread that logs health stats at a regular interval.

    Logs frames/sec, cumulative counts, pending uploads, disk usage,
    and CPU temperature (Raspberry Pi only).

    Args:
        reader: The active RealCANReader
        pending_dir: Directory holding files waiting for upload
        data_dir: Root data directory (for disk-usage check)
        interval_sec: How often to log stats (seconds)
    """
    logger.info("Started health monitor (interval=%d s)", interval_sec)
    session_start = time.time()

    while not shutdown_event.is_set():
        if shutdown_event.wait(timeout=interval_sec):
            break
        try:
            stats = reader.get_stats()
            pending_count = (
                len(list(Path(pending_dir).glob("*.parquet")))
                if Path(pending_dir).exists()
                else 0
            )
            try:
                usage = shutil.disk_usage(data_dir)
                disk_used_gb = usage.used / (1024 ** 3)
                disk_free_gb = usage.free / (1024 ** 3)
            except Exception:  # noqa: BLE001
                disk_used_gb = disk_free_gb = 0.0

            cpu_temp = _read_cpu_temp()
            uptime_min = (time.time() - session_start) / 60.0

            parts = [
                f"uptime={uptime_min:.1f}min",
                f"frames={stats['frames']}",
                f"fps={stats['frames_per_sec']}",
                f"errors={stats['errors']}",
                f"bus_off={stats['bus_off']}",
                f"pending={pending_count}",
                f"disk_used={disk_used_gb:.1f}GB",
                f"disk_free={disk_free_gb:.1f}GB",
            ]
            if cpu_temp is not None:
                parts.append(f"cpu_temp={cpu_temp:.1f}C")

            logger.info("HEALTH: %s", " | ".join(parts))
        except Exception as exc:  # noqa: BLE001
            logger.error("Health monitor error: %s", exc)

    logger.info("Health monitor stopped")


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


def run_dry_run(config: dict) -> NoReturn:
    """
    Read real CAN frames and log them to the console without batching or uploading.

    Useful for verifying the CAN connection before a full capture session.

    Args:
        config: Normalised configuration dictionary
    """
    logger.info("=== DRY-RUN MODE — no data will be written or uploaded ===")
    reader = RealCANReader(config)

    try:
        with reader:
            for frame in reader.read_frames():
                if shutdown_event.is_set():
                    break
                logger.info(
                    "FRAME arb_id=0x%03X dlc=%d data=%s ts=%.6f",
                    frame.arb_id,
                    frame.dlc,
                    frame.data.hex(),
                    frame.timestamp,
                )
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_event.set()
        logger.info(
            "Dry-run finished. Total frames: %d", reader.get_stats()["frames"]
        )

    sys.exit(0)


# ---------------------------------------------------------------------------
# Decode-live mode
# ---------------------------------------------------------------------------


def run_decode_live(config: dict) -> NoReturn:
    """
    Read real CAN frames, decode them with the configured DBC file, and print
    decoded signal values to stdout in real time.

    Output format:
        [timestamp] MessageName.SignalName = value unit

    Args:
        config: Normalised configuration dictionary
    """
    dbc_path: Optional[str] = config.get("dbc", {}).get("path")
    if not dbc_path:
        logger.error("No DBC path configured. Set dbc.path in your config file.")
        sys.exit(1)

    logger.info("=== DECODE-LIVE MODE — loading DBC: %s ===", dbc_path)
    try:
        db = cantools.database.load_file(dbc_path)
    except Exception as exc:
        logger.error("Failed to load DBC: %s", exc)
        sys.exit(1)

    logger.info(
        "Loaded %d messages, %d signals",
        len(db.messages),
        sum(len(m.signals) for m in db.messages),
    )
    logger.info("Listening on %s...", config["can"]["channel"])

    reader = RealCANReader(config)
    frame_count = 0
    decode_errors = 0

    try:
        with reader:
            for frame in reader.read_frames():
                if shutdown_event.is_set():
                    break
                frame_count += 1
                try:
                    msg = db.get_message_by_frame_id(frame.arb_id)
                    decoded = msg.decode(frame.data, decode_choices=False)
                    ts_str = f"[{frame.timestamp:.3f}]"
                    for sig_name, value in decoded.items():
                        sig = msg.get_signal_by_name(sig_name)
                        unit = sig.unit or ""
                        print(f"{ts_str} {msg.name}.{sig_name} = {value} {unit}")
                except KeyError:
                    logger.debug(
                        "Unknown frame 0x%03X: %s", frame.arb_id, frame.data.hex()
                    )
                except Exception as exc:  # noqa: BLE001
                    decode_errors += 1
                    logger.debug("Decode error for 0x%03X: %s", frame.arb_id, exc)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_event.set()
        logger.info(
            "Decode-live finished: %d frames, %d decode errors",
            frame_count,
            decode_errors,
        )

    sys.exit(0)


# ---------------------------------------------------------------------------
# Normal agent loop
# ---------------------------------------------------------------------------


def run_agent(config: dict, simulate: bool) -> NoReturn:
    """
    Main agent loop — reads CAN frames, batches to Parquet, uploads to S3.

    Args:
        config: Normalised configuration dictionary
        simulate: When True, use SimulatedCANReader instead of real hardware
    """
    vehicle_id: str = config["vehicle_id"]
    s3_config: dict = config["s3"]
    can_config: dict = config["can"]
    dbc_config: dict = config["dbc"]
    batch_config: dict = config["batch"]
    storage_config: dict = config["storage"]
    upload_config: dict = config["upload"]
    offline_config: dict = config["offline"]
    monitoring_config: dict = config.get("monitoring", {})
    heartbeat_sec: int = int(monitoring_config.get("heartbeat_interval_seconds", 60))

    logger.info("Starting CAN telemetry edge agent for vehicle: %s", vehicle_id)
    logger.info("Mode: %s", "SIMULATION" if simulate else "REAL CAN INTERFACE")

    # ---- Component initialisation -------------------------------------- #
    batcher = CANFrameBatcher(
        vehicle_id=vehicle_id,
        window_sec=batch_config["interval_sec"],
        max_frames=batch_config["max_frames"],
        output_dir=storage_config["data_dir"],
    )

    upload_enabled: bool = bool(upload_config.get("enabled", True))
    if not upload_enabled:
        logger.info("Upload disabled — operating in local-only mode")
        uploader = None
    else:
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

    # ---- Background threads ------------------------------------------- #
    threads: list[threading.Thread] = []

    if uploader is not None:
        retry_thread = threading.Thread(
            target=retry_pending_worker,
            args=(uploader, offline_config["check_interval_sec"]),
            daemon=True,
            name="retry-worker",
        )
        retry_thread.start()
        threads.append(retry_thread)

    # ---- CAN reader ---------------------------------------------------- #
    if simulate:
        logger.info("Using simulated CAN with DBC: %s", dbc_config["path"])
        reader_ctx: SimulatedCANReader | RealCANReader = SimulatedCANReader(
            dbc_path=dbc_config["path"], frequency=100
        )
    else:
        logger.info(
            "Using real CAN interface: %s %s",
            can_config["interface"],
            can_config["channel"],
        )
        reader_ctx = RealCANReader(config)

        # Health monitor only makes sense for real hardware
        health_thread = threading.Thread(
            target=health_monitor_worker,
            args=(
                reader_ctx,
                storage_config["pending_dir"],
                storage_config["data_dir"],
                heartbeat_sec,
            ),
            daemon=True,
            name="health-monitor",
        )
        health_thread.start()
        threads.append(health_thread)

    # ---- Main loop ----------------------------------------------------- #
    batch_count = 0
    upload_success = 0
    upload_failed = 0

    try:
        with reader_ctx:
            logger.info("CAN reader initialised, starting frame capture...")

            for parquet_path in batcher.process_frames(reader_ctx.read_frames()):
                if shutdown_event.is_set():
                    logger.info("Shutdown requested, stopping capture...")
                    break

                batch_count += 1
                logger.info("Batch %d written: %s", batch_count, parquet_path)

                if uploader is not None:
                    if uploader.upload(parquet_path):
                        upload_success += 1
                    else:
                        upload_failed += 1
                        logger.warning(
                            "Upload failed for batch %d, file moved to pending",
                            batch_count,
                        )

                if batch_count % 10 == 0:
                    buf_stats = offline_buffer.get_stats()
                    logger.info(
                        "Stats: batches=%d upload_ok=%d upload_fail=%d "
                        "pending=%d disk=%.2f GB",
                        batch_count,
                        upload_success,
                        upload_failed,
                        buf_stats["pending_count"],
                        buf_stats["disk_usage_gb"],
                    )

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as exc:
        logger.error("Fatal error in agent loop: %s", exc, exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Shutting down edge agent...")
        shutdown_event.set()

        for t in threads:
            t.join(timeout=5)

        buf_stats = offline_buffer.get_stats()
        logger.info(
            "Final stats: batches=%d upload_ok=%d upload_fail=%d pending=%d",
            batch_count,
            upload_success,
            upload_failed,
            buf_stats["pending_count"],
        )
        logger.info("Edge agent stopped")

    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate run mode."""
    parser = argparse.ArgumentParser(
        description="CAN telemetry edge agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Real CAN hardware (full capture + S3 upload)
  python -m src.main --config config-rpi.yaml

  # Simulation mode
  python -m src.main --config config.yaml --simulate

  # Verify CAN connection without writing anything
  python -m src.main --config config-rpi.yaml --dry-run

  # Real-time signal decode and print
  python -m src.main --config config-rpi.yaml --decode-live
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
        help="Run in simulation mode (generate fake CAN data from DBC)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read real CAN frames and log them; do NOT write or upload anything",
    )
    parser.add_argument(
        "--decode-live",
        action="store_true",
        help="Read real CAN, decode with DBC, print signal values to stdout",
    )

    args = parser.parse_args()

    # Mutually exclusive flags
    if sum([args.simulate, args.dry_run, args.decode_live]) > 1:
        parser.error(
            "--simulate, --dry-run, and --decode-live are mutually exclusive"
        )

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Error loading config: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.dry_run:
        run_dry_run(config)
    elif args.decode_live:
        run_decode_live(config)
    else:
        run_agent(config, simulate=args.simulate)


if __name__ == "__main__":
    main()
