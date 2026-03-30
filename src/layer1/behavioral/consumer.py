"""Redis Streams consumer for behavioral session events.

Reads SessionComplete events from stream:behavioral_session, updates
per-agent baselines, and caches anomaly scores in Redis. Runs as a
standalone ARQ worker process.
"""

import json

import redis.asyncio as aioredis
import structlog

from src.layer1.behavioral.baselines import AgentBaseline, update_baseline
from src.layer1.behavioral.scoring import (
    COLD_START_THRESHOLD,
    cold_start_score,
    compute_anomaly_score,
    compute_z_scores,
)
from src.shared.redis_client.streams import create_consumer_group, xack, xreadgroup

logger = structlog.get_logger()

BEHAVIORAL_STREAM = "stream:behavioral_session"
CONSUMER_GROUP = "behavioral_engine"
BASELINE_PREFIX = "behavioral:baseline:"
SCORE_PREFIX = "behavioral:score:"
SCORE_TTL = 1800  # 30 minutes


async def process_session_events(redis_client: aioredis.Redis, consumer_name: str = "worker-1") -> int:
    """Process pending session events from the behavioral stream.

    Args:
        redis_client: Async Redis client.
        consumer_name: Name of this consumer within the group.

    Returns:
        Number of events processed.
    """
    await create_consumer_group(redis_client, BEHAVIORAL_STREAM, CONSUMER_GROUP)

    messages = await xreadgroup(
        redis_client,
        BEHAVIORAL_STREAM,
        CONSUMER_GROUP,
        consumer_name,
        count=50,
        block_ms=1000,
    )

    processed = 0
    for msg_id, payload in messages:
        try:
            agent_id = payload.get("agent_id", "")
            metrics = payload.get("metrics", {})
            if isinstance(metrics, str):
                metrics = json.loads(metrics)

            # Load current baseline
            baseline_key = f"{BASELINE_PREFIX}{agent_id}"
            baseline_data = await redis_client.get(baseline_key)
            baseline = AgentBaseline.model_validate_json(baseline_data) if baseline_data else None

            # Update baseline
            new_baseline = update_baseline(baseline, metrics)
            await redis_client.set(baseline_key, new_baseline.model_dump_json())

            # Compute and cache anomaly score
            score_key = f"{SCORE_PREFIX}{agent_id}"
            if new_baseline.total_sessions < COLD_START_THRESHOLD:
                score = cold_start_score()
                factors = ["cold_start"]
            else:
                z_scores = compute_z_scores(new_baseline, metrics)
                score = compute_anomaly_score(z_scores)
                factors = [f"{k}:{v:.2f}" for k, v in z_scores.items() if abs(v) > 1.0]

            score_data = json.dumps(
                {
                    "anomaly_score": score,
                    "factors": factors,
                    "total_sessions": new_baseline.total_sessions,
                }
            )
            await redis_client.set(score_key, score_data, ex=SCORE_TTL)

            await xack(redis_client, BEHAVIORAL_STREAM, CONSUMER_GROUP, msg_id)
            processed += 1

            logger.info(
                "session_processed",
                agent_id=agent_id,
                anomaly_score=score,
                total_sessions=new_baseline.total_sessions,
            )
        except Exception:
            logger.exception("session_processing_error", msg_id=msg_id)

    return processed


async def run_consumer_loop() -> None:
    """Run the consumer in a continuous loop."""
    from src.shared.config.settings import Settings
    from src.shared.redis_client.client import close_redis, init_redis

    settings = Settings()
    redis_client = await init_redis(settings)
    logger.info("behavioral_consumer_started")

    try:
        while True:
            await process_session_events(redis_client)
    finally:
        await close_redis()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_consumer_loop())
