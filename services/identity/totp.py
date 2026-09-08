"""RFC 6238 Time-based One-Time Password (TOTP) implementation.

Self-contained cryptographic MFA implementation without third-party dependencies.
Enforces 30-second window with +/- 1 window clock skew tolerance.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time


def generate_totp_secret(length: int = 20) -> str:
    """Generate a cryptographically random base32 TOTP secret."""
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _generate_hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    """Generate HOTP code for a given counter value (RFC 4226)."""
    # Normalize base32 padding
    secret_clean = secret_b32.strip().replace(" ", "").upper()
    missing_padding = len(secret_clean) % 8
    if missing_padding:
        secret_clean += "=" * (8 - missing_padding)

    secret_bytes = base64.b32decode(secret_clean, casefold=True)
    counter_bytes = struct.pack(">Q", counter)

    digest = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = str(code_int % (10**digits)).zfill(digits)
    return code


def generate_totp_code(
    secret_b32: str,
    timestamp: float | None = None,
    interval: int = 30,
    digits: int = 6,
) -> str:
    """Generate current TOTP code for secret (RFC 6238)."""
    if timestamp is None:
        timestamp = time.time()
    counter = int(timestamp // interval)
    return _generate_hotp(secret_b32, counter, digits=digits)


def verify_totp_code(
    secret_b32: str,
    code: str,
    timestamp: float | None = None,
    interval: int = 30,
    digits: int = 6,
    window: int = 1,
) -> bool:
    """Verify a TOTP code against secret allowing +/- window intervals."""
    if timestamp is None:
        timestamp = time.time()
    current_counter = int(timestamp // interval)
    code_clean = code.strip()

    if len(code_clean) != digits or not code_clean.isdigit():
        return False

    for offset in range(-window, window + 1):
        expected = _generate_hotp(secret_b32, current_counter + offset, digits=digits)
        if hmac.compare_digest(expected, code_clean):
            return True

    return False
