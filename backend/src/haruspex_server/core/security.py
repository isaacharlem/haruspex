"""API key generation and verification. Keys are hashed at rest, never logged."""

import hashlib
import secrets

KEY_PREFIX_LEN = 8
SCOPE_INGEST = "ingest"
SCOPE_READ = "read"
SCOPE_ADMIN = "admin"
ALL_SCOPES = frozenset({SCOPE_INGEST, SCOPE_READ, SCOPE_ADMIN})


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(plaintext_key, key_prefix, key_hash)``.

    The plaintext is shown exactly once at creation; only prefix + sha256 are stored.
    """
    key = "hx_" + secrets.token_urlsafe(32)
    return key, key[:KEY_PREFIX_LEN], hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_api_key(presented_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of the presented key's hash against the stored hash."""
    return secrets.compare_digest(hash_api_key(presented_key), stored_hash)
