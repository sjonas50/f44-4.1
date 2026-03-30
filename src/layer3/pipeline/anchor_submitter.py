"""Anchor submitter — commits batch Merkle roots to Base L2.

Signs EIP-1559 transactions locally using eth-account and submits via
eth_sendRawTransaction to Alchemy (primary) or QuickNode (fallback).
No web3.py dependency — minimal stack: eth-account + eth-abi + httpx.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from eth_abi.abi import encode  # type: ignore[import-untyped]
from eth_account import Account
from eth_utils.abi import function_signature_to_4byte_selector  # type: ignore[import-untyped]
from pydantic import BaseModel

from src.layer3.pipeline.batch_extension import BatchResult
from src.shared.config.settings import Settings
from src.shared.crypto.hashing import sha256_hex

logger = structlog.get_logger()

# Correct Keccak-256 selector for anchorBatch(bytes32,bytes32,uint256)
ANCHOR_BATCH_SELECTOR: bytes = function_signature_to_4byte_selector("anchorBatch(bytes32,bytes32,uint256)")


class AnchorResult(BaseModel):
    """Result of submitting a batch root to the anchor contract."""

    tx_hash: str
    block_number: int
    chain_id: int
    contract_address: str
    anchored_at: datetime
    gas_used: int = 0


class AnchorSubmissionError(Exception):
    """Raised when both primary and fallback RPC providers fail."""


async def submit_anchor(batch_result: BatchResult, settings: Settings) -> AnchorResult:
    """Submit a batch Merkle root to the Base L2 anchor contract.

    Signs the transaction locally and submits via eth_sendRawTransaction.
    Tries primary RPC (Alchemy), falls back to QuickNode on failure.

    Args:
        batch_result: The built batch with Merkle root.
        settings: Application settings with RPC URLs, contract address, and deployer key.

    Returns:
        AnchorResult with tx hash and chain metadata.

    Raises:
        AnchorSubmissionError: If both RPCs fail.
    """
    if not settings.DEPLOYER_PRIVATE_KEY:
        raise AnchorSubmissionError("DEPLOYER_PRIVATE_KEY not configured")
    if not settings.ANCHOR_CONTRACT_ADDRESS:
        raise AnchorSubmissionError("ANCHOR_CONTRACT_ADDRESS not configured")

    calldata = _encode_anchor_call(batch_result)

    primary_error: Exception | None = None

    for rpc_url in [settings.BASE_L2_RPC_URL, settings.BASE_L2_RPC_FALLBACK_URL]:
        if not rpc_url:
            continue
        try:
            return await _sign_and_send(
                rpc_url=rpc_url,
                contract_address=settings.ANCHOR_CONTRACT_ADDRESS,
                calldata=calldata,
                private_key=settings.DEPLOYER_PRIVATE_KEY,
                chain_id=settings.BASE_CHAIN_ID,
            )
        except Exception as err:
            if primary_error is None:
                primary_error = err
                logger.warning("primary_rpc_failed", error=str(err), rpc=rpc_url)
            else:
                logger.error("fallback_rpc_failed", error=str(err), rpc=rpc_url)
                raise AnchorSubmissionError(f"Both RPCs failed. Primary: {primary_error}, Fallback: {err}") from err

    raise AnchorSubmissionError(f"No valid RPC URLs configured. Last error: {primary_error}")


def _encode_anchor_call(batch_result: BatchResult) -> bytes:
    """Encode the anchorBatch(bytes32, bytes32, uint256) calldata.

    Args:
        batch_result: Batch with merkle_root, batch_id, and record_count.

    Returns:
        ABI-encoded calldata bytes.
    """
    # Convert hex strings to bytes32
    merkle_root = bytes.fromhex(batch_result.merkle_root[:64].ljust(64, "0"))
    metadata_hash_hex = sha256_hex(f"{batch_result.batch_id}:{batch_result.record_count}")
    metadata_hash = bytes.fromhex(metadata_hash_hex[:64])

    # Convert batch_id string to uint256 (hash it to get a deterministic number)
    batch_id_int = int(sha256_hex(batch_result.batch_id)[:16], 16)

    # ABI encode: selector + encode(bytes32, bytes32, uint256)
    encoded_args: bytes = encode(
        ["bytes32", "bytes32", "uint256"],
        [merkle_root, metadata_hash, batch_id_int],
    )

    return ANCHOR_BATCH_SELECTOR + encoded_args


async def _sign_and_send(
    rpc_url: str,
    contract_address: str,
    calldata: bytes,
    private_key: str,
    chain_id: int,
) -> AnchorResult:
    """Sign an EIP-1559 transaction locally and submit via eth_sendRawTransaction."""
    account = Account.from_key(private_key)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get nonce
        nonce_hex = str(await _rpc_call(client, rpc_url, "eth_getTransactionCount", [account.address, "pending"]))
        nonce_int = int(nonce_hex, 16)

        # Get current base fee from latest block
        latest_block: dict[str, Any] = await _rpc_call(  # type: ignore[assignment]
            client, rpc_url, "eth_getBlockByNumber", ["latest", False]
        )
        base_fee = int(str(latest_block["baseFeePerGas"]), 16)

        # EIP-1559 gas params: maxFeePerGas = 2 * baseFee + tip (safe margin for Base L2)
        max_priority_fee = 1_000_000  # 0.001 gwei — Base sequencer accepts near-zero tips
        max_fee_per_gas = base_fee * 2 + max_priority_fee

        # Estimate gas
        gas_estimate_hex = str(
            await _rpc_call(
                client,
                rpc_url,
                "eth_estimateGas",
                [{"from": account.address, "to": contract_address, "data": "0x" + calldata.hex()}],
            )
        )
        gas_limit = int(gas_estimate_hex, 16) + 10_000  # Small buffer

        # Build EIP-1559 (Type 2) transaction
        tx = {
            "type": 2,
            "chainId": chain_id,
            "nonce": nonce_int,
            "to": contract_address,
            "data": calldata,
            "gas": gas_limit,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee,
            "value": 0,
        }

        # Sign locally
        signed = Account.sign_transaction(tx, private_key)
        raw_tx_hex = "0x" + signed.raw_transaction.hex()

        # Submit
        tx_hash = str(await _rpc_call(client, rpc_url, "eth_sendRawTransaction", [raw_tx_hex]))

        logger.info("anchor_tx_submitted", tx_hash=tx_hash, nonce=nonce_int, gas_limit=gas_limit)

        # Poll for receipt (up to 60 seconds)
        receipt = await _wait_for_receipt(client, rpc_url, tx_hash, timeout_seconds=60)

    block_number = int(str(receipt["blockNumber"]), 16) if receipt else 0
    gas_used = int(str(receipt["gasUsed"]), 16) if receipt else 0
    status = int(str(receipt["status"]), 16) if receipt else 0

    if receipt and status != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash}")

    logger.info("anchor_confirmed", tx_hash=tx_hash, block=block_number, gas_used=gas_used)

    return AnchorResult(
        tx_hash=tx_hash,
        block_number=block_number,
        chain_id=chain_id,
        contract_address=contract_address,
        anchored_at=datetime.now(UTC),
        gas_used=gas_used,
    )


async def _rpc_call(client: httpx.AsyncClient, rpc_url: str, method: str, params: list) -> Any:
    """Make a JSON-RPC call and return the result.

    Raises:
        RuntimeError: If the RPC returns an error.
    """
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    response = await client.post(rpc_url, json=payload)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"RPC error ({method}): {data['error']}")

    return data["result"]


async def _wait_for_receipt(
    client: httpx.AsyncClient,
    rpc_url: str,
    tx_hash: str,
    timeout_seconds: int = 60,
    poll_interval: float = 2.0,
) -> dict[str, Any] | None:
    """Poll for transaction receipt until confirmed or timeout."""
    elapsed = 0.0
    while elapsed < timeout_seconds:
        try:
            receipt = await _rpc_call(client, rpc_url, "eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                return receipt  # type: ignore[return-value]
        except RuntimeError:
            pass
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.warning("anchor_receipt_timeout", tx_hash=tx_hash, timeout=timeout_seconds)
    return None
