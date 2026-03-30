"""Anomaly scoring via z-scores.

Computes per-metric z-scores from the agent baseline, then produces a
composite anomaly score (0.0-1.0) via clipped RMS. All computation is
pure (no I/O), testable in isolation.
"""

import math

from src.layer1.behavioral.baselines import TRACKED_METRICS, AgentBaseline
from src.layer1.behavioral.metrics import extract_metric_value

COLD_START_THRESHOLD = 5  # Minimum sessions before scoring is meaningful
COLD_START_SCORE = 0.5
Z_SCORE_CLIP = 4.0  # Clip z-scores to prevent extreme outliers from dominating


def compute_z_scores(baseline: AgentBaseline, session_metrics: dict) -> dict[str, float]:
    """Compute per-metric z-scores against the agent's baseline.

    Args:
        baseline: Agent's current statistical baseline.
        session_metrics: Metrics from the current session.

    Returns:
        Dict mapping metric name to z-score.
    """
    z_scores: dict[str, float] = {}

    for metric_name in TRACKED_METRICS:
        stats = baseline.metrics.get(metric_name)
        if stats is None or stats.count < 2 or stats.std < 1e-10:
            z_scores[metric_name] = 0.0
            continue

        value = extract_metric_value(session_metrics, metric_name)
        z = (value - stats.mean) / stats.std
        z_scores[metric_name] = max(-Z_SCORE_CLIP, min(Z_SCORE_CLIP, z))

    return z_scores


def compute_anomaly_score(z_scores: dict[str, float]) -> float:
    """Compute composite anomaly score from z-scores.

    Uses RMS (root mean square) of z-scores, normalized to [0.0, 1.0].
    Higher score = more anomalous.

    Args:
        z_scores: Per-metric z-scores.

    Returns:
        Anomaly score between 0.0 and 1.0.
    """
    if not z_scores:
        return COLD_START_SCORE

    sum_sq = sum(z * z for z in z_scores.values())
    rms = math.sqrt(sum_sq / len(z_scores))

    # Normalize: RMS of 0 → score 0, RMS of Z_SCORE_CLIP → score 1.0
    score = min(rms / Z_SCORE_CLIP, 1.0)
    return round(score, 4)


def cold_start_score() -> float:
    """Return the default score for agents with insufficient session history.

    Returns:
        0.5 (neutral — neither trusted nor suspicious).
    """
    return COLD_START_SCORE
