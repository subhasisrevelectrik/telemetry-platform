"""Lambda handler for decoding raw CAN Parquet files."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

import boto3
import cantools
import pyarrow.parquet as pq

from decoder_core import decode_raw_table

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3_client = boto3.client("s3")

# Environment variables
DBC_BUCKET = os.environ.get("DBC_BUCKET", "")
DBC_KEY = os.environ.get("DBC_KEY", "dbc/ev_powertrain.dbc")
DECODED_PREFIX = os.environ.get("DECODED_PREFIX", "decoded")

# Cache DBC in /tmp across warm starts
DBC_CACHE_PATH = "/tmp/cached.dbc"
db_cache: cantools.database.Database | None = None


def load_dbc() -> cantools.database.Database:
    """
    Load DBC file from S3, with caching.

    Returns:
        Loaded cantools database
    """
    global db_cache

    # Return cached DB if available
    if db_cache is not None:
        logger.info("Using cached DBC")
        return db_cache

    # Check if DBC is in /tmp from previous invocation
    if Path(DBC_CACHE_PATH).exists():
        logger.info(f"Loading DBC from warm cache: {DBC_CACHE_PATH}")
        db_cache = cantools.database.load_file(DBC_CACHE_PATH)
        return db_cache

    # Download from S3
    logger.info(f"Downloading DBC from s3://{DBC_BUCKET}/{DBC_KEY}")
    s3_client.download_file(DBC_BUCKET, DBC_KEY, DBC_CACHE_PATH)

    # Load DBC
    logger.info(f"Loading DBC: {DBC_CACHE_PATH}")
    db_cache = cantools.database.load_file(DBC_CACHE_PATH)

    logger.info(
        f"DBC loaded: {len(db_cache.messages)} messages, "
        f"{sum(len(msg.signals) for msg in db_cache.messages)} signals"
    )

    return db_cache


def extract_partition_info(s3_key: str) -> dict[str, str]:
    """
    Extract Hive partition values from S3 key.

    Args:
        s3_key: S3 object key

    Returns:
        Dictionary of partition key-value pairs
    """
    partitions = {}
    parts = s3_key.split("/")

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            partitions[key] = value

    return partitions


def build_decoded_key(raw_key: str, decoded_prefix: str) -> str:
    """
    Build output S3 key from input key, preserving partitions.

    Args:
        raw_key: Input S3 key (e.g., raw/vehicle_id=X/year=Y/month=M/day=D/file.parquet)
        decoded_prefix: Output prefix (e.g., "decoded")

    Returns:
        Output S3 key
    """
    # Extract filename and partition parts
    parts = raw_key.split("/")
    filename = parts[-1].replace("_raw.parquet", "_decoded.parquet")

    # Find partition components
    partition_parts = [p for p in parts if "=" in p]

    # Build output key
    output_key = "/".join([decoded_prefix] + partition_parts + [filename])

    return output_key


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for S3-triggered CAN frame decoding.

    Args:
        event: S3 PUT event
        context: Lambda context

    Returns:
        Response with decode statistics
    """
    start_time = time.time()

    try:
        # Extract S3 event details
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        logger.info(f"Processing: s3://{bucket}/{key}")

        # Download raw Parquet file
        raw_local_path = f"/tmp/raw_{Path(key).name}"
        logger.info(f"Downloading to {raw_local_path}")
        s3_client.download_file(bucket, key, raw_local_path)

        file_size_mb = Path(raw_local_path).stat().st_size / (1024 * 1024)
        logger.info(f"Downloaded {file_size_mb:.2f} MB")

        # Load DBC
        dbc = load_dbc()

        # Read raw Parquet
        logger.info("Reading raw Parquet file")
        raw_table = pq.read_table(raw_local_path)
        logger.info(f"Read {len(raw_table)} raw frames")

        # Decode frames
        logger.info("Decoding CAN frames")
        decoded_table = decode_raw_table(raw_table, dbc)
        logger.info(f"Decoded to {len(decoded_table)} signals")

        # Write decoded Parquet
        decoded_local_path = f"/tmp/decoded_{Path(key).name}"
        pq.write_table(
            decoded_table,
            decoded_local_path,
            compression="zstd",
            compression_level=3,
            use_dictionary=True,
            write_statistics=True,
        )

        decoded_size_mb = Path(decoded_local_path).stat().st_size / (1024 * 1024)
        logger.info(f"Wrote decoded Parquet: {decoded_size_mb:.2f} MB")

        # Upload to S3
        output_key = build_decoded_key(key, DECODED_PREFIX)
        logger.info(f"Uploading to s3://{bucket}/{output_key}")

        s3_client.upload_file(
            decoded_local_path,
            bucket,
            output_key,
            ExtraArgs={
                "ServerSideEncryption": "AES256",
            },
        )

        # Cleanup temp files
        Path(raw_local_path).unlink(missing_ok=True)
        Path(decoded_local_path).unlink(missing_ok=True)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Return success
        result = {
            "statusCode": 200,
            "body": json.dumps({
                "input": f"s3://{bucket}/{key}",
                "output": f"s3://{bucket}/{output_key}",
                "raw_frames": len(raw_table),
                "decoded_signals": len(decoded_table),
                "duration_ms": duration_ms,
            }),
        }

        logger.info(f"Decode complete: {duration_ms}ms")
        return result

    except Exception as e:
        logger.error(f"Error decoding CAN data: {e}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }),
        }
