"""Interactive owner bootstrap script.

Creates the single system owner account. Uses admin database credentials.
Refuses to run if an owner already exists (singleton constraint).

Usage: python -m scripts.bootstrap_owner
       OR: make bootstrap-owner
"""

import asyncio
import getpass
import os
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.identity.hashing import hash_password  # noqa: E402

MIN_PASSWORD_LENGTH = 16
MAX_PASSWORD_LENGTH = 128


def validate_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email)) and len(email) <= 320


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password meets policy: 16-128 chars, no complexity rules."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, f"Password must be at most {MAX_PASSWORD_LENGTH} characters"
    return True, ""


async def bootstrap() -> None:
    """Create the system owner interactively."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set. Use admin credentials.", file=sys.stderr)
        sys.exit(1)

    engine = create_async_engine(database_url, pool_size=1)

    # Check if owner already exists
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM owners"))
        count = result.scalar()
        if count and count > 0:
            print("ERROR: An owner already exists. Only one owner is allowed.", file=sys.stderr)
            await engine.dispose()
            sys.exit(1)

    # Get email
    print("\n=== Mercury Hive Owner Bootstrap ===")
    print("Creating the system owner account.\n")

    email = input("Owner email: ").strip()
    if not validate_email(email):
        print("ERROR: Invalid email format.", file=sys.stderr)
        await engine.dispose()
        sys.exit(1)

    # Get password (no echo)
    password = getpass.getpass("Owner password (min 16 chars): ")
    valid, msg = validate_password(password)
    if not valid:
        print(f"ERROR: {msg}", file=sys.stderr)
        await engine.dispose()
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("ERROR: Passwords do not match.", file=sys.stderr)
        await engine.dispose()
        sys.exit(1)

    # Hash password
    password_hash_value = hash_password(password)

    # Insert owner
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO owners (id, singleton, email, password_hash, status) "
                    "VALUES (gen_random_uuid(), true, :email, :password_hash, 'ACTIVE')"
                ),
                {"email": email, "password_hash": password_hash_value},
            )
        print(f"\nOwner created successfully: {email}")
        print("You can now login via POST /auth/login")
    except Exception as e:
        error_msg = str(e)
        if "uq_owners_singleton" in error_msg or "singleton" in error_msg:
            print("ERROR: An owner already exists.", file=sys.stderr)
        else:
            print(f"ERROR: Failed to create owner: {error_msg}", file=sys.stderr)
        sys.exit(1)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
