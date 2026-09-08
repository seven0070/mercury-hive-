"""Unit tests for Argon2id password hashing."""

from services.identity.hashing import hash_password, needs_rehash, verify_password


def test_hash_and_verify():
    """Argon2id hash + verify cycle works."""
    password = "a-secure-test-password-123"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True
    assert hashed != password  # Not stored as plaintext
    assert "$argon2id$" in hashed  # Correct algorithm


def test_wrong_password_fails():
    """Wrong password returns False."""
    hashed = hash_password("correct-password-here")
    assert verify_password("wrong-password-here!", hashed) is False


def test_needs_rehash_with_current_params():
    """Hash with current params does not need rehash."""
    hashed = hash_password("test-password-12345")
    assert needs_rehash(hashed) is False
