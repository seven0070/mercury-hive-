from enum import StrEnum


class OwnerStatus(StrEnum):
    """Owner account status. Uses StrEnum for clean serialization.

    Database uses VARCHAR(16) with CHECK constraint, not PostgreSQL enum,
    to allow forward-only migration without ALTER TYPE.
    """

    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
