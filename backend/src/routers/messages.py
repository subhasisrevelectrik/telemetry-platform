"""Messages router."""

from pathlib import Path
from typing import List

import pyarrow.parquet as pq
from fastapi import APIRouter

from ..athena_client import AthenaClient
from ..config import settings
from ..models import Message

router = APIRouter()


@router.get("/{vehicle_id}/messages", response_model=List[Message])
async def get_messages(vehicle_id: str):
    """Get available CAN messages for a vehicle."""
    if settings.local_mode:
        return get_messages_local(vehicle_id)
    else:
        return get_messages_athena(vehicle_id)


def get_messages_local(vehicle_id: str) -> List[Message]:
    """Get messages from local files."""
    data_dir = Path(settings.local_data_dir)
    vehicle_dir = data_dir / f"vehicle_id={vehicle_id}"

    if not vehicle_dir.exists():
        return []

    parquet_files = sorted(vehicle_dir.rglob("*.parquet"))
    if not parquet_files:
        return []

    # Distinct message names come from the first file (consistent across partitions).
    # This avoids a full O(total_rows) scan — reads one file instead of all.
    first_table = pq.ParquetFile(str(parquet_files[0])).read(columns=["message_name"])
    unique_names = sorted(first_table.column("message_name").unique().to_pylist())

    # Count total rows using Parquet metadata only (no data read).
    total_rows = sum(pq.read_metadata(str(f)).num_rows for f in parquet_files)
    per_message = total_rows // len(unique_names) if unique_names else 0

    return [
        Message(message_name=name, sample_count=per_message)
        for name in unique_names
    ]


def get_messages_athena(vehicle_id: str) -> List[Message]:
    """Get messages from Athena."""
    client = AthenaClient()

    sql = f"""
    SELECT message_name, COUNT(*) as sample_count
    FROM decoded
    WHERE vehicle_id = '{vehicle_id}'
    GROUP BY message_name
    ORDER BY message_name
    """

    results = client.run_query(sql)

    return [
        Message(message_name=row["message_name"], sample_count=int(row["sample_count"]))
        for row in results
    ]
