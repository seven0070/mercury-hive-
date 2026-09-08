"""Constitution runtime validator.

Provides utilities for checking constitutional compliance at runtime.
"""

from services.constitution.loader import Constitution


class ConstitutionValidator:
    """Runtime constitutional rule checker.

    Holds a reference to the loaded constitution and provides
    methods to check specific rules during authorization decisions.
    """

    def __init__(self, constitution: Constitution) -> None:
        self._constitution = constitution

    @property
    def constitution(self) -> Constitution:
        return self._constitution

    def is_deny_by_default(self) -> bool:
        """Check if deny-by-default is active."""
        return self._constitution.rules.get("deny_by_default", True)

    def requires_approval_for_high_risk(self) -> bool:
        """Check if high-risk actions require approval."""
        return self._constitution.rules.get("high_risk_actions_require_approval", True)

    def agents_can_modify_own_permissions(self) -> bool:
        """Check if agents can modify their own permissions. Should always be False."""
        return self._constitution.rules.get("agents_cannot_modify_own_permissions", True) is False

    def is_owner_override_enabled(self) -> bool:
        """Check if owner override is enabled. Should always be True."""
        return self._constitution.rules.get("owner_override_cannot_be_disabled", True)

    def is_emergency_shutdown_enabled(self) -> bool:
        """Check if emergency shutdown capability exists."""
        return self._constitution.rules.get("emergency_shutdown_enabled", True)

    def requires_bridge_for_cross_department(self) -> bool:
        """Check if cross-department access requires bridge."""
        return self._constitution.rules.get("cross_department_access_requires_bridge", True)

    def producer_can_verify_own_work(self) -> bool:
        """Check if producer can be sole verifier. Should always be False."""
        return self._constitution.rules.get("producer_cannot_be_sole_verifier", True) is False
