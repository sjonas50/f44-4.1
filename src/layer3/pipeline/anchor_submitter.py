"""Anchor submitter — commits batch Merkle roots to Base L2.

Calls the anchor contract's anchorBatch(merkleRoot, metadataHash, batchId)
via JSON-RPC to the Base L2. Uses Alchemy as primary RPC with QuickNode fallback.
"""

from datetime import UTC, datetime

import httpx
import structlog
from pydantic import BaseModel

from src.layer3.pipeline.batch_extension import BatchResult
from src.shared.config.settings import Settings
from src.shared.crypto.hashing import sha256_hex

logger = structlog.get_logger()


class AnchorResult(BaseModel):
    """Result of submitting a batch root to the anchor contract."""

    tx_hash: str
    block_number: int
    chain_id: int
    contract_address: str
    anchored_at: datetime


class AnchorSubmissionError(Exception):
    """Raised when both primary and fallback RPC providers fail."""


async def submit_anchor(batch_result: BatchResult, settings: Settings) -> AnchorResult:
    """Submit a batch Merkle root to the Base L2 anchor contract.

    Tries primary RPC (Alchemy), falls back to QuickNode on failure.

    Args:
        batch_result: The built batch with Merkle root.
        settings: Application settings with RPC URLs and contract address.

    Returns:
        AnchorResult with tx hash and chain metadata.

    Raises:
        AnchorSubmissionError: If both RPCs fail.
    """
    metadata_hash = sha256_hex(f"{batch_result.batch_id}:{batch_result.record_count}")

    primary_error: Exception | None = None

    # Try primary RPC
    try:
        return await _send_anchor_tx(
            rpc_url=settings.BASE_L2_RPC_URL,
            contract_address=settings.ANCHOR_CONTRACT_ADDRESS,
            merkle_root=batch_result.merkle_root,
            metadata_hash=metadata_hash,
            batch_id=batch_result.batch_id,
        )
    except Exception as err:
        primary_error = err
        logger.warning("primary_rpc_failed", error=str(err))

    # Try fallback RPC
    try:
        return await _send_anchor_tx(
            rpc_url=settings.BASE_L2_RPC_FALLBACK_URL,
            contract_address=settings.ANCHOR_CONTRACT_ADDRESS,
            merkle_root=batch_result.merkle_root,
            metadata_hash=metadata_hash,
            batch_id=batch_result.batch_id,
        )
    except Exception as fallback_err:
        logger.error("fallback_rpc_failed", error=str(fallback_err))
        raise AnchorSubmissionError(
            f"Both RPCs failed. Primary: {primary_error}, Fallback: {fallback_err}"
        ) from fallback_err


async def _send_anchor_tx(
    rpc_url: str,
    contract_address: str,
    merkle_root: str,
    metadata_hash: str,
    batch_id: str,
) -> AnchorResult:
    """Send the anchor transaction via JSON-RPC.

    Args:
        rpc_url: Ethereum JSON-RPC endpoint.
        contract_address: Anchor contract address.
        merkle_root: Merkle root hex string.
        metadata_hash: Metadata hash hex string.
        batch_id: Batch identifier.

    Returns:
        AnchorResult on success.
    """
    # Encode anchorBatch(bytes32, bytes32, uint256) call data
    # Function selector: keccak256("anchorBatch(bytes32,bytes32,uint256)")[:4]
    # For now, we build the raw tx payload structure
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_sendTransaction",
        "params": [
            {
                "to": contract_address,
                "data": _encode_anchor_call(merkle_root, metadata_hash, batch_id),
            }
        ],
        "id": 1,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(rpc_url, json=payload)
        response.raise_for_status()
        result = response.json()

        if "error" in result:
            raise RuntimeError(f"RPC error: {result['error']}")

        tx_hash = result.get("result", "0x0")

    logger.info("anchor_submitted", tx_hash=tx_hash, batch_id=batch_id)

    return AnchorResult(
        tx_hash=tx_hash,
        block_number=0,  # Would be populated by tx receipt polling
        chain_id=8453,  # Base mainnet
        contract_address=contract_address,
        anchored_at=datetime.now(UTC),
    )


def _compute_selector(signature: str) -> str:
    """Compute the 4-byte function selector from a Solidity signature.

    Args:
        signature: Function signature, e.g. "anchorBatch(bytes32,bytes32,uint256)".

    Returns:
        Hex-encoded 4-byte selector with 0x prefix.
    """
    import hashlib

    digest = hashlib.sha3_256(signature.encode()).hexdigest()
    return f"0x{digest[:8]}"


# Pre-computed selector for anchorBatch(bytes32,bytes32,uint256)
ANCHOR_BATCH_SELECTOR = _compute_selector("anchorBatch(bytes32,bytes32,uint256)")


def _encode_anchor_call(merkle_root: str, metadata_hash: str, batch_id: str) -> str:
    """Encode the anchorBatch function call data.

    Args:
        merkle_root: 64-char hex string (32 bytes).
        metadata_hash: 64-char hex string (32 bytes).
        batch_id: Batch ID string (hashed to uint256).

    Returns:
        Hex-encoded call data.
    """
    # Left-zero-pad bytes32 args to 64 hex chars (ABI encoding)
    root_padded = merkle_root[:64].zfill(64)
    meta_padded = metadata_hash[:64].zfill(64)
    # Convert batch_id to uint256 (hash it, take as 256-bit integer, left-pad to 64 hex)
    id_hash = sha256_hex(batch_id).zfill(64)
    return f"{ANCHOR_BATCH_SELECTOR}{root_padded}{meta_padded}{id_hash}"
