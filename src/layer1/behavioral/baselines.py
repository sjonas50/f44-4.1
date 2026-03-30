"""Per-agent statistical baselines using exponentially weighted moving averages.

Tracks rolling means and standard deviations for session metrics:
- dead_end_count
- tool_invocations (count)
- cost_usd
- duration_ms
"""

from pydantic import BaseModel, Field

from src.layer1.behavioral.metrics import extract_metric_value

TRACKED_METRICS = ["dead_end_count", "tool_invocations", "cost_usd", "duration_ms"]
EWMA_ALPHA = 2 / (20 + 1)  # Equivalent to pandas EWMA span=20


class MetricStats(BaseModel):
    """Rolling mean and variance for a single metric."""

    mean: float = 0.0
    variance: float = 0.0
    count: int = 0

    @property
    def std(self) -> float:
        return self.variance**0.5 if self.variance > 0 else 0.0


class AgentBaseline(BaseModel):
    """Per-agent behavioral baseline across all tracked metrics."""

    metrics: dict[str, MetricStats] = Field(default_factory=lambda: {m: MetricStats() for m in TRACKED_METRICS})
    total_sessions: int = 0


def update_baseline(current: AgentBaseline | None, session_metrics: dict) -> AgentBaseline:
    """Update a baseline with new session metrics using EWMA.

    Args:
        current: Current baseline (None for first session).
        session_metrics: Dict with metric values from the session.

    Returns:
        New AgentBaseline (never mutates the input).
    """
    if current is None:
        current = AgentBaseline()

    new_metrics: dict[str, MetricStats] = {}

    for metric_name in TRACKED_METRICS:
        value = extract_metric_value(session_metrics, metric_name)
        old = current.metrics.get(metric_name, MetricStats())

        if old.count == 0:
            # First observation
            new_metrics[metric_name] = MetricStats(mean=value, variance=0.0, count=1)
        else:
            # EWMA update for mean
            new_mean = EWMA_ALPHA * value + (1 - EWMA_ALPHA) * old.mean
            # EWMA update for variance (Welford-like with exponential weighting)
            diff = value - old.mean
            new_variance = (1 - EWMA_ALPHA) * (old.variance + EWMA_ALPHA * diff * diff)
            new_metrics[metric_name] = MetricStats(
                mean=new_mean,
                variance=new_variance,
                count=old.count + 1,
            )

    return AgentBaseline(metrics=new_metrics, total_sessions=current.total_sessions + 1)
