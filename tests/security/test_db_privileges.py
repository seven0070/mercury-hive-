"""Database privilege tests.

These tests connect as mercury_test_runtime (the runtime role) using a
synchronous psycopg2 connection to prove that column-level privileges
are correctly enforced.

These tests require:
- Test database running (docker-compose.test.yml)
- Migrations applied
- Privileges applied
"""

import os

import pytest

# Skip if psycopg2 not available
psycopg2 = pytest.importorskip("psycopg2")


@pytest.fixture(scope="module")
def runtime_conn():
    """Synchronous connection as mercury_test_runtime."""
    dsn = os.environ.get(
        "DATABASE_TEST_RUNTIME_SYNC",
        "postgresql://mercury_test_runtime:test_runtime_password@localhost:5433/mercury_hive_test",
    )
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    yield conn
    conn.close()


def test_runtime_is_not_superuser(runtime_conn):
    """Runtime role must not be a superuser."""
    cur = runtime_conn.cursor()
    cur.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
    row = cur.fetchone()
    assert row is not None
    assert row[1] is False, "Runtime role must not be superuser"


def test_cannot_update_password_hash(runtime_conn):
    """Runtime role cannot UPDATE owners.password_hash."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE owners SET password_hash = 'hacked' WHERE email = 'x'")
    runtime_conn.rollback()


def test_cannot_update_email(runtime_conn):
    """Runtime role cannot UPDATE owners.email."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE owners SET email = 'hacked@evil.com' WHERE id = gen_random_uuid()")
    runtime_conn.rollback()


def test_cannot_update_status(runtime_conn):
    """Runtime role cannot UPDATE owners.status."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE owners SET status = 'LOCKED' WHERE email = 'x'")
    runtime_conn.rollback()


def test_cannot_delete_owners(runtime_conn):
    """Runtime role cannot DELETE from owners."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM owners WHERE email = 'x'")
    runtime_conn.rollback()


def test_cannot_create_table(runtime_conn):
    """Runtime role cannot execute DDL."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("CREATE TABLE hack_table (id serial)")
    runtime_conn.rollback()


def test_cannot_update_session_expires_at(runtime_conn):
    """Runtime role cannot UPDATE owner_sessions.expires_at."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE owner_sessions SET expires_at = now() + interval '100 days'")
    runtime_conn.rollback()


def test_cannot_update_token_hash(runtime_conn):
    """Runtime role cannot UPDATE refresh_tokens.token_hash."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE refresh_tokens SET token_hash = 'forged'")
    runtime_conn.rollback()


def test_cannot_delete_audit_events(runtime_conn):
    """Runtime role cannot DELETE from audit_events."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM audit_events")
    runtime_conn.rollback()


def test_cannot_update_audit_events(runtime_conn):
    """Runtime role cannot UPDATE audit_events."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE audit_events SET event_type = 'forged'")
    runtime_conn.rollback()


def test_can_select_owner_fields(runtime_conn):
    """Runtime role CAN SELECT allowed owner columns."""
    cur = runtime_conn.cursor()
    cur.execute("SELECT id, email, status, created_at, last_login_at FROM owners LIMIT 1")
    # Should not raise


def test_can_insert_session(runtime_conn):
    """Runtime role CAN INSERT owner_sessions (allowed columns)."""
    cur = runtime_conn.cursor()
    # Get an owner ID first
    cur.execute("SELECT id FROM owners LIMIT 1")
    row = cur.fetchone()
    if row:
        owner_id = row[0]
        try:
            cur.execute(
                "INSERT INTO owner_sessions (id, owner_id, expires_at) "
                "VALUES (gen_random_uuid(), %s, now() + interval '7 days')",
                (owner_id,),
            )
        except Exception:
            runtime_conn.rollback()
            pytest.fail("Runtime role should be able to insert sessions")
