import hashlib


def sha256_hex(content: bytes | str) -> str:
    """Compute SHA-256 hex digest of content.

    Args:
        content: Bytes or UTF-8 string to hash.

    Returns:
        Lowercase hex digest string.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()
