"""Claude API integration with tool use for the telemetry chatbot."""

import json
import logging
from typing import Any, Dict, List, Optional

import anthropic

from .chat_tools import TOOL_DEFINITIONS, execute_tool, fetch_chart_data

logger = logging.getLogger(__name__)

MODEL_ID = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_TOOL_ITERATIONS = 10

SYSTEM_PROMPT_TEMPLATE = """You are a telemetry data analyst assistant embedded in a CAN Bus Telemetry Dashboard.
You help engineers explore, visualize, and analyze vehicle CAN bus data.

You have access to tools to query the telemetry database.
When a user asks to see data, visualize signals, or analyze trends, use the appropriate tools
to fetch the data and then describe what you see in clear, technical language.

When generating chart configurations, always use the exact signal names and message names
from the tools — never guess or invent names.

{vehicle_context}

For anomaly detection, compute statistics from the queried data and flag values that exceed
the user's stated thresholds or that are more than 3 standard deviations from the mean.

For general EV/CAN bus questions, draw on your knowledge of:
- CAN bus protocol (2.0A/B, CAN-FD), arbitration, bit timing, error handling
- Battery management systems (SOC, SOH, cell balancing, thermal management, charging)
- Electric powertrain (motor controllers, inverters, DC-DC converters, regenerative braking)
- DBC file format, signal encoding/decoding (factor, offset, byte order)
- OBD-II standards, UDS diagnostics, J1939 protocol

Keep responses concise and technical. After answering, call propose_suggestions with 2-3
relevant follow-up questions or analyses the engineer might find useful."""


def _build_vehicle_context(vehicle_id: Optional[str], vehicle_info: Optional[Dict]) -> str:
    """Build the vehicle context section of the system prompt."""
    if not vehicle_id:
        return "No vehicle is currently selected. You can still answer general questions."
    if vehicle_info:
        return (
            f"The current vehicle context is: {vehicle_id}\n"
            f"Available time range: {vehicle_info.get('first_seen', 'unknown')} "
            f"to {vehicle_info.get('last_seen', 'unknown')}\n"
            f"Total frame count: {vehicle_info.get('frame_count', 'unknown')}"
        )
    return f"The current vehicle context is: {vehicle_id}"


def _extract_text(content_blocks: List[Any]) -> str:
    """Extract concatenated text from Anthropic content blocks."""
    parts = []
    for block in content_blocks:
        if hasattr(block, "text") and block.text:
            parts.append(block.text.strip())
    return "\n".join(parts).strip()


def run_chat(
    user_message: str,
    conversation_history: List[Dict],
    vehicle_id: Optional[str],
    vehicle_info: Optional[Dict],
    api_key: str,
) -> Dict[str, Any]:
    """
    Run one user turn through the Claude tool-use agentic loop.

    Args:
        user_message:        The user's message text.
        conversation_history: Previous messages in Anthropic format (mutated in-place).
        vehicle_id:          Currently selected vehicle (may be None).
        vehicle_info:        Vehicle metadata dict from list_vehicles tool.
        api_key:             Anthropic API key.

    Returns:
        dict with keys: text, charts, anomalies, suggestions, input_tokens, output_tokens
    """
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        vehicle_context=_build_vehicle_context(vehicle_id, vehicle_info)
    )

    # Append the new user message
    messages = list(conversation_history)
    messages.append({"role": "user", "content": user_message})

    charts: List[Dict] = []
    anomalies: List[Dict] = []
    suggestions: List[str] = []
    total_input_tokens = 0
    total_output_tokens = 0
    accumulated_text_parts: List[str] = []

    # Collect generate_chart tool inputs so we can fetch data after the loop
    pending_chart_configs: List[Dict] = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        logger.info(
            "Claude response: stop_reason=%s, tokens=%d+%d (iter=%d)",
            response.stop_reason,
            response.usage.input_tokens,
            response.usage.output_tokens,
            iteration,
        )

        # Accumulate text from every assistant turn (not just the last)
        turn_text = _extract_text(response.content)
        if turn_text:
            accumulated_text_parts.append(turn_text)

        # Append assistant message to history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Final text response
            break

        # Execute tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            logger.info("Executing tool: %s, input: %s", tool_name, json.dumps(tool_input)[:200])

            # Special handling for generate_chart — queue it, return placeholder
            if tool_name == "generate_chart":
                # Attach vehicle_id to each signal spec if missing
                for sig in tool_input.get("signals", []):
                    if not sig.get("vehicle_id") and vehicle_id:
                        sig["vehicle_id"] = vehicle_id
                pending_chart_configs.append(tool_input)
                result = {
                    "status": "chart_queued",
                    "chart_type": tool_input.get("chart_type"),
                    "title": tool_input.get("title"),
                    "signals": len(tool_input.get("signals", [])),
                    "message": "Chart data will be included in the final response.",
                }
            elif tool_name == "propose_suggestions":
                suggestions = tool_input.get("suggestions", [])
                result = {"status": "suggestions_noted"}
            else:
                try:
                    result = execute_tool(tool_name, tool_input)
                    # Collect anomaly results
                    if tool_name == "compute_statistics" and "anomalies" in result:
                        anomalies.append(result)
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name)
                    result = {"error": str(exc)}

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )

        # Feed tool results back to Claude
        messages.append({"role": "user", "content": tool_results})

    # Combine text accumulated across all assistant turns
    final_text = "\n".join(accumulated_text_parts).strip()

    # Fetch actual chart data for all queued charts
    for chart_config in pending_chart_configs:
        chart_data = fetch_chart_data(chart_config)
        if chart_data:
            charts.append(chart_data)

    # Update conversation history in-place so the caller can persist it
    conversation_history.clear()
    conversation_history.extend(messages)

    return {
        "text": final_text,
        "charts": charts,
        "anomalies": anomalies,
        "suggestions": suggestions,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
