from enum import StrEnum


class SystemRole(StrEnum):
    """System roles for the Mercury Hive hierarchy.

    Phase 1 only implements OWNER. Other roles are defined
    for forward compatibility but not enforced until Phase 3+.
    """

    OWNER = "OWNER"
    CEO = "CEO"
    HR = "HR"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    WORKER = "WORKER"
    VERIFIER = "VERIFIER"
    JUDGE = "JUDGE"
    TEMPORARY_SUB_AGENT = "TEMPORARY_SUB_AGENT"
