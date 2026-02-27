"""Lambda handler for registering Athena partitions on new decoded Parquet files.

Triggered by S3 ObjectCreated events on decoded/*.parquet.
Runs ALTER TABLE ... ADD IF NOT EXISTS PARTITION for each new file,
which is O(1) and far cheaper than a full MSCK REPAIR TABLE scan.
"""

import logging
import os
import re
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

athena = boto3.client("athena")

DATABASE = os.environ["ATHENA_DATABASE"]
WORKGROUP = os.environ["ATHENA_WORKGROUP"]
TABLE = "decoded"

# Matches: decoded/vehicle_id=VIN001/year=2026/month=02/day=12/file.parquet
PARTITION_RE = re.compile(
    r"decoded/vehicle_id=([^/]+)/year=([^/]+)/month=([^/]+)/day=([^/]+)/"
)

POLL_INTERVAL_S = 2
MAX_WAIT_S = 30


def _wait_for_query(query_id: str) -> tuple[str, str]:
    """Poll until the query leaves QUEUED/RUNNING. Returns (state, reason)."""
    deadline = time.time() + MAX_WAIT_S
    while time.time() < deadline:
        resp = athena.get_query_execution(QueryExecutionId=query_id)
        status = resp["QueryExecution"]["Status"]
        state = status["State"]
        if state not in ("QUEUED", "RUNNING"):
            reason = status.get("StateChangeReason", "")
            return state, reason
        time.sleep(POLL_INTERVAL_S)
    return "TIMEOUT", "exceeded MAX_WAIT_S"


def _register_partition(bucket: str, vehicle_id: str, year: str, month: str, day: str) -> None:
    """Run ALTER TABLE ADD IF NOT EXISTS PARTITION for one day-level partition."""
    location = (
        f"s3://{bucket}/decoded"
        f"/vehicle_id={vehicle_id}"
        f"/year={year}"
        f"/month={month}"
        f"/day={day}/"
    )

    query = (
        f"ALTER TABLE {DATABASE}.{TABLE} ADD IF NOT EXISTS "
        f"PARTITION ("
        f"vehicle_id='{vehicle_id}', "
        f"year='{year}', "
        f"month='{month}', "
        f"day='{day}'"
        f") "
        f"LOCATION '{location}'"
    )

    logger.info(
        "Registering partition: vehicle_id=%s %s/%s/%s → %s",
        vehicle_id, year, month, day, location,
    )

    resp = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
    )
    query_id = resp["QueryExecutionId"]
    logger.info("Athena query started: %s", query_id)

    state, reason = _wait_for_query(query_id)

    if state == "SUCCEEDED":
        logger.info("Partition registered successfully: %s", location)
    else:
        logger.error(
            "Partition registration failed — query=%s state=%s reason=%s",
            query_id, state, reason,
        )
        raise RuntimeError(
            f"Athena query {query_id} ended with state {state}: {reason}"
        )


def handler(event, context):
    """Entry point. Handles all S3 records in the event batch."""
    errors = []

    for record in event["Records"]:
        key = record["s3"]["object"]["key"]
        bucket = record["s3"]["bucket"]["name"]

        match = PARTITION_RE.match(key)
        if not match:
            logger.info("Skipping non-partition key: %s", key)
            continue

        vehicle_id, year, month, day = match.groups()

        try:
            _register_partition(bucket, vehicle_id, year, month, day)
        except Exception as exc:
            # Collect errors so remaining records are still processed
            logger.error("Failed for key %s: %s", key, exc)
            errors.append(str(exc))

    if errors:
        raise RuntimeError(f"{len(errors)} partition(s) failed: {errors}")
