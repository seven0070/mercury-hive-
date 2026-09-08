"""Argon2id password hashing.

Uses argon2-cffi with OWASP/RFC 9106 recommended parameters.
Never use passlib — it is unmaintained and incompatible with Python 3.12+.
"""

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# OWASP / RFC 9106 baseline parameters
_hasher = PasswordHasher(
    time_cost=3,  # 3 iterations
    memory_cost=65536,  # 64 MiB (in KiB)
    parallelism=1,  # 1 lane — prevents thread starvation in async workers
    hash_len=32,  # 32-byte digest
    salt_len=16,  # 16-byte random salt
    type=Type.ID,  # Argon2id — hybrid mode
)


def hash_password(password: str) -> str:
    """Hash a cleartext password with Argon2id and an automatic CSPRNG salt.

    Returns the full PHC-format hash string including algorithm parameters.
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored Argon2id hash.

    Uses constant-time comparison internally.
    Returns False for any verification failure — does not distinguish
    between wrong password, corrupted hash, or invalid format.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Check if a hash was created with older/weaker parameters.

    Call this during login and rehash if True to automatically
    upgrade hash strength.
    """
    return _hasher.check_needs_rehash(password_hash)
