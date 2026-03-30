"""Shared metric extraction utility for behavioral analysis."""


def extract_metric_value(session_metrics: dict, metric_name: str) -> float:
    """Extract a numeric metric value from session data.

    Args:
        session_metrics: Raw session metrics dict.
        metric_name: Name of the metric to extract.

    Returns:
        Float value of the metric.
    """
    if metric_name == "tool_invocations":
        val = session_metrics.get(metric_name, 0)
        return float(len(val)) if isinstance(val, list) else float(val)
    return float(session_metrics.get(metric_name, 0))
