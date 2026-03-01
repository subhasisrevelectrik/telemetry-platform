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
    """Get signals from local files.

    Reads a single representative Parquet file so the response is fast
    even when there are millions of rows across many partitions.
    """
    data_dir = Path(settings.local_data_dir)
    vehicle_dir = data_dir / f"vehicle_id={vehicle_id}"

    if not vehicle_dir.exists():
        return []

    parquet_files = sorted(vehicle_dir.rglob("*.parquet"))
    if not parquet_files:
        return []

    signal_stats: dict = {}

    # Read ONE file — signal names and units are identical across partitions.
    # Stats (min/max/avg) are approximate but sufficient for the selector UI.
    for parquet_file in parquet_files[:1]:
        import pyarrow.compute as pc

        table = pq.ParquetFile(str(parquet_file)).read(
            columns=["message_name", "signal_name", "value", "unit"]
        )
        mask = pc.equal(table.column("message_name"), message_name)
        filtered = table.filter(mask)

        if len(filtered) == 0:
            continue

        for sig_name in filtered.column("signal_name").unique().to_pylist():
            sig_mask = pc.equal(filtered.column("signal_name"), sig_name)
            sig_rows = filtered.filter(sig_mask)
            values = sig_rows.column("value")
            unit = sig_rows.column("unit")[0].as_py()
            signal_stats[sig_name] = {
                "unit": unit,
                "min": pc.min(values).as_py(),
                "max": pc.max(values).as_py(),
                "mean": pc.mean(values).as_py(),
            }

    return sorted(
        [
            Signal(
                signal_name=sig_name,
                unit=stats["unit"],
                min_value=stats["min"],
                max_value=stats["max"],
                avg_value=stats["mean"],
            )
            for sig_name, stats in signal_stats.items()
        ],
        key=lambda s: s.signal_name,
    )


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
