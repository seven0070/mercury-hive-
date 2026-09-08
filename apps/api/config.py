"""Application configuration using Pydantic Settings.

Three separate settings classes enforce credential separation:
- RuntimeSettings: for the API server (mercury_runtime only)
- MigrationSettings: for Alembic migrations (mercury_admin only)
- BootstrapSettings: for owner bootstrap (mercury_admin only)

The API container NEVER receives admin credentials.
"""

from pydantic_settings import BaseSettings


class RuntimeSettings(BaseSettings):
    """Settings for the runtime API. Only mercury_runtime credentials."""

    database_url: str  # postgresql+asyncpg://mercury_runtime:...
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "mercury-hive"
    jwt_audience: str = "mercury-hive-api"
    jwt_access_token_minutes: int = 5
    jwt_refresh_token_hours: int = 24
    jwt_session_days: int = 7
    constitution_path: str = "policies/constitution.yaml"
    log_level: str = "INFO"

    model_config = {"env_prefix": "", "case_sensitive": False}


class MigrationSettings(BaseSettings):
    """Settings for admin operations. Only used by admin service."""

    database_url: str  # postgresql+asyncpg://mercury_admin:...

    model_config = {"env_prefix": "", "case_sensitive": False}


class BootstrapSettings(BaseSettings):
    """Settings for owner bootstrap. Only used by admin service."""

    database_url: str  # postgresql+asyncpg://mercury_admin:...

    model_config = {"env_prefix": "", "case_sensitive": False}
