# Project: Mercury Hive Production Hardening

## Architecture
Mercury Hive is an autonomous AI agent collective and governance platform built with FastAPI, SQLAlchemy (PostgreSQL), Pydantic v2, and Argon2id/HS256 authentication.

### Core Subsystems:
- **Identity & Auth (`services/identity/`)**: Singleton Owner administration, Argon2id password hashing, sliding-window rate limiting, RFC 6238 TOTP MFA, active session tracking, and refresh token rotation with cryptographic replay protection.
- **Agent Runtime & Model Provider (`services/agent_runtime/`)**: Autonomous cycle execution loop, live LLM provider client, bounded connect/read timeouts, exponential backoff retries, fail-closed schema validation, input sanitization boundaries, and token/USD cost accounting.
- **Tribe & External Integrations (`services/tribe/`)**: Inbound webhook ingestion, HMAC-SHA256 signature verification, nonce and timestamp freshness replay prevention, idempotency key tracking with cached responses, and outbound backoff with jitter.
- **Governance & Emergency Shutdown (`services/governance/`, `apps/api/dependencies.py`)**: Three-state runtime mode (`NORMAL`, `DEGRADED`, `EMERGENCY_SHUTDOWN`). Enforced across all 11 functional route modules at every mutation boundary.
- **Supply Chain & Container Security (`Dockerfile`, `scripts/security_check.py`)**: CycloneDX SBOM, Trivy vulnerability-scanned base image (zero high/critical), and automated git history secret scanning.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Sliding-Window Rate Limiting | Rate limit /auth/login (5 failed/min -> 429) and /auth/refresh | M1 | ORIGINAL_REQUEST §R1 |
| 2 | TOTP MFA for Owner | RFC 6238 TOTP verification on owner login when enabled | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Active Session Management Endpoints | GET /auth/sessions, DELETE /auth/sessions/{id}, DELETE /auth/sessions | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Immediate Refresh Invalidation | Revoking session immediately invalidates refresh tokens | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Live Model Provider Adapter | Live-capable LLM adapter (Claude / OpenAI) subclassing BaseModelProvider | M2 | ORIGINAL_REQUEST §R2 |
| 6 | API Key Isolation & Redaction | SecretStr config, zero DB storage, expanded audit redaction | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Bounded Network Timeouts & Retries | Connect 5s, read 30s, exponential backoff with graceful degradation | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Fail-Closed Schema Validation | Robust parsing, rejection of malformed JSON outputs | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Prompt & Tool Injection Defenses | Input sanitization, XML boundary delimiters, control plane enforcement | M2 | ORIGINAL_REQUEST §R2 |
| 10 | Token & USD Cost Accounting | Exact input/output tokens and USD expenditure recorded in audit events | M2 | ORIGINAL_REQUEST §R2 |
| 11 | Tribe Webhook HMAC Verification | HMAC-SHA256 verification (X-Hub-Signature-256) on incoming webhooks | M3 | ORIGINAL_REQUEST §R3 |
| 12 | Nonce & Timestamp Replay Defense | Validate timestamp freshness (<= 300s) and nonce uniqueness | M3 | ORIGINAL_REQUEST §R3 |
| 13 | Idempotency Key & Cached Responses | At-most-once processing, return cached response for duplicate keys | M3 | ORIGINAL_REQUEST §R3 |
| 14 | Outbound Exponential Backoff & Jitter | Resilient external sync calls with jittered retries | M3 | ORIGINAL_REQUEST §R3 |
| 15 | Centralized Shutdown Dependency | verify_shutdown_state enforcing DEGRADED & EMERGENCY_SHUTDOWN | M4 | ORIGINAL_REQUEST §R4 |
| 16 | Route Module Shutdown Coverage | All 11 route modules enforce shutdown state checks prior to mutation | M4 | ORIGINAL_REQUEST §R4 |
| 17 | Dedicated Shutdown Test Suite | Comprehensive automated tests verifying DEGRADED and EMERGENCY_SHUTDOWN | M4 | ORIGINAL_REQUEST §R4 |
| 18 | CycloneDX SBOM Generation | Validated CycloneDX SBOM artifact generation | M5 | ORIGINAL_REQUEST §R5 |
| 19 | Base Image Vulnerability Remediation | Zero high or critical vulnerabilities in container base image via Trivy | M5 | ORIGINAL_REQUEST §R5 |
| 20 | Git History Secret Scanning | Automated git history scan ensuring zero secret leakage | M5 | ORIGINAL_REQUEST §R5 |
| 21 | Comprehensive Acceptance Verification | Full automated test execution verifying all acceptance criteria | M6 | ORIGINAL_REQUEST Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Production Auth & Abuse Prevention | Rate limiting, TOTP MFA, session management & revocation | none | DONE |
| M2 | Model Provider Adapter & Guardrails | Live adapter, key isolation, timeouts, retries, injection defense, cost accounting | none | DONE |
| M3 | External Webhook Security & Idempotency | HMAC-SHA256 verification, nonce/timestamp replay checks, idempotency cache, backoff | none | DONE |
| M4 | Emergency Shutdown Coverage Audit | verify_shutdown_state across all 11 routes, mutation blocking in DEGRADED/SHUTDOWN, test suite | none | DONE |
| M5 | Container & Supply Chain Security | CycloneDX SBOM, Dockerfile base image patching (0 high/critical), git secret scanning | none | PLANNED |
| M6 | Final Verification & Victory Report | Comprehensive test run, acceptance criteria checklist verification, report to parent | M1, M2, M3, M4, M5 | PLANNED |

