"""Phase 10: 3D Workspace Contracts, Avatars, Presence & Virtual Meetings.

Revision ID: 009_phase10
Revises: 008_phase8
Create Date: 2026-09-08

Forward-only migration. Creates:
- workspace_zones table + seeds default spatial zones
- avatar_profiles table (governed appearance contracts & attire)
- presence_sessions table (spatial coordinates & presence state)
- virtual_meetings table (boardroom conclaves and meetings)
- meeting_participants table (meeting attendees & roles)
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "009_phase10"
down_revision: str | None = "008_phase8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ZONES = [
    (
        "Executive Boardroom",
        "BOARDROOM",
        30,
        "RESTRICTED",
        {"min_x": -15.0, "max_x": 15.0, "min_y": -10.0, "max_y": 10.0, "min_z": 0.0, "max_z": 5.0},
    ),
    (
        "Central Commons & Forum",
        "COMMONS",
        150,
        "PUBLIC",
        {"min_x": -50.0, "max_x": 50.0, "min_y": -50.0, "max_y": 50.0, "min_z": 0.0, "max_z": 8.0},
    ),
    (
        "Secure Cryptographic Vault",
        "SECURE_VAULT",
        10,
        "RESTRICTED",
        {"min_x": -5.0, "max_x": 5.0, "min_y": -5.0, "max_y": 5.0, "min_z": -5.0, "max_z": 0.0},
    ),
]


def upgrade() -> None:
    # === workspace_zones ===
    op.create_table(
        "workspace_zones",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("zone_type", sa.String(32), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("capacity", sa.Integer(), server_default=sa.text("20"), nullable=False),
        sa.Column(
            "security_level",
            sa.String(32),
            server_default=sa.text("'CONFIDENTIAL'"),
            nullable=False,
        ),
        sa.Column("spatial_bounds", JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_zones")),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_workspace_zones_department_id_departments"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "zone_type IN ('EXECUTIVE_SUITE', 'DEPARTMENT_POD', 'BOARDROOM', "
            "'AUDITORIUM', 'SECURE_VAULT', 'COMMONS')",
            name=op.f("ck_workspace_zones_valid_type"),
        ),
        sa.CheckConstraint(
            "security_level IN ('PUBLIC', 'CONFIDENTIAL', 'RESTRICTED')",
            name=op.f("ck_workspace_zones_security_level"),
        ),
    )
    op.create_index("ix_workspace_zones_type", "workspace_zones", ["zone_type"])

    # Seed initial zones
    for name, z_type, cap, sec, bounds in DEFAULT_ZONES:
        op.execute(
            sa.text(
                "INSERT INTO workspace_zones "
                "(id, name, zone_type, capacity, security_level, spatial_bounds) "
                "VALUES (gen_random_uuid(), :name, :z_type, :cap, :sec, CAST(:bounds AS jsonb))"
            ).bindparams(
                name=name,
                z_type=z_type,
                cap=cap,
                sec=sec,
                bounds=json.dumps(bounds),
            )
        )

    # === avatar_profiles ===
    op.create_table(
        "avatar_profiles",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("avatar_model_uri", sa.String(512), nullable=False),
        sa.Column("attire_class", sa.String(32), nullable=False),
        sa.Column("customization_payload", JSONB(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avatar_profiles")),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_avatar_profiles_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["owners.id"],
            name=op.f("fk_avatar_profiles_approved_by_owners"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "attire_class IN ('EXECUTIVE_FORMAL', 'BUSINESS_PROFESSIONAL', "
            "'TECHNICAL_SMART', 'STANDARD_UTILITY')",
            name=op.f("ck_avatar_profiles_attire"),
        ),
    )
    op.create_index("ix_avatar_profiles_agent_id", "avatar_profiles", ["agent_id"])

    # === presence_sessions ===
    op.create_table(
        "presence_sessions",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(32), server_default=sa.text("'AGENT'"), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column(
            "position_x",
            sa.Numeric(8, 2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "position_y",
            sa.Numeric(8, 2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "position_z",
            sa.Numeric(8, 2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "rotation_yaw",
            sa.Numeric(6, 2),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "presence_state",
            sa.String(32),
            server_default=sa.text("'ONLINE'"),
            nullable=False,
        ),
        sa.Column("current_task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presence_sessions")),
        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["workspace_zones.id"],
            name=op.f("fk_presence_sessions_zone_id_workspace_zones"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_task_id"],
            ["tasks.id"],
            name=op.f("fk_presence_sessions_current_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "presence_state IN ('ONLINE', 'IN_MEETING', 'IDLE', 'OFFLINE')",
            name=op.f("ck_presence_sessions_state"),
        ),
        sa.CheckConstraint(
            "entity_type IN ('OWNER', 'AGENT')",
            name=op.f("ck_presence_sessions_entity_type"),
        ),
    )
    op.create_index("ix_presence_sessions_entity", "presence_sessions", ["entity_id"])
    op.create_index("ix_presence_sessions_zone", "presence_sessions", ["zone_id"])

    # === virtual_meetings ===
    op.create_table(
        "virtual_meetings",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=False),
        sa.Column("host_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default=sa.text("'SCHEDULED'"),
            nullable=False,
        ),
        sa.Column("agenda", sa.Text(), nullable=True),
        sa.Column("meeting_minutes", JSONB(), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_virtual_meetings")),
        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["workspace_zones.id"],
            name=op.f("fk_virtual_meetings_zone_id_workspace_zones"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'IN_PROGRESS', 'CONCLUDED', 'CANCELLED')",
            name=op.f("ck_virtual_meetings_status"),
        ),
    )
    op.create_index("ix_virtual_meetings_zone_id", "virtual_meetings", ["zone_id"])

    # === meeting_participants ===
    op.create_table(
        "meeting_participants",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role_in_meeting",
            sa.String(32),
            server_default=sa.text("'ATTENDEE'"),
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meeting_participants")),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["virtual_meetings.id"],
            name=op.f("fk_meeting_participants_meeting_id_virtual_meetings"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role_in_meeting IN ('HOST', 'SPEAKER', 'ATTENDEE', 'OBSERVER')",
            name=op.f("ck_meeting_participants_role"),
        ),
    )
    op.create_index(
        "ix_meeting_participants_meeting_id",
        "meeting_participants",
        ["meeting_id"],
    )


def downgrade() -> None:
    # Forward-only migration; downgrade provided for test harnesses
    op.drop_table("meeting_participants")
    op.drop_table("virtual_meetings")
    op.drop_table("presence_sessions")
    op.drop_table("avatar_profiles")
    op.drop_table("workspace_zones")
