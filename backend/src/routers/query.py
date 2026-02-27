"""Query router for time-series data."""

import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from fastapi import APIRouter, HTTPException

from ..athena_client import AthenaClient
from ..config import settings
from ..downsampler import lttb_downsample
from ..models import DataPoint, QueryRequest, QueryResponse, QueryStats, SignalData

router = APIRouter()


def _extract_partition_date(path: Path) -> Optional[date]:
    """Extract date from Hive partition path like .../year=2024/month=1/day=15/..."""
    parts: Dict[str, int] = {}
    for part in path.parts:
        if "=" in part:
            k, _, v = part.partition("=")
            if k in ("year", "month", "day"):
                try:
                    parts[k] = int(v)
                except ValueError:
                    pass
    if len(parts) == 3:
        try:
            return date(parts["year"], parts["month"], parts["day"])
        except ValueError:
            pass
    return None


@router.post("/{vehicle_id}/query", response_model=QueryResponse)
async def query_signals(vehicle_id: str, request: QueryRequest):
    """Query time-series signal data with downsampling."""
    if settings.local_mode:
        return query_signals_local(vehicle_id, request)
    else:
        return query_signals_athena(vehicle_id, request)


def query_signals_local(vehicle_id: str, request: QueryRequest) -> QueryResponse:
    """Query signals from local Parquet files."""
    start_time_wall = time.time()

    data_dir = Path(settings.local_data_dir)
    vehicle_dir = data_dir / f"vehicle_id={vehicle_id}"

    if not vehicle_dir.exists():
        raise HTTPException(status_code=404, detail="Vehicle not found")

    start_ts_ns = int(request.start_time.timestamp() * 1e9)
    end_ts_ns = int(request.end_time.timestamp() * 1e9)
    query_start_date = request.start_time.date()
    query_end_date = request.end_time.date()

    # O(1) lookup for requested (message, signal) pairs
    requested = {(s.message_name, s.signal_name) for s in request.signals}
    requested_msg_names = pa.array(
        list({s.message_name for s in request.signals}), type=pa.string()
    )

    all_data: Dict[str, List[Tuple[float, float]]] = {}
    rows_scanned = 0
    bytes_scanned = 0

    for parquet_file in vehicle_dir.rglob("*.parquet"):
        # Partition pruning: skip files whose day is outside the query range
        file_date = _extract_partition_date(parquet_file)
        if file_date is not None and not (query_start_date <= file_date <= query_end_date):
            continue

        table = pq.ParquetFile(parquet_file).read(
            columns=["timestamp", "message_name", "signal_name", "value"]
        )
        bytes_scanned += parquet_file.stat().st_size

        if len(table) == 0:
            continue

        # Vectorized filter: keep only rows for requested message names
        msg_mask = pc.is_in(table.column("message_name"), value_set=requested_msg_names)
        table = table.filter(msg_mask)
        if len(table) == 0:
            continue

        # Vectorized filter: keep only rows within the time range
        ts_col = table.column("timestamp")
        ts_int = pc.cast(ts_col, pa.int64()) if pa.types.is_timestamp(ts_col.type) else ts_col
        time_mask = pc.and_(
            pc.greater_equal(ts_int, pa.scalar(start_ts_ns, type=pa.int64())),
            pc.less_equal(ts_int, pa.scalar(end_ts_ns, type=pa.int64())),
        )
        table = table.filter(time_mask)
        if len(table) == 0:
            continue

        timestamps_raw = table.column("timestamp").to_pylist()
        message_names_list = table.column("message_name").to_pylist()
        signal_names_list = table.column("signal_name").to_pylist()
        values_list = table.column("value").to_pylist()

        for ts, msg_name, sig_name, value in zip(
            timestamps_raw, message_names_list, signal_names_list, values_list
        ):
            if (msg_name, sig_name) not in requested:
                continue

            ts_ns = ts.value if hasattr(ts, "value") else int(ts.timestamp() * 1e9)
            key = f"{msg_name}.{sig_name}"
            if key not in all_data:
                all_data[key] = []
            all_data[key].append((ts_ns / 1e6, float(value)))
            rows_scanned += 1

    # Apply downsampling and format response
    signal_responses = []
    for req_sig in request.signals:
        key = f"{req_sig.message_name}.{req_sig.signal_name}"
        if key not in all_data:
            continue
        points = sorted(all_data[key], key=lambda p: p[0])
        if request.stride is not None:
            points = points[::request.stride]
        elif len(points) > request.max_points:
            points = lttb_downsample(points, request.max_points)
        data_points = [DataPoint(t=int(t), v=v) for t, v in points]
        signal_responses.append(SignalData(
            name=req_sig.signal_name,
            unit="",
            data=data_points,
        ))

    duration_ms = int((time.time() - start_time_wall) * 1000)
    return QueryResponse(
        signals=signal_responses,
        query_stats=QueryStats(
            rows_scanned=rows_scanned,
            bytes_scanned=bytes_scanned,
            duration_ms=duration_ms,
        ),
    )