## Interface Contracts
### Auth Router ↔ Identity Service (`services/identity/`)
- `login(session, request: LoginRequest, client_ip: str, settings: RuntimeSettings) -> TokenResponse`
  - Validates password (Argon2id)
  - If MFA enabled: verifies `request.totp_code` via `verify_totp_code()`; raises `AuthenticationError("mfa_failed")` if invalid
  - Rate limiter: checked before login; recorded on failure; reset on success
- `refresh(session, request: RefreshRequest, client_ip: str, settings: RuntimeSettings) -> TokenResponse`
  - Rejects if session revoked (`revoked_at is not None`)
- `list_active_sessions(session, owner_id, current_session_id) -> list[SessionInfo]`
- `revoke_session(session, owner_id, session_id) -> bool`
- `revoke_all_sessions(session, owner_id, include_current: bool) -> int`

### Agent Runtime ↔ Model Provider (`services/agent_runtime/`)
- `BaseModelProvider.generate_decision(system_prompt: str, execution_context: AgentExecutionContext) -> tuple[AgentDecision, UsageMetrics]`
- `HttpModelProvider(BaseModelProvider)`: supports live HTTP client or mock transport, timeout (connect=5s, read=30s), exponential retries on 5xx/429.
- `sanitize_untrusted_input(text: str) -> str`: wraps untrusted context in boundary tags and neutralizes control markers.

### Tribe Webhook ↔ Security (`services/tribe/`)
- `verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool`
- `verify_timestamp_and_nonce(timestamp: int, nonce: str) -> bool`
- `get_cached_idempotent_response(idempotency_key: str) -> WebhookResponse | None`
- `store_idempotent_response(idempotency_key: str, response: WebhookResponse)`

### Shutdown Dependency ↔ Route Modules (`apps/api/dependencies.py`)
- `verify_shutdown_state(mutation: bool = True, allow_in_degraded: bool = False)`:
  - In `EMERGENCY_SHUTDOWN`: blocks all non-recovery operations (returns 503 Service Unavailable).
  - In `DEGRADED`: permits safe read-only queries (GET) and approved low-risk actions; blocks all mutations (returns 503 Service Unavailable).

## Code Layout
- `apps/api/`: FastAPI application factory, routing definitions, dependencies, and settings.
- `services/identity/`: Authentication, password hashing, tokens, rate limiter, TOTP, and session management.
- `services/agent_runtime/`: Agent decision loop, model provider adapters, prompt templates, and execution runners.
- `services/tribe/`: External integration adapter, webhooks, HMAC verification, and task synchronization.
- `services/governance/`: Emergency shutdown triggers, system state management, and owner approvals.
- `services/permissions/`: Role-based and constitutional authorization engine.
- `domain/`: SQLAlchemy models, Pydantic schemas, and enums.
- `tests/unit/`: Fast unit tests (auth, tokens, runtime, shutdown, tribe, tools).
- `tests/integration/`: Component and API integration tests.
- `tests/security/`: Security-specific audits, privilege checks, and injection defense tests.
- `scripts/`: Tooling, security checks, SBOM generation, and database privilege scripts.
