"""Custom Merkle tree with OpenZeppelin-compatible proof format.

Leaf hashing: SHA-256(0x00 || leaf_data)
Node hashing: SHA-256(0x01 || sorted(left, right))

Sorting internal node children ensures proof verification doesn't need
left/right position tracking — matches OpenZeppelin's MerkleProof.verify().
"""

import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _hash_leaf(data: str) -> str:
    """Hash a leaf value with domain separation prefix."""
    return hashlib.sha256(LEAF_PREFIX + data.encode("utf-8")).hexdigest()


def _hash_node(left: str, right: str) -> str:
    """Hash two child nodes with domain separation, sorted for OZ compatibility."""
    pair = sorted([left, right])
    return hashlib.sha256(NODE_PREFIX + bytes.fromhex(pair[0]) + bytes.fromhex(pair[1])).hexdigest()


class MerkleTree:
    """Binary Merkle tree with OpenZeppelin-compatible inclusion proofs.

    Args:
        leaves: List of leaf values (strings). Must be non-empty.

    Raises:
        ValueError: If leaves list is empty.
    """

    def __init__(self, leaves: list[str]) -> None:
        if not leaves:
            raise ValueError("Cannot build Merkle tree from empty leaf list")

        self._leaf_hashes = [_hash_leaf(leaf) for leaf in leaves]
        self._layers: list[list[str]] = [self._leaf_hashes[:]]
        self._build()

    def _build(self) -> None:
        """Build tree layers bottom-up."""
        current = self._layers[0]
        while len(current) > 1:
            next_layer: list[str] = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else current[i]
                next_layer.append(_hash_node(left, right))
            self._layers.append(next_layer)
            current = next_layer

    @property
    def root(self) -> str:
        """The Merkle root hash."""
        return self._layers[-1][0]

    def get_proof(self, index: int) -> list[str]:
        """Get inclusion proof for leaf at index.

        Args:
            index: Zero-based leaf index.

        Returns:
            List of sibling hashes forming the proof path.

        Raises:
            IndexError: If index is out of range.
        """
        if index < 0 or index >= len(self._leaf_hashes):
            raise IndexError(f"Leaf index {index} out of range [0, {len(self._leaf_hashes)})")

        proof: list[str] = []
        idx = index
        for layer in self._layers[:-1]:
            sibling_idx = idx + 1 if idx % 2 == 0 else idx - 1

            if sibling_idx < len(layer):
                proof.append(layer[sibling_idx])
            else:
                proof.append(layer[idx])
            idx //= 2

        return proof


def verify_proof(leaf: str, proof: list[str], root: str) -> bool:
    """Verify a Merkle inclusion proof.

    Args:
        leaf: The leaf value (not pre-hashed).
        proof: List of sibling hashes from get_proof().
        root: Expected Merkle root.

    Returns:
        True if the proof is valid.
    """
    current = _hash_leaf(leaf)
    for sibling in proof:
        current = _hash_node(current, sibling)
    return current == root
