"""Redis Streams helpers for durable event delivery."""

import json

import redis.asyncio as aioredis


async def xadd(client: aioredis.Redis, stream: str, data: dict) -> str:
    """Add a message to a Redis Stream.

    Args:
        client: Async Redis client.
        stream: Stream name.
        data: Message data (serialized to JSON string under 'payload' key).

    Returns:
        The stream message ID.
    """
    return await client.xadd(stream, {"payload": json.dumps(data)})


async def create_consumer_group(client: aioredis.Redis, stream: str, group: str) -> None:
    """Create a consumer group, ignoring if it already exists.

    Args:
        client: Async Redis client.
        stream: Stream name.
        group: Consumer group name.
    """
    try:
        await client.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def xreadgroup(
    client: aioredis.Redis,
    stream: str,
    group: str,
    consumer: str,
    count: int = 10,
    block_ms: int = 5000,
) -> list[tuple[str, dict]]:
    """Read messages from a consumer group.

    Args:
        client: Async Redis client.
        stream: Stream name.
        group: Consumer group name.
        consumer: Consumer name within the group.
        count: Max messages to read.
        block_ms: Block timeout in milliseconds.

    Returns:
        List of (message_id, parsed_data) tuples.
    """
    results = await client.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    messages: list[tuple[str, dict]] = []
    if results:
        for _stream_name, stream_messages in results:
            for msg_id, msg_data in stream_messages:
                payload = json.loads(msg_data["payload"])
                messages.append((msg_id, payload))
    return messages


async def xack(client: aioredis.Redis, stream: str, group: str, message_id: str) -> None:
    """Acknowledge a message in a consumer group.

    Args:
        client: Async Redis client.
        stream: Stream name.
        group: Consumer group name.
        message_id: Message ID to acknowledge.
    """
    await client.xack(stream, group, message_id)
