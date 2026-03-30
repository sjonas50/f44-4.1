// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BatchAnchor — Minimal Merkle root commitment for Sovereign Agent
/// @notice Stores periodic Merkle root hashes linking Layer 1, 2, and 3 records.
///         Zero operational data on-chain. Just a 32-byte commitment per batch.
/// @dev Deployed to Base L2. ~50 lines. No complex state management.
contract BatchAnchor {
    address public immutable owner;

    struct Anchor {
        bytes32 merkleRoot;
        bytes32 metadataHash;
        uint256 timestamp;
    }

    mapping(uint256 => Anchor) public anchors;
    uint256 public anchorCount;

    event BatchAnchored(
        bytes32 indexed merkleRoot,
        bytes32 metadataHash,
        uint256 indexed batchId,
        uint256 timestamp
    );

    error Unauthorized();
    error BatchAlreadyAnchored();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /// @notice Anchor a Merkle root hash on-chain
    /// @param merkleRoot The Merkle root covering records from all three layers
    /// @param metadataHash Hash of batch metadata (record count, layer distribution)
    /// @param batchId Unique batch identifier
    function anchorBatch(
        bytes32 merkleRoot,
        bytes32 metadataHash,
        uint256 batchId
    ) external onlyOwner {
        if (anchors[batchId].timestamp != 0) revert BatchAlreadyAnchored();

        anchors[batchId] = Anchor({
            merkleRoot: merkleRoot,
            metadataHash: metadataHash,
            timestamp: block.timestamp
        });
        anchorCount++;

        emit BatchAnchored(merkleRoot, metadataHash, batchId, block.timestamp);
    }

    /// @notice Retrieve a stored anchor by batch ID
    /// @param batchId The batch identifier
    /// @return merkleRoot The stored Merkle root
    /// @return metadataHash The stored metadata hash
    /// @return timestamp When the anchor was committed
    function getAnchor(uint256 batchId)
        external
        view
        returns (bytes32 merkleRoot, bytes32 metadataHash, uint256 timestamp)
    {
        Anchor storage a = anchors[batchId];
        return (a.merkleRoot, a.metadataHash, a.timestamp);
    }
}
