"""Fail-closed constitution loader.

Validates and loads the constitutional rules file during application startup.
If the constitution is missing, invalid, or weakened, the application MUST NOT start.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConstitutionError(Exception):
    """Raised when the constitution is invalid. Application must not start."""


# Every mandatory rule must exist and be true
MANDATORY_RULES = frozenset(
    {
        "owner_final_authority",
        "deny_by_default",
        "agents_cannot_modify_own_permissions",
        "agents_cannot_modify_constitution",
        "agents_cannot_delete_audit_logs",
        "permanent_agent_creation_requires_authorization",
        "high_risk_actions_require_approval",
        "producer_cannot_be_sole_verifier",
        "cross_department_access_requires_bridge",
        "failed_outputs_must_be_preserved",
        "emergency_shutdown_enabled",
        "evolution_requires_testing",
        "owner_override_cannot_be_disabled",
        "external_release_requires_approval",
        "sensitive_memory_requires_scoped_access",
        "real_person_identity_requires_authorization",
    }
)

# Change control rules that must be true
CHANGE_CONTROL_REQUIRED_TRUE = frozenset(
    {
        "owner_authorization_required",
        "explicit_migration_required",
        "automated_tests_required",
    }
)

# Change control rules that must be false
CHANGE_CONTROL_REQUIRED_FALSE = frozenset(
    {
        "agent_changes_allowed",
    }
)


@dataclass(frozen=True)
class Constitution:
    """Validated constitution with computed hash."""

    schema_version: int
    policy_version: int
    rules: dict[str, bool]
    change_control: dict[str, bool]
    sha256_hash: str
    raw_content: bytes = field(repr=False)


class ConstitutionLoader:
    """Loads and validates the constitution file.

    Fail-closed: any validation failure raises ConstitutionError,
    preventing application startup.
    """

    def __init__(self, constitution_path: str | Path) -> None:
        self._path = Path(constitution_path)

    def load(self) -> Constitution:
        """Load, validate, and return the constitution.

        Raises:
            ConstitutionError: If the file is missing, invalid, or weakened.
        """
        raw_content = self._read_file()
        sha256_hash = self._compute_hash(raw_content)
        data = self._parse_yaml(raw_content)
        self._validate_structure(data)
        self._validate_schema_version(data)
        self._validate_policy_version(data)
        self._validate_mandatory_rules(data)
        self._validate_change_control(data)

        return Constitution(
            schema_version=data["schema_version"],
            policy_version=data["policy_version"],
            rules=data["rules"],
            change_control=data["change_control"],
            sha256_hash=sha256_hash,
            raw_content=raw_content,
        )

    def _read_file(self) -> bytes:
        """Read the constitution file. Fail if missing."""
        if not self._path.exists():
            raise ConstitutionError(
                f"Constitution file not found: {self._path}. "
                "Application cannot start without a valid constitution."
            )
        return self._path.read_bytes()

    @staticmethod
    def _compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of raw file content."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _parse_yaml(content: bytes) -> dict:
        """Parse YAML content. Fail on invalid YAML."""
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ConstitutionError(f"Invalid YAML in constitution: {e}") from e

        if not isinstance(data, dict):
            raise ConstitutionError("Constitution must be a YAML mapping")

        return data

    @staticmethod
    def _validate_structure(data: dict) -> None:
        """Validate required top-level keys."""
        required_keys = {"schema_version", "policy_version", "rules", "change_control"}
        missing = required_keys - set(data.keys())
        if missing:
            raise ConstitutionError(f"Missing required keys: {missing}")

    @staticmethod
    def _validate_schema_version(data: dict) -> None:
        """Validate schema version is a positive integer."""
        version = data.get("schema_version")
        if not isinstance(version, int) or version < 1:
            raise ConstitutionError(
                f"Invalid schema_version: {version}. Must be a positive integer."
            )

    @staticmethod
    def _validate_policy_version(data: dict) -> None:
        """Validate policy version is a positive integer."""
        version = data.get("policy_version")
        if not isinstance(version, int) or version < 1:
            raise ConstitutionError(
                f"Invalid policy_version: {version}. Must be a positive integer."
            )

    @staticmethod
    def _validate_mandatory_rules(data: dict) -> None:
        """Validate all mandatory rules exist and are true."""
        rules = data.get("rules", {})
        if not isinstance(rules, dict):
            raise ConstitutionError("'rules' must be a mapping")

        missing = MANDATORY_RULES - set(rules.keys())
        if missing:
            raise ConstitutionError(f"Missing mandatory rules: {missing}")

        weakened = [rule for rule in MANDATORY_RULES if rules.get(rule) is not True]
        if weakened:
            raise ConstitutionError(f"Weakened mandatory rules (must be true): {weakened}")

    @staticmethod
    def _validate_change_control(data: dict) -> None:
        """Validate change control rules are not weakened."""
        cc = data.get("change_control", {})
        if not isinstance(cc, dict):
            raise ConstitutionError("'change_control' must be a mapping")

        # Rules that must be true
        for rule in CHANGE_CONTROL_REQUIRED_TRUE:
            if rule not in cc:
                raise ConstitutionError(f"Missing change_control rule: {rule}")
            if cc[rule] is not True:
                raise ConstitutionError(
                    f"Change control rule '{rule}' must be true, got: {cc[rule]}"
                )

        # Rules that must be false
        for rule in CHANGE_CONTROL_REQUIRED_FALSE:
            if rule not in cc:
                raise ConstitutionError(f"Missing change_control rule: {rule}")
            if cc[rule] is not False:
                raise ConstitutionError(
                    f"Change control rule '{rule}' must be false, got: {cc[rule]}"
                )
