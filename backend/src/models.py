"""Pydantic models for API request/response schemas."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    """Vehicle information."""

    vehicle_id: str
    first_seen: datetime
    last_seen: datetime
    frame_count: int


class Session(BaseModel):
    """Recording session (day of data)."""

    date: str
    start_time: datetime
    end_time: datetime
    sample_count: int


class Message(BaseModel):
    """CAN message information."""

    message_name: str
    sample_count: int


class Signal(BaseModel):
    """Signal information."""

    signal_name: str
    unit: str
    min_value: float
    max_value: float
    avg_value: float


class SignalRequest(BaseModel):
    """Signal identifier for query."""

    message_name: str
    signal_name: str


class QueryRequest(BaseModel):
    """Time-series query request."""

    signals: List[SignalRequest] = Field(..., min_length=1)
    start_time: datetime
    end_time: datetime
    max_points: int = Field(default=2000, ge=10, le=100000)


class DataPoint(BaseModel):
    """Single time-series data point."""

    t: int  # Timestamp in milliseconds since epoch
    v: float  # Value


class SignalData(BaseModel):
    """Time-series data for a single signal."""

    name: str
    unit: str
    data: List[DataPoint]


class QueryStats(BaseModel):
    """Query execution statistics."""

    rows_scanned: int
    bytes_scanned: int
    duration_ms: int


class QueryResponse(BaseModel):
    """Time-series query response."""

    signals: List[SignalData]
    query_stats: QueryStats


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    mode: str
