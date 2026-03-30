"""Storage adapter for provenance artifacts.

Development: writes to local filesystem under ./provenance/{session_id}/
Production: writes to S3 WORM bucket under provenance/{session_id}/ prefix.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from src.shared.config.settings import Settings


class StorageResult(BaseModel):
    """Result of writing session artifacts to storage."""

    storage_path: str
    artifact_keys: list[str]


async def write_session(
    session_id: str,
    artifacts: dict[str, object],
    settings: Settings,
) -> StorageResult:
    """Write session artifacts to storage.

    Args:
        session_id: Session identifier.
        artifacts: Dict of artifact_name → artifact_data from to_5w_artifacts().
        settings: Application settings.

    Returns:
        StorageResult with storage path and artifact keys.
    """
    if settings.ENVIRONMENT == "development":
        return await _write_local(session_id, artifacts)
    else:
        return await _write_s3(session_id, artifacts, settings)


async def _write_local(session_id: str, artifacts: dict[str, object]) -> StorageResult:
    """Write artifacts to local filesystem."""
    base_path = Path("provenance") / session_id
    base_path.mkdir(parents=True, exist_ok=True)

    keys: list[str] = []
    for name, data in artifacts.items():
        file_path = base_path / name
        if name.endswith(".md"):
            file_path.write_text(str(data))
        elif name.endswith(".jsonl"):
            # JSONL: one JSON object per line
            lines = [json.dumps(item) for item in data] if isinstance(data, list) else [json.dumps(data)]
            file_path.write_text("\n".join(lines) + "\n")
        else:
            file_path.write_text(json.dumps(data, indent=2, default=str))
        keys.append(name)

    return StorageResult(storage_path=str(base_path), artifact_keys=keys)


async def _write_s3(
    session_id: str,
    artifacts: dict[str, object],
    settings: Settings,
) -> StorageResult:
    """Write artifacts to S3 WORM bucket.

    Note: In production, this would use boto3 with Object Lock retention.
    For now, this is a structured placeholder that documents the contract.
    """
    prefix = f"provenance/{session_id}"
    keys: list[str] = []

    for name, _data in artifacts.items():
        key = f"{prefix}/{name}"
        # TODO: boto3.put_object with ObjectLockRetainUntilDate
        keys.append(key)

    return StorageResult(
        storage_path=f"s3://{settings.AWS_S3_WORM_BUCKET}/{prefix}",
        artifact_keys=keys,
    )
