"""Sessions router."""

from datetime import datetime
from typing import List

from fastapi import APIRouter

from ..athena_client import AthenaClient
from ..config import settings
from ..models import Session

router = APIRouter()


@router.get("/{vehicle_id}/sessions", response_model=List[Session])
async def get_sessions(vehicle_id: str):
    """Get recording sessions for a vehicle."""
    if settings.local_mode:
        # Simplified local mode - return empty list
        return []

    client = AthenaClient()

    sql = f"""
    SELECT
        DATE(timestamp) as date,
        MIN(timestamp) as start_time,
        MAX(timestamp) as end_time,
        COUNT(*) as sample_count
    FROM decoded
    WHERE vehicle_id = '{vehicle_id}'
    GROUP BY DATE(timestamp)
    ORDER BY DATE(timestamp) DESC
    """

    results = client.run_query(sql)

    sessions = []
    for row in results:
        sessions.append(Session(
            date=row["date"],
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]),
            sample_count=int(row["sample_count"]),
        ))

    return sessions
