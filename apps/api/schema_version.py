"""Schema version and constitution validation at startup."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_schema_version(session: AsyncSession) -> str | None:
    """Check that Alembic migrations have been applied.

    Returns the current revision or None if no migrations exist.
    """
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    row = result.scalar_one_or_none()
    return row
