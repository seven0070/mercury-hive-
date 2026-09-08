import json
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import RuntimeSettings
from apps.api.dependencies import (
    AuthenticatedOwner,
    get_current_owner,
    get_db,
    get_optional_db,
    get_settings,
    verify_shutdown_state,
)
from domain.schemas.tribe import (
    AgentSkillCreate,
    AgentSkillResponse,
    AgentSkillVerify,
    ExternalTaskIngestRequest,
    TaskSyncCreate,
    TaskSyncResponse,
    TribeMappingCreate,
    TribeMappingResponse,
    WebhookResponse,
)
from services.tribe.security import (
    idempotency_tracker,
    verify_timestamp_and_nonce,
    verify_webhook_signature,
)
from services.tribe.service import (
    TribeError,
    create_tribe_mapping,
    ingest_external_task,
    list_agent_skills,
    list_task_sync_mappings,
    list_tribe_mappings,
    register_agent_skill,
    sync_task_mapping,
    verify_agent_skill,
)

logger = structlog.get_logger()

_webhook_execution_count = 0


def get_webhook_execution_count() -> int:
    """Get count of executed webhook business logic invocations (for testing)."""
    return _webhook_execution_count


def reset_webhook_execution_count() -> None:
    """Reset the webhook business logic invocation counter."""
    global _webhook_execution_count
    _webhook_execution_count = 0


router = APIRouter(prefix="/tribe", tags=["tribe"])


