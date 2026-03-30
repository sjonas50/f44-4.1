import hashlib

from src.shared.crypto.hashing import sha256_hex


class TestSha256Hex:
    def test_string_input(self) -> None:
        result = sha256_hex("hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert result == expected

    def test_bytes_input(self) -> None:
        result = sha256_hex(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert result == expected

    def test_empty_string(self) -> None:
        result = sha256_hex("")
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_deterministic(self) -> None:
        assert sha256_hex("test") == sha256_hex("test")

    def test_different_inputs_different_hashes(self) -> None:
        assert sha256_hex("a") != sha256_hex("b")

    def test_lowercase_hex(self) -> None:
        result = sha256_hex("test")
        assert result == result.lower()
        assert len(result) == 64
