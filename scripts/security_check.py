"""Security check script.

Runs basic security validations:
1. .env is gitignored
2. .env is not tracked
3. No secrets in tracked files or git history
4. Dependencies have no known vulnerabilities

Usage: python scripts/security_check.py
"""

import re
import subprocess
import sys

SECRET_PATTERNS = (
    "password=",
    "secret_key=",
    "POSTGRES_ADMIN_PASSWORD=",
    "JWT_SECRET_KEY=",
)

SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?m)^[+\-]?[ \t]*(?:export[ \t]+)?"
    r"(?:POSTGRES_ADMIN_PASSWORD|JWT_SECRET_KEY|SECRET_KEY|API_KEY|TRIBE_WEBHOOK_SECRET)"
    r"[ \t]*=[ \t]*"
    r"(?!(?:$|[\"']?[\s#]|\$\{))[^\r\n]+"
)


def check_env_gitignored() -> bool:
    """Check that .env is in .gitignore."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", ".env"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("FAIL: .env is not gitignored")
            return False
        print("PASS: .env is gitignored")
        return True
    except FileNotFoundError:
        print("SKIP: git not installed (container environment)")
        return True


def check_env_not_tracked() -> bool:
    """Check that .env is not tracked in git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", ".env"],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            print("CRITICAL: .env is tracked in git!")
            return False
        print("PASS: .env is not tracked")
        return True
    except FileNotFoundError:
        print("SKIP: git not installed (container environment)")
        return True


def check_no_secrets_in_code() -> bool:
    """Basic check for common secret patterns in tracked files."""
    try:
        result = subprocess.run(
            ["git", "grep", "-l", "--"] + list(SECRET_PATTERNS),
            capture_output=True,
            text=True,
        )
        # Filter out .env.example and this script
        files = [
            f
            for f in result.stdout.strip().split("\n")
            if f
            and not f.endswith(".example")
            and not f.endswith("security_check.py")
            and not f.endswith("conftest.py")
            and not f.endswith(".sh")
        ]
        if files:
            print(f"WARNING: Possible secrets found in: {files}")
            return False
        print("PASS: No obvious secrets in tracked files")
        return True
    except FileNotFoundError:
        print("SKIP: git not installed (container environment)")
        return True


def check_no_secrets_in_history() -> bool:
    """Check all reachable git history for common secret assignments."""
    try:
        result = subprocess.run(
            ["git", "log", "--all", "-p", "--no-ext-diff", "--"] ,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        history = result.stdout or ""
        findings = [
            finding.strip()
            for finding in SECRET_ASSIGNMENT_PATTERN.findall(history)
            if not re.search(r"(?i)(test|example|placeholder|changeme|\$\{)", finding)
        ]
        if findings:
            print(f"CRITICAL: Possible secrets found in git history: {findings}")
            return False
        print("PASS: No obvious secrets found in git history")
        return True
    except FileNotFoundError:
        print("SKIP: git not installed (container environment)")
        return True


DEV_IGNORED_VULNERABILITIES = [
    # pytest 8.4.2 constraint required by pytest-asyncio < 1.0 (awaiting pytest 9 upstream compat)
    "PYSEC-2026-1845",
    # Base container pip build-time advisories (unused at runtime)
    "PYSEC-2026-196",
    "PYSEC-2026-1795",
    "PYSEC-2026-1796",
    "PYSEC-2026-2875",
    "PYSEC-2026-2876",
    "PYSEC-2026-3721",
]


def check_dependencies() -> bool:
    """Run pip-audit for known vulnerabilities."""
    cmd = [sys.executable, "-m", "pip_audit"]
    for vuln_id in DEV_IGNORED_VULNERABILITIES:
        cmd.extend(["--ignore-vuln", vuln_id])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"FAIL: Vulnerability found:\n{result.stdout}")
            return False
        print("PASS: No known vulnerabilities (production packages 100% clean)")
        return True
    except FileNotFoundError:
        print("SKIP: pip-audit not installed")
        return True


def main() -> None:
    print("=== Mercury Hive Security Check ===")
    results = [
        check_env_gitignored(),
        check_env_not_tracked(),
        check_dependencies(),
        check_no_secrets_in_code(),
        check_no_secrets_in_history(),
    ]
    if all(results):
        print("\nAll security checks passed.")
    else:
        print("\nSome security checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
