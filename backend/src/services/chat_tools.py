"""Tool definitions and execution logic for the Claude chatbot."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import settings
from ..models import QueryRequest, SignalRequest
from ..routers.messages import get_messages_local, get_messages_athena
from ..routers.signals import get_signals_local, get_signals_athena
from ..routers.vehicles import list_vehicles_local, list_vehicles_athena
from ..routers.query import query_signals_local, query_signals_athena
from .anomaly_detector import detect_anomalies

# ---------------------------------------------------------------------------
# Tool definitions for the Anthropic API
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: List[Dict] = [
    {
        "name": "list_vehicles",
        "description": (
            "List all vehicles in the telemetry database with their data time ranges "
            "and frame counts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_messages",
        "description": (
            "List all CAN messages available for a vehicle. Returns message names "
            "and sample counts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {
                    "type": "string",
                    "description": "Vehicle identifier",
                }
            },
            "required": ["vehicle_id"],
        },
    },
    {
        "name": "list_signals",
        "description": (
            "List all signals within a specific CAN message for a vehicle. "
            "Returns signal names, units, and min/max/avg statistics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "string"},
                "message_name": {
                    "type": "string",
                    "description": "CAN message name (e.g., 'BMS_PackStatus')",
                },
            },
            "required": ["vehicle_id", "message_name"],
        },
    },
    {
        "name": "query_signals",
        "description": (
            "Query time-series data for one or more signals. Returns timestamped values. "
            "Use this to fetch data for charts, analysis, and anomaly detection."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "string"},
                "signals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "message_name": {"type": "string"},
                            "signal_name": {"type": "string"},
                        },
                        "required": ["message_name", "signal_name"],
                    },
                    "description": "Signals to query",
                },
                "start_time": {
                    "type": "string",
                    "description": "ISO 8601 start time",
                },
                "end_time": {
                    "type": "string",
                    "description": "ISO 8601 end time",
                },
                "max_points": {
                    "type": "integer",
                    "description": "Maximum data points per signal (default 2000)",
                },
            },
            "required": ["vehicle_id", "signals", "start_time", "end_time"],
        },
    },
    {
        "name": "compute_statistics",
        "description": (
            "Compute statistics on signal data: min, max, mean, std_dev, percentiles, "
            "and detect anomalies. Use this to analyze signal quality or find threshold violations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": "string"},
                "signal": {
                    "type": "object",
                    "properties": {
                        "message_name": {"type": "string"},
                        "signal_name": {"type": "string"},
                    },
                    "required": ["message_name", "signal_name"],
                },
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "threshold_low": {
                    "type": "number",
                    "description": "Flag values below this threshold",
                },
                "threshold_high": {
                    "type": "number",
                    "description": "Flag values above this threshold",
                },
                "std_dev_threshold": {
                    "type": "number",
                    "description": "Flag values beyond N standard deviations from mean (default: 3)",
                },
            },
            "required": ["vehicle_id", "signal", "start_time", "end_time"],
        },
    },
    {
        "name": "generate_chart",
        "description": (
            "Generate a chart configuration that the frontend will render. Use this "
            "when the user asks to visualize data. The chart will be rendered "
            "interactively by the frontend using Plotly.js."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["time_series", "histogram", "scatter", "box_plot"],
                    "description": "Type of chart to generate",
                },
                "title": {"type": "string"},
                "signals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "vehicle_id": {"type": "string"},
                            "message_name": {"type": "string"},
                            "signal_name": {"type": "string"},
                            "y_axis": {
                                "type": "string",
                                "enum": ["left", "right"],
                                "description": "Which Y axis (for dual-axis charts)",
                            },
                        },
                        "required": ["vehicle_id", "message_name", "signal_name"],
                    },
                },
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "max_points": {"type": "integer"},
                "annotations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "timestamp": {"type": "string"},
                            "label": {"type": "string"},
                            "color": {"type": "string"},
                        },
                    },
                    "description": "Annotations to overlay on the chart",
                },
                "threshold_lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number"},
                            "label": {"type": "string"},
                            "color": {"type": "string"},
                            "signal_name": {"type": "string"},
                        },
                    },
                    "description": "Horizontal threshold lines",
                },
            },
            "required": ["chart_type", "title", "signals", "start_time", "end_time"],
        },
    },
    {
        "name": "propose_suggestions",
        "description": (
            "Propose 2-3 follow-up questions or actions for the user to explore next. "
            "Call this at the end of your response to help the user continue their analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-3 concise follow-up suggestions",
                }
            },
            "required": ["suggestions"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


def _get_vehicle_info(vehicle_id: Optional[str]) -> Optional[Dict]:
    """Return a vehicle dict if vehicle_id is set, else None."""
    if not vehicle_id:
        return None
    vehicles = list_vehicles_local() if settings.local_mode else list_vehicles_athena()
    for v in vehicles:
        if v.vehicle_id == vehicle_id:
            return {
                "vehicle_id": v.vehicle_id,
                "first_seen": v.first_seen.isoformat(),
                "last_seen": v.last_seen.isoformat(),
                "frame_count": v.frame_count,
            }
    return None


def execute_tool(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool call and return a JSON-serialisable result dict."""

    if name == "list_vehicles":
        vehicles = list_vehicles_local() if settings.local_mode else list_vehicles_athena()
        return {
            "vehicles": [
                {
                    "vehicle_id": v.vehicle_id,
                    "first_seen": v.first_seen.isoformat(),
                    "last_seen": v.last_seen.isoformat(),
                    "frame_count": v.frame_count,
                }
                for v in vehicles
            ]
        }

    elif name == "list_messages":
        vehicle_id = tool_input["vehicle_id"]
        msgs = (
            get_messages_local(vehicle_id)
            if settings.local_mode
            else get_messages_athena(vehicle_id)
        )
        return {
            "vehicle_id": vehicle_id,
            "messages": [
                {"message_name": m.message_name, "sample_count": m.sample_count}
                for m in msgs
            ],
        }

    elif name == "list_signals":
        vehicle_id = tool_input["vehicle_id"]
        message_name = tool_input["message_name"]
        sigs = (
            get_signals_local(vehicle_id, message_name)
            if settings.local_mode
            else get_signals_athena(vehicle_id, message_name)
        )
        return {
            "vehicle_id": vehicle_id,
            "message_name": message_name,
            "signals": [
                {
                    "signal_name": s.signal_name,
                    "unit": s.unit,
                    "min_value": s.min_value,
                    "max_value": s.max_value,
                    "avg_value": s.avg_value,
                }
                for s in sigs
            ],
        }

    elif name == "query_signals":
        vehicle_id = tool_input["vehicle_id"]
        signals_input = tool_input["signals"]
        start_time = datetime.fromisoformat(tool_input["start_time"].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(tool_input["end_time"].replace("Z", "+00:00"))
        max_points = int(tool_input.get("max_points", 2000))

        request = QueryRequest(
            signals=[
                SignalRequest(
                    message_name=s["message_name"],
                    signal_name=s["signal_name"],
                )
                for s in signals_input
            ],
            start_time=start_time,
            end_time=end_time,
            max_points=max_points,
        )

        response = (
            query_signals_local(vehicle_id, request)
            if settings.local_mode
            else query_signals_athena(vehicle_id, request)
        )

        # Return compact summary to Claude (avoid filling context with raw data)
        return {
            "vehicle_id": vehicle_id,
            "signals_returned": len(response.signals),
            "signal_summaries": [
                {
                    "name": s.name,
                    "unit": s.unit,
                    "points": len(s.data),
                    "min": min((p.v for p in s.data), default=0),
                    "max": max((p.v for p in s.data), default=0),
                    "mean": (
                        sum(p.v for p in s.data) / len(s.data) if s.data else 0
                    ),
                }
                for s in response.signals
            ],
            "query_stats": {
                "rows_scanned": response.query_stats.rows_scanned,
                "duration_ms": response.query_stats.duration_ms,
            },
        }

    elif name == "compute_statistics":
        vehicle_id = tool_input["vehicle_id"]
        signal = tool_input["signal"]
        start_time = datetime.fromisoformat(tool_input["start_time"].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(tool_input["end_time"].replace("Z", "+00:00"))

        request = QueryRequest(
            signals=[
                SignalRequest(
                    message_name=signal["message_name"],
                    signal_name=signal["signal_name"],
                )
            ],
            start_time=start_time,
            end_time=end_time,
            max_points=10000,
        )

        response = (
            query_signals_local(vehicle_id, request)
            if settings.local_mode
            else query_signals_athena(vehicle_id, request)
        )

        if not response.signals:
            return {"error": "No data found for the requested signal and time range"}

        signal_data = response.signals[0]
        timestamps = [
            datetime.fromtimestamp(p.t / 1000).isoformat() for p in signal_data.data
        ]
        values = [p.v for p in signal_data.data]

        stats = detect_anomalies(
            timestamps=timestamps,
            values=values,
            threshold_low=tool_input.get("threshold_low"),
            threshold_high=tool_input.get("threshold_high"),
            std_dev_threshold=float(tool_input.get("std_dev_threshold", 3.0)),
        )

        return {
            "vehicle_id": vehicle_id,
            "signal_name": signal["signal_name"],
            "message_name": signal["message_name"],
            "unit": signal_data.unit,
            **stats,
        }

    elif name == "generate_chart":
        # Return a placeholder — the actual data fetch happens in the chat router
        # after the tool-use loop completes.
        return {
            "status": "chart_queued",
            "chart_type": tool_input.get("chart_type", "time_series"),
            "title": tool_input.get("title", "Chart"),
            "signals": len(tool_input.get("signals", [])),
        }

    elif name == "propose_suggestions":
        return {"status": "suggestions_noted"}

    else:
        return {"error": f"Unknown tool: {name}"}


def fetch_chart_data(chart_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Fetch actual signal data for a generate_chart tool call and return
    a complete chart dict suitable for the frontend.
    """
    signals_spec = chart_config.get("signals", [])
    if not signals_spec:
        return None

    start_time_str = chart_config.get("start_time", "")
    end_time_str = chart_config.get("end_time", "")

    try:
        start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    max_points = int(chart_config.get("max_points", 2000))

    # Group signals by vehicle (usually all the same vehicle)
    by_vehicle: Dict[str, List] = {}
    for sig in signals_spec:
        vid = sig.get("vehicle_id", "")
        if vid not in by_vehicle:
            by_vehicle[vid] = []
        by_vehicle[vid].append(sig)

    chart_data: Dict[str, Dict] = {}

    for vehicle_id, sigs in by_vehicle.items():
        request = QueryRequest(
            signals=[
                SignalRequest(
                    message_name=s["message_name"],
                    signal_name=s["signal_name"],
                )
                for s in sigs
            ],
            start_time=start_time,
            end_time=end_time,
            max_points=max_points,
        )

        try:
            response = (
                query_signals_local(vehicle_id, request)
                if settings.local_mode
                else query_signals_athena(vehicle_id, request)
            )
        except Exception:
            continue

        for sig_resp in response.signals:
            # Find matching spec to get y_axis preference
            y_axis = "left"
            for spec in sigs:
                if spec["signal_name"] == sig_resp.name:
                    y_axis = spec.get("y_axis", "left")
                    break

            # Find message name for the key
            message_name = ""
            for spec in sigs:
                if spec["signal_name"] == sig_resp.name:
                    message_name = spec["message_name"]
                    break

            key = f"{message_name}.{sig_resp.name}"
            chart_data[key] = {
                "timestamps": [
                    datetime.fromtimestamp(p.t / 1000).isoformat() + "Z"
                    for p in sig_resp.data
                ],
                "values": [p.v for p in sig_resp.data],
                "unit": sig_resp.unit,
                "y_axis": y_axis,
            }

    if not chart_data:
        return None

    return {
        "chart_type": chart_config.get("chart_type", "time_series"),
        "title": chart_config.get("title", "Chart"),
        "data": chart_data,
        "threshold_lines": chart_config.get("threshold_lines", []),
        "annotations": chart_config.get("annotations", []),
        "start_time": start_time_str,
        "end_time": end_time_str,
    }
