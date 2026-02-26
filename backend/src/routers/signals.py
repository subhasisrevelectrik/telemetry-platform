"""Signals router."""

from pathlib import Path
from typing import List

import pyarrow.parquet as pq
from fastapi import APIRouter

from ..athena_client import AthenaClient
from ..config import settings
from ..models import Signal

router = APIRouter()


@router.get("/{vehicle_id}/messages/{message_name}/signals", response_model=List[Signal])
async def get_signals(vehicle_id: str, message_name: str):
    """Get signals for a specific message."""
    if settings.local_mode:
        return get_signals_local(vehicle_id, message_name)
    else:
        return get_signals_athena(vehicle_id, message_name)


def get_signals_local(vehicle_id: str, message_name: str) -> List[Signal]:
    """Get signals from local files."""
    data_dir = Path(settings.local_data_dir)
    vehicle_dir = data_dir / f"vehicle_id={vehicle_id}"

    if not vehicle_dir.exists():
        return []

    signal_stats = {}

    for parquet_file in vehicle_dir.rglob("*.parquet"):
        table = pq.read_table(parquet_file)

        # Filter by message_name
        mask = [msg == message_name for msg in table.column("message_name").to_pylist()]
        filtered = table.filter(mask)

        if len(filtered) == 0:
            continue

        signal_names = filtered.column("signal_name").to_pylist()
        values = filtered.column("value").to_pylist()
        units = filtered.column("unit").to_pylist()

        for sig_name, value, unit in zip(signal_names, values, units):
            if sig_name not in signal_stats:
                signal_stats[sig_name] = {
                    "unit": unit,
                    "values": []
                }
            signal_stats[sig_name]["values"].append(value)

    signals = []
    for sig_name, stats in signal_stats.items():
        values = stats["values"]
        signals.append(Signal(
            signal_name=sig_name,
            unit=stats["unit"],
            min_value=min(values),
            max_value=max(values),
            avg_value=sum(values) / len(values),
        ))

    return sorted(signals, key=lambda s: s.signal_name)


def get_signals_athena(vehicle_id: str, message_name: str) -> List[Signal]:
    """Get signals from Athena."""
    client = AthenaClient()

    sql = f"""
    SELECT
        signal_name,
        unit,
        MIN(value) as min_value,
        MAX(value) as max_value,
        AVG(value) as avg_value
    FROM decoded
    WHERE vehicle_id = '{vehicle_id}' AND message_name = '{message_name}'
    GROUP BY signal_name, unit
    ORDER BY signal_name
    """

    results = client.run_query(sql)

    return [
        Signal(
            signal_name=row["signal_name"],
            unit=row["unit"],
            min_value=float(row["min_value"]),
            max_value=float(row["max_value"]),
            avg_value=float(row["avg_value"]),
        )
        for row in results
    ]
