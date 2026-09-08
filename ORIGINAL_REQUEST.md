# Original User Request

## 2026-09-08T12:55:49Z

Mercury Hive production hardening: implement production authentication safeguards, real model-provider adapter validation, external webhook security, container vulnerability scanning, and exhaustive emergency shutdown verification.

Working directory: d:\mercury hive
Integrity mode: development

## Requirements

### R1. Production Authentication & Abuse Prevention
Implement bounded rate limiting on authentication routes (`/auth/login`, `/auth/refresh`) using sliding-window tracking, add Time-based One-Time Password (TOTP) MFA support for the System Owner, and provide an active session management UI endpoint enabling single-session or all-session revocation.

### R2. Real Model Provider Adapter & Defensive Guardrails
Implement and test a live-capable Model Provider adapter (e.g., Anthropic Claude / OpenAI API client) with:
- Strict API key isolation (keys loaded from environment/secrets manager, never logged or stored in DB)
- Bounded network timeouts (connect: 5s, read: 30s) and exponential backoff retry logic
- Schema validation with fail-closed rejection on malformed JSON
- Defensive sanitization against prompt injection and tool-result injection
- Cost accounting recording input/output token usage and USD expenditure per cycle

### R3. External Integration Webhook Security & Idempotency
Harden the Tribe/external integration adapter (`services/tribe/`) with:
- HMAC-SHA256 signature verification for incoming webhooks
- Replay prevention using cryptographic nonces and timestamp freshness windows
- Idempotency key tracking to guarantee at-most-once processing
- Exponential backoff retry with jitter for external synchronization calls

### R4. Exhaustive Emergency Shutdown Coverage Audit
Verify and enforce that both shutdown states (`DEGRADED` and `EMERGENCY_SHUTDOWN`) are checked at every mutation boundary:
- Agent creation, suspension, and termination
- Task creation, delegation, and status transition
- Tool execution through the Sandboxed Gateway
- Memory writes and state rollbacks
- Cross-department bridge approvals and external sync
- Guarantee: `DEGRADED` permits safe read-only queries while blocking high-risk mutations; `EMERGENCY_SHUTDOWN` halts all non-owner operations immediately.

### R5. Container Image & Supply Chain Security
Generate a Software Bill of Materials (SBOM) in CycloneDX format, run Trivy vulnerability scanning on the Docker image and filesystem, and execute automated git history scanning to guarantee zero secret leakage.

---

## Acceptance Criteria

### Authentication & Rate Limiting
- [ ] Brute-force requests to `/auth/login` (> 5 failed attempts in 1 minute) return `HTTP 429 Too Many Requests`
- [ ] TOTP MFA challenge is verified for Owner login when MFA is enabled
- [ ] Revoking a session via the session management endpoint immediately invalidates the associated refresh token and rejects further refresh attempts

### Model Provider Guardrails
- [ ] Network timeout and 5xx errors from the LLM provider trigger bounded retries and degrade gracefully to `AgentExecutionResult(success=False)`
- [ ] Prompt injection payloads in task descriptions or tool outputs cannot bypass the constitutional authority hierarchy
- [ ] Token and USD cost accounting records exact values in audit events

### External Webhooks & Idempotency
- [ ] Incoming webhooks with invalid or missing HMAC signatures are rejected with `HTTP 401 Unauthorized`
- [ ] Replayed webhook payloads (duplicate idempotency key or expired timestamp) return cached response without re-executing logic

### Shutdown Coverage
- [ ] All 11 route modules enforce shutdown state checks prior to mutation
- [ ] Dedicated automated test suite verifies both `DEGRADED` and `EMERGENCY_SHUTDOWN` states against all state-altering endpoints

### Container & Dependency Scans
- [ ] CycloneDX SBOM generated and validated
- [ ] Zero critical or high severity vulnerabilities in the container base image
- [ ] Zero secrets found in Git history
