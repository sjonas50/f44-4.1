from datetime import datetime
from typing import Literal

from src.shared.models.base import BaseEntity


class BatchRecord(BaseEntity):
    """Universal input record for the Merkle batch pipeline.

    This is the key contract with ASOR's pipeline extension. All three layers
    submit records in this format: audit (L2), trust_event (L1), provenance (L3).
    The batch pipeline computes a Merkle tree over the hashes regardless of type.
    """

    hash: str
    record_type: Literal["audit", "trust_event", "provenance"]
    layer: Literal[1, 2, 3]
    timestamp: datetime
