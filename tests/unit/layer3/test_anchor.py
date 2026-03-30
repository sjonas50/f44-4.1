"""Tests for anchor submitter, scheduler, and ABI encoding."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.layer3.pipeline.anchor_submitter import (
    ANCHOR_BATCH_SELECTOR,
    AnchorSubmissionError,
    _encode_anchor_call,
    submit_anchor,
)
from src.layer3.pipeline.batch_extension import BatchExtension
from src.shared.crypto.hashing import sha256_hex
from src.shared.models.batch_record import BatchRecord


class TestABIEncoding:
    def test_selector_is_4_bytes(self) -> None:
        assert len(ANCHOR_BATCH_SELECTOR) == 4

    def test_selector_is_keccak256(self) -> None:
        """Verify we use real Keccak-256 (not SHA3-256)."""
        from eth_utils import function_signature_to_4byte_selector

        expected = function_signature_to_4byte_selector("anchorBatch(bytes32,bytes32,uint256)")
        assert expected == ANCHOR_BATCH_SELECTOR

    def test_encode_produces_valid_calldata(self) -> None:
        ext = BatchExtension()
        ext.add_record(BatchRecord(hash=sha256_hex("test"), record_type="audit", layer=2, timestamp=datetime.now(UTC)))
        result = ext.build_batch()

        calldata = _encode_anchor_call(result)
        # 4 bytes selector + 3 * 32 bytes args = 100 bytes
        assert len(calldata) == 4 + 32 * 3
        assert calldata[:4] == ANCHOR_BATCH_SELECTOR

    def test_encode_is_deterministic(self) -> None:
        record = BatchRecord(
            hash=sha256_hex("deterministic"),
            record_type="provenance",
            layer=3,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
        ext1 = BatchExtension()
        ext1.add_record(record)

        r1 = ext1.build_batch()
        calldata1 = _encode_anchor_call(r1)
        calldata2 = _encode_anchor_call(r1)
        assert calldata1 == calldata2


class TestSubmitAnchor:
    @pytest.fixture
    def settings(self):
        from src.shared.config.settings import Settings

        return Settings(
            BASE_L2_RPC_URL="https://primary.example.com",
            BASE_L2_RPC_FALLBACK_URL="https://fallback.example.com",
            ANCHOR_CONTRACT_ADDRESS="0x1234567890abcdef1234567890abcdef12345678",
            DEPLOYER_PRIVATE_KEY="0x" + "ab" * 32,
            BASE_CHAIN_ID=84532,
        )

    @pytest.fixture
    def batch_result(self):
        ext = BatchExtension()
        ext.add_record(BatchRecord(hash=sha256_hex("test"), record_type="audit", layer=2, timestamp=datetime.now(UTC)))
        return ext.build_batch()

    @pytest.mark.asyncio
    async def test_missing_private_key_raises(self, batch_result) -> None:
        from src.shared.config.settings import Settings

        settings = Settings(DEPLOYER_PRIVATE_KEY="", ANCHOR_CONTRACT_ADDRESS="0x123")
        with pytest.raises(AnchorSubmissionError, match="DEPLOYER_PRIVATE_KEY"):
            await submit_anchor(batch_result, settings)

    @pytest.mark.asyncio
    async def test_missing_contract_address_raises(self, batch_result) -> None:
        from src.shared.config.settings import Settings

        settings = Settings(DEPLOYER_PRIVATE_KEY="0x" + "ab" * 32, ANCHOR_CONTRACT_ADDRESS="")
        with pytest.raises(AnchorSubmissionError, match="ANCHOR_CONTRACT_ADDRESS"):
            await submit_anchor(batch_result, settings)

    @pytest.mark.asyncio
    async def test_both_rpcs_fail_raises(self, settings, batch_result) -> None:
        with (
            patch(
                "src.layer3.pipeline.anchor_submitter._sign_and_send",
                side_effect=RuntimeError("Connection failed"),
            ),
            pytest.raises(AnchorSubmissionError, match="Both RPCs failed"),
        ):
            await submit_anchor(batch_result, settings)

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, settings, batch_result) -> None:
        from src.layer3.pipeline.anchor_submitter import AnchorResult

        mock_result = AnchorResult(
            tx_hash="0xfallback",
            block_number=101,
            chain_id=84532,
            contract_address=settings.ANCHOR_CONTRACT_ADDRESS,
            anchored_at=datetime.now(UTC),
            gas_used=50000,
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Primary failed")
            return mock_result

        with patch("src.layer3.pipeline.anchor_submitter._sign_and_send", side_effect=side_effect):
            result = await submit_anchor(batch_result, settings)
            assert result.tx_hash == "0xfallback"
            assert call_count == 2


class TestAnchorScheduler:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def settings(self):
        from src.shared.config.settings import Settings

        return Settings(
            ANCHOR_CONTRACT_ADDRESS="0x1234567890abcdef1234567890abcdef12345678",
            DEPLOYER_PRIVATE_KEY="0x" + "ab" * 32,
            BASE_L2_RPC_URL="https://example.com",
            ANCHOR_INTERVAL_SECONDS=5,
        )

    @pytest.mark.asyncio
    async def test_enqueue_and_drain(self, redis_client) -> None:
        from src.layer3.pipeline.scheduler import PENDING_RECORDS_KEY, enqueue_batch_record

        record = BatchRecord(hash=sha256_hex("test"), record_type="provenance", layer=3, timestamp=datetime.now(UTC))
        await enqueue_batch_record(redis_client, record)

        count = await redis_client.llen(PENDING_RECORDS_KEY)
        assert count == 1

    @pytest.mark.asyncio
    async def test_build_batch_with_no_records_returns_none(self, redis_client, settings) -> None:
        from src.layer3.pipeline.scheduler import build_and_submit_batch

        result = await build_and_submit_batch(redis_client, settings)
        assert result is None

    @pytest.mark.asyncio
    async def test_build_batch_requeues_on_failure(self, redis_client, settings) -> None:
        from src.layer3.pipeline.scheduler import (
            PENDING_RECORDS_KEY,
            build_and_submit_batch,
            enqueue_batch_record,
        )

        for i in range(3):
            record = BatchRecord(
                hash=sha256_hex(f"record-{i}"), record_type="provenance", layer=3, timestamp=datetime.now(UTC)
            )
            await enqueue_batch_record(redis_client, record)

        with (
            patch("src.layer3.pipeline.scheduler.submit_anchor", side_effect=AnchorSubmissionError("test")),
            pytest.raises(AnchorSubmissionError),
        ):
            await build_and_submit_batch(redis_client, settings)

        # Records should be re-enqueued on failure
        count = await redis_client.llen(PENDING_RECORDS_KEY)
        assert count == 3

    @pytest.mark.asyncio
    async def test_successful_submission_clears_queue(self, redis_client, settings) -> None:
        from src.layer3.pipeline.anchor_submitter import AnchorResult
        from src.layer3.pipeline.scheduler import (
            PENDING_RECORDS_KEY,
            build_and_submit_batch,
            enqueue_batch_record,
        )

        for i in range(2):
            record = BatchRecord(
                hash=sha256_hex(f"record-{i}"), record_type="audit", layer=2, timestamp=datetime.now(UTC)
            )
            await enqueue_batch_record(redis_client, record)

        mock_anchor = AnchorResult(
            tx_hash="0xabc",
            block_number=100,
            chain_id=84532,
            contract_address="0x123",
            anchored_at=datetime.now(UTC),
            gas_used=45000,
        )

        with patch("src.layer3.pipeline.scheduler.submit_anchor", return_value=mock_anchor):
            result = await build_and_submit_batch(redis_client, settings)

        assert result is not None
        assert result.record_count == 2
        count = await redis_client.llen(PENDING_RECORDS_KEY)
        assert count == 0
