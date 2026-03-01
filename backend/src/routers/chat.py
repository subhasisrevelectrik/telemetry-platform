"""Chat router — AI telemetry assistant powered by Claude.

Architecture (production):
  POST /chat              → creates a job, invokes Lambda asynchronously, returns job_id immediately
  GET  /chat/status/{id} → polls S3 for job result (pending | complete | error)

The async Lambda invocation bypasses API Gateway's 29-second timeout.
Job state and conversation history are stored in S3 under the chat-jobs/ prefix.

Local dev (LOCAL_MODE=true or no S3_DATA_BUCKET):
  Falls back to in-memory storage and synchronous processing.
"""

import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services.anthropic_client import run_chat
from ..services.chat_tools import execute_tool

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_S3_BUCKET = os.environ.get("S3_DATA_BUCKET", "")
_JOBS_PREFIX = "chat-jobs/jobs"
_CONV_PREFIX = "chat-jobs/conversations"
_FUNCTION_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")
_LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() == "true" or not _S3_BUCKET

# ---------------------------------------------------------------------------
# In-memory fallback for local dev
# ---------------------------------------------------------------------------

_local_jobs: Dict[str, dict] = {}
_local_conversations: Dict[str, List] = {}

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per conversation ID)
# ---------------------------------------------------------------------------

_rate_state: Dict[str, Deque[float]] = {}
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 20
_MAX_HISTORY = 20
_DAILY_TOKEN_WARN = 1_000_000

_usage: Dict[str, Any] = {
    "date": datetime.utcnow().date().isoformat(),
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_calls": 0,
}

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Incoming chat message."""

    message: str
    conversation_id: Optional[str] = None
    vehicle_context: Optional[str] = None


class ChatStartResponse(BaseModel):
    """Returned immediately from POST /chat — client polls for the result."""

    job_id: str
    conversation_id: str


class JobStatusResponse(BaseModel):
    """Returned by GET /chat/status/{job_id}."""

    status: str  # "pending" | "complete" | "error"
    response: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None
    error: Optional[str] = None


class UsageResponse(BaseModel):
    """Chat usage statistics."""

    date: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_calls: int
    avg_tokens_per_call: float


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------


def _s3():
    return boto3.client("s3")


def _write_job(job_id: str, data: dict) -> None:
    if _LOCAL_MODE:
        _local_jobs[job_id] = data
        return
    _s3().put_object(
        Bucket=_S3_BUCKET,
        Key=f"{_JOBS_PREFIX}/{job_id}.json",
        Body=json.dumps(data, default=str),
        ContentType="application/json",
    )


def _read_job(job_id: str) -> Optional[dict]:
    if _LOCAL_MODE:
        return _local_jobs.get(job_id)
    try:
        resp = _s3().get_object(Bucket=_S3_BUCKET, Key=f"{_JOBS_PREFIX}/{job_id}.json")
        return json.loads(resp["Body"].read())
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return None
        raise


def _serialize_content(content: Any) -> Any:
    """Convert Anthropic SDK content blocks to plain dicts for JSON storage."""
    if isinstance(content, list):
        return [_serialize_content(b) for b in content]
    if hasattr(content, "model_dump"):
        return content.model_dump()
    return content


def _serialize_messages(messages: List[Dict]) -> List[Dict]:
    return [{"role": m["role"], "content": _serialize_content(m["content"])} for m in messages]


def _write_conversation(conv_id: str, messages: List[Dict]) -> None:
    serialized = _serialize_messages(messages)
    if _LOCAL_MODE:
        _local_conversations[conv_id] = serialized
        return
    _s3().put_object(
        Bucket=_S3_BUCKET,
        Key=f"{_CONV_PREFIX}/{conv_id}.json",
        Body=json.dumps(serialized, default=str),
        ContentType="application/json",
    )


def _read_conversation(conv_id: str) -> List[Dict]:
    if _LOCAL_MODE:
        return list(_local_conversations.get(conv_id, []))
    try:
        resp = _s3().get_object(Bucket=_S3_BUCKET, Key=f"{_CONV_PREFIX}/{conv_id}.json")
        return json.loads(resp["Body"].read())
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchKey":
            return []
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_rate_limit(session_id: str) -> None:
    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW
    if session_id not in _rate_state:
        _rate_state[session_id] = deque()
    timestamps = _rate_state[session_id]
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()
    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_RATE_LIMIT_MAX} messages per {_RATE_LIMIT_WINDOW}s",
        )
    timestamps.append(now)


def _reset_usage_if_new_day() -> None:
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


@router.post("/chat", response_model=ChatStartResponse)
async def chat(request: ChatRequest) -> ChatStartResponse:
    """
    Start an async chat job.

    Returns immediately with a job_id. Poll GET /chat/status/{job_id} for the result.
    This allows responses that exceed API Gateway's 29-second timeout.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chat feature requires ANTHROPIC_API_KEY to be configured. "
                "Add ANTHROPIC_API_KEY=<your-key> to the backend .env file."
            ),
        )

    conv_id = request.conversation_id or str(uuid4())
    _check_rate_limit(conv_id)

    job_id = str(uuid4())
    _write_job(job_id, {"status": "pending", "conversation_id": conv_id})

    if _LOCAL_MODE or not _FUNCTION_NAME:
        # Local dev: process synchronously so the first poll returns immediately
        _do_process_chat_job(job_id, request.message, conv_id, request.vehicle_context)
    else:
        # Production: invoke this Lambda asynchronously (bypasses API Gateway timeout)
        lambda_client = boto3.client("lambda")
        lambda_client.invoke(
            FunctionName=_FUNCTION_NAME,
            InvocationType="Event",  # async — returns 202, no response body
            Payload=json.dumps(
                {
                    "_job_type": "chat_process",
                    "job_id": job_id,
                    "message": request.message,
                    "conversation_id": conv_id,
                    "vehicle_context": request.vehicle_context,
                }
            ).encode(),
        )

    return ChatStartResponse(job_id=job_id, conversation_id=conv_id)


