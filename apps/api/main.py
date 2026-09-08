"""Mercury Hive API application factory.

Startup sequence:
1. Load and validate constitution (fail-closed)
2. Create database engines (primary and dedicated persistent audit engine)
3. Verify database connectivity
4. Verify Alembic migration state
5. Start serving

If any startup check fails, the application does not start.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.config import RuntimeSettings
from apps.api.database import create_engine, create_session_factory
from services.agent_registry.router import router as agent_router
from services.bridges.router import router as bridge_router
from services.constitution.loader import ConstitutionError, ConstitutionLoader
from services.evolution.router import router as evolution_router
from services.governance.router import router as governance_router
from services.identity.router import router as auth_router
from services.judging.router import router as judging_router
from services.memory.router import router as memory_router
from services.rollback.router import router as rollback_router
from services.tasks.router import router as task_router
from services.tools.router import router as tool_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup checks and cleanup."""
    settings = RuntimeSettings()
    app.state.settings = settings

    # 1. Load and validate constitution — fail closed
    try:
        loader = ConstitutionLoader(settings.constitution_path)
        constitution = loader.load()
        app.state.constitution = constitution
        logger.info(
            "constitution_loaded",
            schema_version=constitution.schema_version,
            policy_version=constitution.policy_version,
            sha256=constitution.sha256_hash[:12],
        )
    except ConstitutionError as e:
        logger.critical("constitution_validation_failed", error=str(e))
        raise SystemExit(1) from e

    # 2. Create primary database engine (runtime credentials only)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory

    # 3. Create dedicated persistent audit engine to avoid connection churn
    audit_engine = create_async_engine(
        settings.database_url,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
    )
    app.state.audit_engine = audit_engine

    # 4. Verify database connectivity
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info("database_connected")
    except Exception as e:
        logger.critical("database_connection_failed", error=str(e))
        raise SystemExit(1) from e

    # 5. Verify Alembic migration state
    try:
        async with session_factory() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            revision = result.scalar_one_or_none()
            if revision is None:
                logger.critical("no_migrations_applied")
                raise SystemExit(1)
            logger.info("schema_verified", revision=revision)
    except SystemExit:
        raise
    except Exception as e:
        logger.critical("schema_check_failed", error=str(e))
        raise SystemExit(1) from e

    logger.info("mercury_hive_started")
    yield

    # Cleanup
    await audit_engine.dispose()
    await engine.dispose()
    logger.info("mercury_hive_stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Mercury Hive",
        description="Governed virtual AI company API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    # Health endpoints (no auth required)
    @app.get("/health/live")
    async def health_live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def health_ready():
        """Readiness probe: checks DB connectivity, schema migration,
        and re-hashes constitution on disk.
        """
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
                result = await session.execute(text("SELECT version_num FROM alembic_version"))
                revision = result.scalar_one_or_none()
        except Exception:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "reason": "database"}
            )

        if revision is None:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "reason": "no_migration"}
            )

        # Active check: re-read and hash constitution on disk, ensure it matches loaded hash
        try:
            loader = ConstitutionLoader(app.state.settings.constitution_path)
            disk_constitution = loader.load()
            if disk_constitution.sha256_hash != app.state.constitution.sha256_hash:
                return JSONResponse(
                    status_code=503,
                    content={"status": "not_ready", "reason": "constitution_hash_mismatch"},
                )
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "constitution_invalid_or_missing"},
            )

        return {
            "status": "ready",
            "revision": revision,
            "constitution_hash": app.state.constitution.sha256_hash[:12],
        }

    # Auth, Governance, Agents, Bridges, Tasks, Tools, Memory, & Rollback routes
    app.include_router(auth_router)
    app.include_router(governance_router)
    app.include_router(agent_router)
    app.include_router(bridge_router)
    app.include_router(task_router)
    app.include_router(tool_router)
    app.include_router(memory_router)
    app.include_router(rollback_router)
    app.include_router(judging_router)
    app.include_router(evolution_router)

    return app
