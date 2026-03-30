import pytest

from src.shared.crypto.merkle import MerkleTree, verify_proof


class TestMerkleTree:
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            MerkleTree([])

    def test_single_leaf(self) -> None:
        tree = MerkleTree(["leaf0"])
        assert tree.root is not None
        assert len(tree.root) == 64

    def test_single_leaf_proof_verifies(self) -> None:
        tree = MerkleTree(["leaf0"])
        proof = tree.get_proof(0)
        assert verify_proof("leaf0", proof, tree.root)

    def test_two_leaves(self) -> None:
        tree = MerkleTree(["a", "b"])
        assert verify_proof("a", tree.get_proof(0), tree.root)
        assert verify_proof("b", tree.get_proof(1), tree.root)

    def test_power_of_two_leaves(self) -> None:
        leaves = [f"leaf{i}" for i in range(4)]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            assert verify_proof(leaf, tree.get_proof(i), tree.root)

    def test_seven_leaves(self) -> None:
        leaves = [f"leaf{i}" for i in range(7)]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            assert verify_proof(leaf, tree.get_proof(i), tree.root)

    def test_nine_leaves(self) -> None:
        leaves = [f"leaf{i}" for i in range(9)]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            assert verify_proof(leaf, tree.get_proof(i), tree.root)

    def test_deterministic_root(self) -> None:
        leaves = ["a", "b", "c"]
        tree1 = MerkleTree(leaves)
        tree2 = MerkleTree(leaves)
        assert tree1.root == tree2.root

    def test_different_leaves_different_root(self) -> None:
        tree1 = MerkleTree(["a", "b"])
        tree2 = MerkleTree(["a", "c"])
        assert tree1.root != tree2.root

    def test_cross_leaf_proof_rejected(self) -> None:
        tree = MerkleTree(["a", "b", "c", "d"])
        proof_for_a = tree.get_proof(0)
        assert not verify_proof("b", proof_for_a, tree.root)

    def test_proof_index_out_of_range(self) -> None:
        tree = MerkleTree(["a", "b"])
        with pytest.raises(IndexError):
            tree.get_proof(2)
        with pytest.raises(IndexError):
            tree.get_proof(-1)

    @pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 13, 16, 31, 32, 33])
    def test_various_leaf_counts(self, n: int) -> None:
        leaves = [f"leaf{i}" for i in range(n)]
        tree = MerkleTree(leaves)
        for i, leaf in enumerate(leaves):
            assert verify_proof(leaf, tree.get_proof(i), tree.root), f"Failed for leaf {i} with {n} total leaves"
