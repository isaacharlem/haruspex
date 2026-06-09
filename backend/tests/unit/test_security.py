from haruspex_server.core.security import (
    KEY_PREFIX_LEN,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


def test_generated_keys_have_prefix_and_hash() -> None:
    key, prefix, key_hash = generate_api_key()
    assert key.startswith("hx_")
    assert prefix == key[:KEY_PREFIX_LEN]
    assert key_hash == hash_api_key(key)
    assert len(key_hash) == 64


def test_generated_keys_are_unique() -> None:
    keys = {generate_api_key()[0] for _ in range(100)}
    assert len(keys) == 100


def test_verify_accepts_correct_key() -> None:
    key, _, key_hash = generate_api_key()
    assert verify_api_key(key, key_hash)


def test_verify_rejects_wrong_key() -> None:
    _, _, key_hash = generate_api_key()
    other, _, _ = generate_api_key()
    assert not verify_api_key(other, key_hash)


def test_hash_is_deterministic_and_never_plaintext() -> None:
    key, _, _ = generate_api_key()
    assert hash_api_key(key) == hash_api_key(key)
    assert key not in hash_api_key(key)
