"""Security tests proving audit table hardening and write-through DB function."""

import os
import uuid

import pytest

psycopg2 = pytest.importorskip("psycopg2")


@pytest.fixture(scope="module")
def runtime_conn():
    """Synchronous connection as mercury_test_runtime."""
    dsn = os.environ.get(
        "DATABASE_TEST_RUNTIME_SYNC",
        "postgresql://mercury_test_runtime:test_runtime_password@postgres-test:5432/mercury_hive_test",
    )
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    yield conn
    conn.close()


def test_runtime_cannot_directly_insert_audit_events(runtime_conn):
    """Direct table INSERT on audit_events must be DENIED to runtime role."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute(
            "INSERT INTO audit_events (id, event_type, action) "
            "VALUES (gen_random_uuid(), 'AUTH', 'forged_login')"
        )
    runtime_conn.rollback()


def test_runtime_can_log_via_security_definer_function(runtime_conn):
    """Runtime role CAN write audit records strictly through fn_record_audit_event."""
    cur = runtime_conn.cursor()
    actor_id = str(uuid.uuid4())
    cur.execute(
        """
        SELECT fn_record_audit_event(
            'AUTH',
            %s::uuid,
            'OWNER',
            NULL,
            NULL,
            'login',
            'ALLOW',
            'authenticated_successfully',
            NULL,
            NULL
        )
        """,
        (actor_id,),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] is not None  # Generated UUID returned


def test_runtime_cannot_update_or_delete_audit_events(runtime_conn):
    """Runtime role cannot mutate or delete audit log entries."""
    cur = runtime_conn.cursor()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE audit_events SET reason = 'tampered'")
    runtime_conn.rollback()

    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM audit_events")
    runtime_conn.rollback()
