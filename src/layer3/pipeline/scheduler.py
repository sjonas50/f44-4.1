"""Periodic anchor scheduler — collects pending records and commits to Base L2.

Runs as a background task in the Layer 3 app or as a standalone worker.
Every ANCHOR_INTERVAL_SECONDS, it:
1. Drains pending batch records from Redis
2. Builds a Merkle tree over all records
3. Signs and submits the root to the Base L2 anchor contract
4. Stores the tx hash alongside the batch in WORM
"""

import asyncio

import redis.asyncio as aioredis
import structlog

from src.layer3.pipeline.anchor_submitter import AnchorSubmissionError, submit_anchor
from src.layer3.pipeline.batch_extension import BatchExtension, BatchResult
from src.shared.config.settings import Settings
from src.shared.models.batch_record import BatchRecord

logger = structlog.get_logger()

PENDING_RECORDS_KEY = "anchor:pending_records"


async def enqueue_batch_record(redis_client: aioredis.Redis, record: BatchRecord) -> None:
    """Add a batch record to the pending anchor queue.

    Args:
        redis_client: Async Redis client.
        record: BatchRecord to queue for the next anchor batch.
    """
    await redis_client.rpush(PENDING_RECORDS_KEY, record.model_dump_json())


async def build_and_submit_batch(redis_client: aioredis.Redis, settings: Settings) -> BatchResult | None:
    """Drain pending records, build Merkle batch, and submit to Base L2.

    Args:
        redis_client: Async Redis client.
        settings: Application settings.

    Returns:
        BatchResult if a batch was submitted, None if no pending records.
    """
    # Atomically drain all pending records
    pipe = redis_client.pipeline()
    pipe.lrange(PENDING_RECORDS_KEY, 0, -1)
    pipe.delete(PENDING_RECORDS_KEY)
    results = await pipe.execute()
    raw_records = results[0]

    if not raw_records:
        logger.debug("anchor_scheduler_no_pending_records")
        return None

    # Parse records
    batch = BatchExtension()
    for raw in raw_records:
        record = BatchRecord.model_validate_json(raw)
        batch.add_record(record)

    batch_result = batch.build_batch()
    logger.info(
        "anchor_batch_built",
        batch_id=batch_result.batch_id,
        record_count=batch_result.record_count,
        merkle_root=batch_result.merkle_root[:16],
    )

    # Submit to Base L2
    if not settings.DEPLOYER_PRIVATE_KEY or not settings.ANCHOR_CONTRACT_ADDRESS:
        logger.warning(
            "anchor_submission_skipped",
            reason="DEPLOYER_PRIVATE_KEY or ANCHOR_CONTRACT_ADDRESS not configured",
            batch_id=batch_result.batch_id,
        )
        return batch_result

    try:
        anchor_result = await submit_anchor(batch_result, settings)
        logger.info(
            "anchor_batch_committed",
            batch_id=batch_result.batch_id,
            tx_hash=anchor_result.tx_hash,
            block=anchor_result.block_number,
            gas_used=anchor_result.gas_used,
        )
    except AnchorSubmissionError as e:
        # Re-enqueue records for the next interval
        logger.error("anchor_submission_failed_requeueing", error=str(e), record_count=len(raw_records))
        for raw in raw_records:
            await redis_client.rpush(PENDING_RECORDS_KEY, raw)
        raise

    return batch_result


async def run_anchor_scheduler(redis_client: aioredis.Redis, settings: Settings) -> None:
    """Run the periodic anchor scheduler loop.

    Runs forever, submitting batches every ANCHOR_INTERVAL_SECONDS.

    Args:
        redis_client: Async Redis client.
        settings: Application settings.
    """
    interval = settings.ANCHOR_INTERVAL_SECONDS
    logger.info("anchor_scheduler_started", interval_seconds=interval)

    while True:
        try:
            result = await build_and_submit_batch(redis_client, settings)
            if result:
                logger.info("anchor_cycle_complete", batch_id=result.batch_id, records=result.record_count)
        except AnchorSubmissionError:
            pass  # Already logged and requeued in build_and_submit_batch
        except Exception:
            logger.exception("anchor_scheduler_unexpected_error")

        await asyncio.sleep(interval)


if __name__ == "__main__":
    from src.shared.redis_client.client import init_redis

    async def main() -> None:
        settings = Settings()
        redis_client = await init_redis(settings)
        await run_anchor_scheduler(redis_client, settings)

    asyncio.run(main())