def query_signals_athena(vehicle_id: str, request: QueryRequest) -> QueryResponse:
    """Query signals from Athena."""
    start_time = time.time()

    client = AthenaClient()

    # Build signal filter
    signal_filters = []
    for sig in request.signals:
        signal_filters.append(
            f"(message_name = '{sig.message_name}' AND signal_name = '{sig.signal_name}')"
        )

    signal_filter_str = " OR ".join(signal_filters)

    # Convert timestamps to nanoseconds (bigint) to match Athena table schema
    start_ts_ns = int(request.start_time.timestamp() * 1e9)
    end_ts_ns = int(request.end_time.timestamp() * 1e9)

    # Build SQL query with LIMIT to prevent excessive data scanning
    # Note: We apply downsampling after fetching, so we fetch more than max_points
    fetch_limit = min(request.max_points * 100, 500000)  # Cap at 500k rows

    sql = f"""
    SELECT timestamp, message_name, signal_name, value, unit
    FROM decoded
    WHERE vehicle_id = '{vehicle_id}'
      AND timestamp BETWEEN {start_ts_ns} AND {end_ts_ns}
      AND ({signal_filter_str})
    ORDER BY timestamp
    LIMIT {fetch_limit}
    """

    try:
        results = client.run_query(sql)

        # Group by signal
        signal_data: Dict[str, List[Tuple[float, float]]] = {}
        signal_units: Dict[str, str] = {}

        for row in results:
            # print(f"ROW KEYS: {list(row.keys())}")
            # print(f"ROW DATA: {row}")
            key = f"{row['message_name']}.{row['signal_name']}"

            if key not in signal_data:
                signal_data[key] = []
                signal_units[key] = row.get("unit", "")

            # Convert timestamp from nanoseconds (bigint) to milliseconds
            ts_ns = int(row["timestamp"])
            ts_ms = ts_ns / 1e6  # nanoseconds to milliseconds
            value = float(row["value"])

            signal_data[key].append((ts_ms, value))

        # Apply downsampling
        signal_responses = []

        for req_sig in request.signals:
            key = f"{req_sig.message_name}.{req_sig.signal_name}"

            if key not in signal_data:
                continue

            points = sorted(signal_data[key], key=lambda p: p[0])

            if request.stride is not None:
                points = points[::request.stride]
            elif len(points) > request.max_points:
                points = lttb_downsample(points, request.max_points)

            data_points = [DataPoint(t=int(t), v=v) for t, v in points]

            signal_responses.append(SignalData(
                name=req_sig.signal_name,
                unit=signal_units.get(key, ""),
                data=data_points,
            ))

        duration_ms = int((time.time() - start_time) * 1000)

        return QueryResponse(
            signals=signal_responses,
            query_stats=QueryStats(
                rows_scanned=len(results),
                bytes_scanned=0,  # Would need to get from query execution
                duration_ms=duration_ms,
            ),
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
