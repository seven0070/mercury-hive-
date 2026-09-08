"""Generate cryptographically random secrets for .env file.

Usage: python scripts/generate_secrets.py

Reads .env.example, fills in blank values with random secrets,
writes to .env. Does NOT overwrite existing .env.
"""

import secrets
import sys
from pathlib import Path


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically random hex string."""
    return secrets.token_hex(length)


def main() -> None:
    env_path = Path(".env")
    example_path = Path(".env.example")

    if env_path.exists():
        print(
            "ERROR: .env already exists. Delete it first if you want to regenerate.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not example_path.exists():
        print("ERROR: .env.example not found.", file=sys.stderr)
        sys.exit(1)

    # Fields that need generated secrets
    secret_fields = {
        "POSTGRES_ADMIN_PASSWORD": generate_secret(24),
        "POSTGRES_RUNTIME_PASSWORD": generate_secret(24),
        "JWT_SECRET_KEY": generate_secret(32),
    }

    lines = []
    for line in example_path.read_text().splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            value = stripped.split("=", 1)[1].strip()
            if key in secret_fields and not value:
                line = f"{key}={secret_fields[key]}"
        lines.append(line)

    env_path.write_text("\n".join(lines) + "\n")
    print(f"Generated .env with {len(secret_fields)} secrets.")
    print("Review and adjust values as needed.")


if __name__ == "__main__":
    main()
