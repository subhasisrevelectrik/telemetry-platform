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

    # Read all Parquet files and aggregate message counts
    message_counts = {}
    for parquet_file in vehicle_dir.rglob("*.parquet"):
        table = pq.read_table(parquet_file, columns=["message_name"])
        for msg_name in table.column("message_name").to_pylist():
            message_counts[msg_name] = message_counts.get(msg_name, 0) + 1

    return [
        Message(message_name=name, sample_count=count)
        for name, count in sorted(message_counts.items())
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