@router.post(
    "/mappings",
    response_model=TribeMappingResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_create_tribe_mapping(
    request: TribeMappingCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TribeMappingResponse:
    """Map a department to an external Tribe/Squad topology."""
    try:
        mapping = await create_tribe_mapping(
            session=session,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TribeMappingResponse.model_validate(mapping)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/mappings",
    response_model=list[TribeMappingResponse],
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_list_tribe_mappings(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    department_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[TribeMappingResponse]:
    """List department-to-tribe mappings."""
    mappings = await list_tribe_mappings(session=session, department_id=department_id)
    return [TribeMappingResponse.model_validate(m) for m in mappings]


@router.post(
    "/skills/{agent_id}",
    response_model=AgentSkillResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_register_agent_skill(
    agent_id: uuid.UUID,
    request: AgentSkillCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentSkillResponse:
    """Register or update an agent capability in the skill matrix."""
    try:
        skill = await register_agent_skill(
            session=session,
            agent_id=agent_id,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return AgentSkillResponse.model_validate(skill)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/skills/{skill_id}/verify",
    response_model=AgentSkillResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_verify_agent_skill(
    skill_id: uuid.UUID,
    request: AgentSkillVerify,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> AgentSkillResponse:
    """Certify and verify an agent skill."""
    try:
        skill = await verify_agent_skill(
            session=session,
            skill_id=skill_id,
            is_verified=request.is_verified,
            verifier_id=owner.owner_id,
            verifier_role="OWNER",
        )
        return AgentSkillResponse.model_validate(skill)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/skills/{agent_id}",
    response_model=list[AgentSkillResponse],
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_list_agent_skills(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> list[AgentSkillResponse]:
    """List all registered skills for an agent."""
    skills = await list_agent_skills(session=session, agent_id=agent_id)
    return [AgentSkillResponse.model_validate(s) for s in skills]


@router.post(
    "/tasks/sync",
    response_model=TaskSyncResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_sync_task_mapping(
    request: TaskSyncCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskSyncResponse:
    """Link an internal task to an external tracker issue/ticket."""
    try:
        mapping = await sync_task_mapping(
            session=session,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TaskSyncResponse.model_validate(mapping)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.post(
    "/tasks/ingest",
    response_model=TaskSyncResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_ingest_external_task(
    request: ExternalTaskIngestRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
) -> TaskSyncResponse:
    """Ingest an external issue as a governed task in Mercury Hive."""
    try:
        _task, sync_mapping = await ingest_external_task(
            session=session,
            data=request,
            actor_id=owner.owner_id,
            actor_role="OWNER",
        )
        return TaskSyncResponse.model_validate(sync_mapping)
    except TribeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get(
    "/tasks/sync",
    response_model=list[TaskSyncResponse],
    dependencies=[Depends(verify_shutdown_state(mutation=False))],
)
async def api_list_task_sync(
    session: Annotated[AsyncSession, Depends(get_db)],
    owner: Annotated[AuthenticatedOwner, Depends(get_current_owner)],
    task_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[TaskSyncResponse]:
    """List task synchronization mappings."""
    mappings = await list_task_sync_mappings(session=session, task_id=task_id)
    return [TaskSyncResponse.model_validate(m) for m in mappings]


@router.post(
    "/webhook",
    response_model=WebhookResponse,
    dependencies=[Depends(verify_shutdown_state(mutation=True))],
)
async def api_tribe_webhook(
    request: Request,
    settings: Annotated[RuntimeSettings, Depends(get_settings)],
    session: Annotated[AsyncSession | None, Depends(get_optional_db)] = None,
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
    x_signature_256: Annotated[str | None, Header(alias="X-Signature-256")] = None,
    x_webhook_timestamp: Annotated[str | None, Header(alias="X-Webhook-Timestamp")] = None,
    x_webhook_nonce: Annotated[str | None, Header(alias="X-Webhook-Nonce")] = None,
    idempotency_key_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> JSONResponse:
    """Inbound webhook endpoint with HMAC verification, replay protection, and idempotency."""
    global _webhook_execution_count

    raw_body = await request.body()

    # 1. HMAC-SHA256 Signature Verification (401 Unauthorized if missing or invalid)
    signature = x_hub_signature_256 or x_signature_256
    if not signature:
        raise HTTPException(status_code=401, detail="Missing HMAC signature header")

    secret = settings.tribe_webhook_secret.get_secret_value()
    if not verify_webhook_signature(raw_body, signature, secret):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # 2. Extract Idempotency Key (from headers or payload)
    idempotency_key = idempotency_key_header or x_idempotency_key
    payload_data: dict[str, Any] = {}
    if raw_body:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict):
                payload_data = parsed
        except Exception:
            payload_data = {}

    if not idempotency_key:
        raw_key = payload_data.get("idempotency_key") or payload_data.get("id")
        if raw_key:
            idempotency_key = str(raw_key)

    # 3. Check Idempotency Store: if COMPLETED, return cached response immediately
    if idempotency_key:
        cached = idempotency_tracker.get_cached_response(idempotency_key)
        if cached is not None:
            status_code, cached_body = cached
            return JSONResponse(status_code=status_code, content=cached_body)

    # 4. Nonce & Timestamp Freshness Verification (400 Bad Request if expired or replayed)
    is_valid, reason = verify_timestamp_and_nonce(
        timestamp_str=x_webhook_timestamp,
        nonce=x_webhook_nonce,
        tolerance_seconds=300,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Replay attack prevented: {reason}")

    # 5. Lock Idempotency Key (transition to PROCESSING)
    if idempotency_key:
        acquired = idempotency_tracker.start_processing(idempotency_key)
        if not acquired:
            cached = idempotency_tracker.get_cached_response(idempotency_key)
            if cached is not None:
                status_code, cached_body = cached
                return JSONResponse(status_code=status_code, content=cached_body)
            raise HTTPException(
                status_code=409,
                detail="Concurrent request with identical idempotency key is in progress",
            )

    # 6. Execute Genuine Business Logic
    try:
        _webhook_execution_count += 1
        task_id = None
        event_name = payload_data.get("event") or payload_data.get("action") or "webhook.received"
        result_details: dict[str, Any] = dict(payload_data)

        if (
            session is not None
            and "external_system" in payload_data
            and "department_id" in payload_data
            and "title" in payload_data
        ):
            try:
                req_data = ExternalTaskIngestRequest(
                    external_system=str(payload_data["external_system"]),
                    external_task_id=str(payload_data.get("external_task_id", uuid.uuid4())),
                    title=str(payload_data["title"]),
                    description=str(
                        payload_data.get("description", "Ingested from external webhook")
                    ),
                    department_id=uuid.UUID(str(payload_data["department_id"])),
                    priority=str(payload_data.get("priority", "MEDIUM")),
                )
                system_actor_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
                task, sync_mapping = await ingest_external_task(
                    session=session,
                    data=req_data,
                    actor_id=system_actor_id,
                    actor_role="EXTERNAL_WEBHOOK",
                )
                task_id = str(task.id)
                result_details["task_id"] = task_id
                result_details["sync_mapping_id"] = str(sync_mapping.id)
            except TribeError as te:
                result_details["warning"] = te.message

        response_content = {
            "status": "processed",
            "message": "Webhook processed successfully",
            "idempotency_key": idempotency_key,
            "event": event_name,
            "task_id": task_id,
            "cached": False,
            "data": result_details,
        }

        # 7. Complete Idempotency Store
        if idempotency_key:
            idempotency_tracker.complete_processing(
                key=idempotency_key,
                status_code=200,
                response_data=response_content,
            )

        return JSONResponse(status_code=200, content=response_content)

    except Exception as exc:
        if idempotency_key:
            idempotency_tracker.fail_processing(idempotency_key)
        if isinstance(exc, HTTPException):
            raise
        logger.error("webhook_processing_error", error=str(exc))
        raise HTTPException(
            status_code=500, detail="Internal webhook processing error"
        ) from exc
