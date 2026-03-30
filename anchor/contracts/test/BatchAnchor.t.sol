// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/BatchAnchor.sol";

contract BatchAnchorTest is Test {
    BatchAnchor public anchor;
    address public deployer = address(this);
    address public attacker = address(0xBEEF);

    function setUp() public {
        anchor = new BatchAnchor();
    }

    function test_anchor_batch_stores_data() public {
        bytes32 root = keccak256("merkle-root-1");
        bytes32 meta = keccak256("metadata-1");
        uint256 batchId = 1;

        anchor.anchorBatch(root, meta, batchId);

        (bytes32 storedRoot, bytes32 storedMeta, uint256 storedTs) = anchor.getAnchor(batchId);
        assertEq(storedRoot, root);
        assertEq(storedMeta, meta);
        assertGt(storedTs, 0);
    }

    function test_anchor_batch_emits_event() public {
        bytes32 root = keccak256("merkle-root-2");
        bytes32 meta = keccak256("metadata-2");
        uint256 batchId = 2;

        vm.expectEmit(true, true, false, true);
        emit BatchAnchor.BatchAnchored(root, meta, batchId, block.timestamp);

        anchor.anchorBatch(root, meta, batchId);
    }

    function test_get_anchor_returns_correct_root() public {
        bytes32 root = keccak256("test-root");
        bytes32 meta = keccak256("test-meta");
        anchor.anchorBatch(root, meta, 42);

        (bytes32 r, , ) = anchor.getAnchor(42);
        assertEq(r, root);
    }

    function test_only_owner_can_anchor() public {
        vm.prank(attacker);
        vm.expectRevert(BatchAnchor.Unauthorized.selector);
        anchor.anchorBatch(keccak256("x"), keccak256("y"), 1);
    }

    function test_cannot_anchor_same_batch_twice() public {
        bytes32 root = keccak256("root");
        bytes32 meta = keccak256("meta");
        anchor.anchorBatch(root, meta, 1);

        vm.expectRevert(BatchAnchor.BatchAlreadyAnchored.selector);
        anchor.anchorBatch(keccak256("root2"), keccak256("meta2"), 1);
    }

    function test_anchor_count_increments() public {
        assertEq(anchor.anchorCount(), 0);
        anchor.anchorBatch(keccak256("a"), keccak256("b"), 1);
        assertEq(anchor.anchorCount(), 1);
        anchor.anchorBatch(keccak256("c"), keccak256("d"), 2);
        assertEq(anchor.anchorCount(), 2);
    }

    function test_unanchored_batch_returns_zeros() public view {
        (bytes32 r, bytes32 m, uint256 t) = anchor.getAnchor(999);
        assertEq(r, bytes32(0));
        assertEq(m, bytes32(0));
        assertEq(t, 0);
    }
}
