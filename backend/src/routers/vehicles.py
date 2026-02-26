"""Vehicles router."""

from datetime import datetime
from pathlib import Path
from typing import List

import pyarrow.parquet as pq
from fastapi import APIRouter, HTTPException

from ..athena_client import AthenaClient
from ..config import settings
from ..models import Vehicle

router = APIRouter()


@router.get("", response_model=List[Vehicle])
async def list_vehicles():
    """List all vehicles with metadata."""
    if settings.local_mode:
        return list_vehicles_local()
    else:
        return list_vehicles_athena()


def list_vehicles_local() -> List[Vehicle]:
    """List vehicles from local Parquet files."""
    vehicles_data = {}
    data_dir = Path(settings.local_data_dir)

    if not data_dir.exists():
        return []

    # Scan for vehicle_id partitions
    for vehicle_dir in data_dir.glob("vehicle_id=*"):
        vehicle_id = vehicle_dir.name.split("=")[1]

        # Find all Parquet files for this vehicle
        parquet_files = list(vehicle_dir.rglob("*.parquet"))

        if not parquet_files:
            continue

        # Read first and last files to get time range
        first_file = min(parquet_files, key=lambda p: p.stat().st_mtime)
        last_file = max(parquet_files, key=lambda p: p.stat().st_mtime)

        first_table = pq.ParquetFile(first_file).read(columns=["timestamp"])
        last_table = pq.ParquetFile(last_file).read(columns=["timestamp"])

        first_seen = datetime.fromtimestamp(
            first_table.column("timestamp")[0].as_py().timestamp()
        )
        last_seen = datetime.fromtimestamp(
            last_table.column("timestamp")[-1].as_py().timestamp()
        )

        # Count total rows (read metadata only — no data scan needed)
        frame_count = sum(pq.ParquetFile(f).metadata.num_rows for f in parquet_files)

        vehicles_data[vehicle_id] = Vehicle(
            vehicle_id=vehicle_id,
            first_seen=first_seen,
            last_seen=last_seen,
            frame_count=frame_count,
        )

    return list(vehicles_data.values())


def list_vehicles_athena() -> List[Vehicle]:
    """List vehicles from Athena."""
    client = AthenaClient()

    sql = """
    SELECT
        vehicle_id,
        MIN(timestamp) as first_seen,
        MAX(timestamp) as last_seen,
        COUNT(*) as frame_count
    FROM decoded
    GROUP BY vehicle_id
    ORDER BY vehicle_id
    """

    try:
        results = client.run_query(sql)

        vehicles = []
        for row in results:
            # Convert bigint nanoseconds to datetime
            first_seen_ns = int(row["first_seen"])
            last_seen_ns = int(row["last_seen"])
            first_seen = datetime.fromtimestamp(first_seen_ns / 1e9)
            last_seen = datetime.fromtimestamp(last_seen_ns / 1e9)

            vehicles.append(Vehicle(
                vehicle_id=row["vehicle_id"],
                first_seen=first_seen,
                last_seen=last_seen,
                frame_count=int(row["frame_count"]),
            ))

        return vehicles

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
