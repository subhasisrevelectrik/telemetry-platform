"""Statistical anomaly detection for CAN telemetry signals."""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Anomaly:
    """A detected anomaly in a signal."""

    timestamp: str
    value: float
    reason: str
    severity: str  # "warning" | "critical"


def _percentile(sorted_values: List[float], p: float) -> float:
    """Compute a percentile from a sorted list."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def detect_anomalies(
    timestamps: List[str],
    values: List[float],
    threshold_low: Optional[float] = None,
    threshold_high: Optional[float] = None,
    std_dev_threshold: float = 3.0,
    rate_of_change_max: Optional[float] = None,
    flatline_duration_samples: int = 10,
) -> Dict:
    """
    Detect anomalies in time-series data using multiple methods.

    Args:
        timestamps:               ISO 8601 timestamp strings (one per value).
        values:                   Signal values aligned with timestamps.
        threshold_low:            Flag values strictly below this.
        threshold_high:           Flag values strictly above this.
        std_dev_threshold:        Flag values |z-score| > this (default 3.0).
        rate_of_change_max:       Flag consecutive delta > this value.
        flatline_duration_samples: Minimum run of identical consecutive values
                                   to be flagged as a flatline (default 10).

    Returns:
        dict with keys: min, max, mean, std_dev, p5, p50, p95,
        sample_count, anomalies (list of dicts).
    """
    if not values:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "std_dev": 0.0,
            "p5": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "sample_count": 0,
            "anomalies": [],
        }

    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    std = math.sqrt(variance)

    sorted_vals = sorted(values)

    anomalies: List[Anomaly] = []
    flagged_indices = set()

    # --- Threshold-based detection ---
    if threshold_low is not None:
        for i, v in enumerate(values):
            if v < threshold_low and i not in flagged_indices:
                flagged_indices.add(i)
                # Critical if more than 5% below threshold
                severity = "critical" if threshold_low != 0 and v < threshold_low * 0.95 else "warning"
                anomalies.append(
                    Anomaly(
                        timestamp=timestamps[i],
                        value=v,
                        reason=f"below threshold {threshold_low}",
                        severity=severity,
                    )
                )

    if threshold_high is not None:
        for i, v in enumerate(values):
            if v > threshold_high and i not in flagged_indices:
                flagged_indices.add(i)
                severity = "critical" if threshold_high != 0 and v > threshold_high * 1.05 else "warning"
                anomalies.append(
                    Anomaly(
                        timestamp=timestamps[i],
                        value=v,
                        reason=f"above threshold {threshold_high}",
                        severity=severity,
                    )
                )

    # --- Statistical outlier detection ---
    if std > 0:
        for i, v in enumerate(values):
            z = abs(v - mean) / std
            if z > std_dev_threshold and i not in flagged_indices:
                flagged_indices.add(i)
                anomalies.append(
                    Anomaly(
                        timestamp=timestamps[i],
                        value=v,
                        reason=f"{z:.1f} std_dev from mean",
                        severity="warning",
                    )
                )

    # --- Rate-of-change detection ---
    if rate_of_change_max is not None and n >= 2:
        for i in range(1, n):
            delta = abs(values[i] - values[i - 1])
            if delta > rate_of_change_max and i not in flagged_indices:
                flagged_indices.add(i)
                anomalies.append(
                    Anomaly(
                        timestamp=timestamps[i],
                        value=values[i],
                        reason=f"rapid change: Δ={delta:.3g}",
                        severity="warning",
                    )
                )

    # --- Flatline detection ---
    if flatline_duration_samples >= 2 and n >= flatline_duration_samples:
        run_start = 0
        for i in range(1, n):
            if values[i] != values[run_start]:
                run_len = i - run_start
                if run_len >= flatline_duration_samples:
                    mid = run_start + run_len // 2
                    if mid not in flagged_indices:
                        flagged_indices.add(mid)
                        anomalies.append(
                            Anomaly(
                                timestamp=timestamps[mid],
                                value=values[mid],
                                reason=f"flatline: {run_len} identical samples",
                                severity="warning",
                            )
                        )
                run_start = i

        # Check final run
        run_len = n - run_start
        if run_len >= flatline_duration_samples:
            mid = run_start + run_len // 2
            if mid not in flagged_indices:
                anomalies.append(
                    Anomaly(
                        timestamp=timestamps[mid],
                        value=values[mid],
                        reason=f"flatline: {run_len} identical samples",
                        severity="warning",
                    )
                )

    # Sort anomalies by timestamp order (they appear in insertion order mostly)
    anomaly_dicts = [
        {
            "timestamp": a.timestamp,
            "value": a.value,
            "reason": a.reason,
            "severity": a.severity,
        }
        for a in anomalies
    ]

    return {
        "min": min(values),
        "max": max(values),
        "mean": mean,
        "std_dev": std,
        "p5": _percentile(sorted_vals, 5),
        "p50": _percentile(sorted_vals, 50),
        "p95": _percentile(sorted_vals, 95),
        "sample_count": n,
        "anomalies": anomaly_dicts,
    }
