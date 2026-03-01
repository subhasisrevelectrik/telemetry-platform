"""Chat router — AI telemetry assistant powered by Claude."""

import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services.anthropic_client import run_chat
from ..services.chat_tools import execute_tool

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# conversation_id → {messages, last_activity, rate_timestamps}
_conversations: Dict[str, Dict[str, Any]] = {}

# Usage tracking (reset daily)
_usage: Dict[str, Any] = {
    "date": datetime.utcnow().date().isoformat(),
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_calls": 0,
}

# Constants
_MAX_HISTORY = 20          # sliding window of messages kept per conversation
_CONVERSATION_TTL = 1800   # seconds — 30 minutes inactivity
_RATE_LIMIT_WINDOW = 60    # seconds
_RATE_LIMIT_MAX = 20       # max messages per _RATE_LIMIT_WINDOW
_DAILY_TOKEN_WARN = 1_000_000


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Incoming chat message."""

    message: str
    conversation_id: Optional[str] = None
    vehicle_context: Optional[str] = None


class ChatResponse(BaseModel):
    """Outgoing chat response."""

    conversation_id: str
    response: Dict[str, Any]


class UsageResponse(BaseModel):
    """Chat usage statistics."""

    date: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_calls: int
    avg_tokens_per_call: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_create_conversation(conversation_id: Optional[str]) -> tuple[str, Dict]:
    """Return (conversation_id, conversation_dict), creating one if needed."""
    _purge_expired_conversations()

    if conversation_id and conversation_id in _conversations:
        conv = _conversations[conversation_id]
        conv["last_activity"] = datetime.utcnow()
        return conversation_id, conv

    new_id = str(uuid4())
    _conversations[new_id] = {
        "messages": [],
        "last_activity": datetime.utcnow(),
        "rate_timestamps": deque(),
    }
    return new_id, _conversations[new_id]


def _purge_expired_conversations() -> None:
    """Remove conversations inactive longer than TTL."""
    cutoff = datetime.utcnow() - timedelta(seconds=_CONVERSATION_TTL)
    expired = [cid for cid, c in _conversations.items() if c["last_activity"] < cutoff]
    for cid in expired:
        del _conversations[cid]


def _check_rate_limit(conv: Dict) -> None:
    """Raise 429 if the session has exceeded the rate limit."""
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    timestamps: Deque[float] = conv["rate_timestamps"]

    # Remove timestamps outside the window
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_RATE_LIMIT_MAX} messages per {_RATE_LIMIT_WINDOW}s",
        )

    timestamps.append(now)


def _enforce_history_cap(messages: List) -> None:
    """Trim history to _MAX_HISTORY messages (keep newest)."""
    if len(messages) > _MAX_HISTORY:
        del messages[: len(messages) - _MAX_HISTORY]


def _reset_usage_if_new_day() -> None:
    """Reset daily usage counters if the date has changed."""
    today = datetime.utcnow().date().isoformat()
    if _usage["date"] != today:
        _usage.update(
            {
                "date": today,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_calls": 0,
            }
        )


def _record_usage(input_tokens: int, output_tokens: int) -> None:
    """Accumulate token usage and warn if daily threshold is crossed."""
    _reset_usage_if_new_day()
    _usage["total_input_tokens"] += input_tokens
    _usage["total_output_tokens"] += output_tokens
    _usage["total_calls"] += 1

    total_today = _usage["total_input_tokens"] + _usage["total_output_tokens"]
    if total_today >= _DAILY_TOKEN_WARN:
        logger.warning(
            "Daily token usage has reached %d (threshold: %d)", total_today, _DAILY_TOKEN_WARN
        )


def _get_vehicle_info(vehicle_id: Optional[str]) -> Optional[Dict]:
    """Fetch vehicle metadata for the system prompt (best-effort)."""
    if not vehicle_id:
        return None
    try:
        result = execute_tool("list_vehicles", {})
        for v in result.get("vehicles", []):
            if v["vehicle_id"] == vehicle_id:
                return v
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the AI telemetry assistant.

    The assistant has access to tools that query vehicles, signals, and
    time-series data from the telemetry database.
    """
    # --- 1. Check API key ---
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chat feature requires ANTHROPIC_API_KEY to be configured. "
                "Add ANTHROPIC_API_KEY=<your-key> to the backend .env file."
            ),
        )

    # --- 2. Get / create conversation ---
    conv_id, conv = _get_or_create_conversation(request.conversation_id)

    # --- 3. Rate limit check ---
    _check_rate_limit(conv)

    # --- 4. Get vehicle context ---
    vehicle_info = _get_vehicle_info(request.vehicle_context)

    # --- 5. Run Claude with tool-use loop ---
    try:
        result = run_chat(
            user_message=request.message,
            conversation_history=conv["messages"],
            vehicle_id=request.vehicle_context,
            vehicle_info=vehicle_info,
            api_key=settings.anthropic_api_key,
        )
    except Exception as exc:
        logger.exception("Claude API call failed")
        raise HTTPException(
            status_code=502,
            detail=f"AI service error: {str(exc)}",
        )

    # --- 6. Trim history ---
    _enforce_history_cap(conv["messages"])
    conv["last_activity"] = datetime.utcnow()

    # --- 7. Record usage ---
    _record_usage(result["input_tokens"], result["output_tokens"])

    return ChatResponse(
        conversation_id=conv_id,
        response={
            "text": result["text"],
            "charts": result["charts"],
            "anomalies": result["anomalies"],
            "suggestions": result["suggestions"],
        },
    )


@router.get("/chat/usage", response_model=UsageResponse)
async def get_usage() -> UsageResponse:
    """
    Return today's API usage statistics.

    This endpoint is intended for administrators to monitor costs.
    """
    _reset_usage_if_new_day()
    total = _usage["total_input_tokens"] + _usage["total_output_tokens"]
    calls = _usage["total_calls"]
    return UsageResponse(
        date=_usage["date"],
        total_input_tokens=_usage["total_input_tokens"],
        total_output_tokens=_usage["total_output_tokens"],
        total_tokens=total,
        total_calls=calls,
        avg_tokens_per_call=total / calls if calls > 0 else 0.0,
    )