@router.get("/chat/status/{job_id}", response_model=JobStatusResponse)
async def get_chat_status(job_id: str) -> JobStatusResponse:
    """Poll for the result of an async chat job."""
    job = _read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job)


@router.get("/chat/usage", response_model=UsageResponse)
async def get_usage() -> UsageResponse:
    """Return today's API usage statistics."""
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


# ---------------------------------------------------------------------------
# Async job processor — called from lambda_handler, not via HTTP
# ---------------------------------------------------------------------------


def process_chat_job_async(event: dict) -> None:
    """Entry point for async Lambda invocation (not an HTTP handler)."""
    _do_process_chat_job(
        job_id=event["job_id"],
        message=event["message"],
        conv_id=event["conversation_id"],
        vehicle_context=event.get("vehicle_context"),
    )


def _do_process_chat_job(
    job_id: str,
    message: str,
    conv_id: str,
    vehicle_context: Optional[str],
) -> None:
    """Run the Claude tool-use loop and write the result to S3 (or in-memory)."""
    try:
        history = _read_conversation(conv_id)
        vehicle_info = _get_vehicle_info(vehicle_context)

        result = run_chat(
            user_message=message,
            conversation_history=history,
            vehicle_id=vehicle_context,
            vehicle_info=vehicle_info,
            api_key=settings.anthropic_api_key,
        )

        # run_chat mutates history in-place — trim and persist
        if len(history) > _MAX_HISTORY:
            del history[: len(history) - _MAX_HISTORY]
        _write_conversation(conv_id, history)

        _record_usage(result["input_tokens"], result["output_tokens"])

        _write_job(
            job_id,
            {
                "status": "complete",
                "conversation_id": conv_id,
                "response": {
                    "text": result["text"],
                    "charts": result["charts"],
                    "anomalies": result["anomalies"],
                    "suggestions": result["suggestions"],
                },
            },
        )
    except Exception as exc:
        logger.exception("Chat job %s failed", job_id)
        _write_job(
            job_id,
            {
                "status": "error",
                "conversation_id": conv_id,
                "error": str(exc),
            },
        )
