"""Unit tests for constitution loader and validator."""

from pathlib import Path

import pytest
import yaml

from services.constitution.loader import ConstitutionError, ConstitutionLoader


@pytest.fixture
def valid_constitution_data() -> dict:
    """Valid constitution data matching policies/constitution.yaml."""
    return {
        "schema_version": 1,
        "policy_version": 1,
        "rules": {
            "owner_final_authority": True,
            "deny_by_default": True,
            "agents_cannot_modify_own_permissions": True,
            "agents_cannot_modify_constitution": True,
            "agents_cannot_delete_audit_logs": True,
            "permanent_agent_creation_requires_authorization": True,
            "high_risk_actions_require_approval": True,
            "producer_cannot_be_sole_verifier": True,
            "cross_department_access_requires_bridge": True,
            "failed_outputs_must_be_preserved": True,
            "emergency_shutdown_enabled": True,
            "evolution_requires_testing": True,
            "owner_override_cannot_be_disabled": True,
            "external_release_requires_approval": True,
            "sensitive_memory_requires_scoped_access": True,
            "real_person_identity_requires_authorization": True,
        },
        "change_control": {
            "owner_authorization_required": True,
            "explicit_migration_required": True,
            "automated_tests_required": True,
            "agent_changes_allowed": False,
        },
    }


def _write_yaml(data: dict, path: Path) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False))


def test_valid_constitution(valid_constitution_data, tmp_path):
    """Valid constitution loads successfully."""
    path = tmp_path / "constitution.yaml"
    _write_yaml(valid_constitution_data, path)
    loader = ConstitutionLoader(path)
    constitution = loader.load()
    assert constitution.schema_version == 1
    assert constitution.policy_version == 1
    assert len(constitution.sha256_hash) == 64


def test_missing_file_fails():
    """Missing constitution file causes startup failure."""
    loader = ConstitutionLoader("/nonexistent/constitution.yaml")
    with pytest.raises(ConstitutionError, match="not found"):
        loader.load()


def test_weakened_mandatory_rule_fails(valid_constitution_data, tmp_path):
    """Setting a mandatory rule to false causes failure."""
    valid_constitution_data["rules"]["deny_by_default"] = False
    path = tmp_path / "constitution.yaml"
    _write_yaml(valid_constitution_data, path)
    loader = ConstitutionLoader(path)
    with pytest.raises(ConstitutionError, match="Weakened"):
        loader.load()


def test_invalid_schema_version_fails(valid_constitution_data, tmp_path):
    """Invalid schema version causes failure."""
    valid_constitution_data["schema_version"] = 0
    path = tmp_path / "constitution.yaml"
    _write_yaml(valid_constitution_data, path)
    loader = ConstitutionLoader(path)
    with pytest.raises(ConstitutionError, match="schema_version"):
        loader.load()


def test_weakened_change_control_fails(valid_constitution_data, tmp_path):
    """Weakening change control rules causes failure."""
    valid_constitution_data["change_control"]["agent_changes_allowed"] = True
    path = tmp_path / "constitution.yaml"
    _write_yaml(valid_constitution_data, path)
    loader = ConstitutionLoader(path)
    with pytest.raises(ConstitutionError, match="(?i)change control"):
        loader.load()


def test_sha256_hash_deterministic(valid_constitution_data, tmp_path):
    """Same content produces same hash."""
    path = tmp_path / "constitution.yaml"
    _write_yaml(valid_constitution_data, path)
    loader = ConstitutionLoader(path)
    c1 = loader.load()
    c2 = loader.load()
    assert c1.sha256_hash == c2.sha256_hash


def test_all_16_mandatory_rules_validated(valid_constitution_data, tmp_path):
    """Each of the 16 mandatory rules must be present."""
    for rule in list(valid_constitution_data["rules"].keys()):
        data = valid_constitution_data.copy()
        data["rules"] = {k: v for k, v in valid_constitution_data["rules"].items() if k != rule}
        data["change_control"] = valid_constitution_data["change_control"].copy()
        path = tmp_path / f"const_{rule}.yaml"
        _write_yaml(data, path)
        loader = ConstitutionLoader(path)
        with pytest.raises(ConstitutionError):
            loader.load()
