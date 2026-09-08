# Constitution

## Overview

The Mercury Hive constitution defines immutable governance rules.
The constitution file is loaded and validated at application startup.
If validation fails, the application does not start.

## Rules

16 mandatory rules that must all be `true`:

1. owner_final_authority
2. deny_by_default
3. agents_cannot_modify_own_permissions
4. agents_cannot_modify_constitution
5. agents_cannot_delete_audit_logs
6. permanent_agent_creation_requires_authorization
7. high_risk_actions_require_approval
8. producer_cannot_be_sole_verifier
9. cross_department_access_requires_bridge
10. failed_outputs_must_be_preserved
11. emergency_shutdown_enabled
12. evolution_requires_testing
13. owner_override_cannot_be_disabled
14. external_release_requires_approval
15. sensitive_memory_requires_scoped_access
16. real_person_identity_requires_authorization

## Change Control

Constitution changes require:
1. Owner authorization
2. Forward migration
3. New tests
4. Security review
5. Version increment
6. Hash update
7. Audit record

## Validation

- File missing → application fails to start
- Rule weakened → application fails to start
- Invalid version → application fails to start
- SHA-256 hash computed and stored for integrity verification
