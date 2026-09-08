"""Integration tests for Phase 7: Controlled Evolution, Sandboxes, and Shadow Deployments."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_evolution_engine_api_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of evolution candidate proposal, sandboxing,

    shadow deployment, promotion, and rollback.
    """
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Fetch departments and provision active proposer agent
    dept_res = await client.get("/departments", headers=headers)
    assert dept_res.status_code == 200
    depts = dept_res.json()
    eng_dept = next(d for d in depts if d["name"] == "Engineering")

    agent_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "AI Evolution Lead",
            "role": "WORKER",
            "department_id": eng_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert agent_res.status_code == 200
    proposer_id = agent_res.json()["id"]

    # 2. Propose an Evolution Candidate
    prop_res = await client.post(
        f"/evolution/candidates?proposer_agent_id={proposer_id}",
        headers=headers,
        json={
            "title": "Adaptive Query Optimization Prompt",
            "evolution_type": "SYSTEM_PROMPT",
            "target_identifier": "worker_query_optimizer",
            "proposed_change": {
                "prompt_template": "You are a database query analyzer with index hints.",
                "max_tokens": 2048,
            },
        },
    )
    assert prop_res.status_code == 200
    candidate = prop_res.json()
    candidate_id = candidate["id"]
    assert candidate["status"] == "PROPOSED"
    assert candidate["shadow_traffic_percentage"] == 0

    # 3. Retrieve Candidate by ID
    get_res = await client.get(f"/evolution/candidates/{candidate_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Adaptive Query Optimization Prompt"

    # 4. Attempt Shadow Deploy prior to passing benchmark — must be rejected
    early_shadow = await client.post(
        f"/evolution/candidates/{candidate_id}/shadow",
        headers=headers,
        json={"percentage": 10},
    )
    assert early_shadow.status_code == 400

    # 5. Run Sandbox Benchmark (Passing)
    bench_res = await client.post(
        f"/evolution/candidates/{candidate_id}/sandbox",
        headers=headers,
        json={
            "candidate_id": candidate_id,
            "test_suite_name": "query_perf_eval_v1",
            "baseline_score": 82.0,
            "candidate_score": 91.5,
            "metrics": {"p95_latency_ms": 110},
            "verdict": "PASSED",
        },
    )
    assert bench_res.status_code == 200
    sandbox_run = bench_res.json()
    assert sandbox_run["verdict"] == "PASSED"

    # 6. List Sandbox Runs
    runs_res = await client.get(
        f"/evolution/candidates/{candidate_id}/sandbox",
        headers=headers,
    )
    assert runs_res.status_code == 200
    assert len(runs_res.json()) >= 1

    # 7. Deploy Shadow Traffic (25%)
    shadow_res = await client.post(
        f"/evolution/candidates/{candidate_id}/shadow",
        headers=headers,
        json={"percentage": 25},
    )
    assert shadow_res.status_code == 200
    shadow_cand = shadow_res.json()
    assert shadow_cand["status"] == "SHADOW_DEPLOYED"
    assert shadow_cand["shadow_traffic_percentage"] == 25

    # 8. Promote to Production (Owner only)
    promote_res = await client.post(
        f"/evolution/candidates/{candidate_id}/promote",
        headers=headers,
        json={"notes": "Excellent performance observed under shadow traffic."},
    )
    assert promote_res.status_code == 200
    promoted_cand = promote_res.json()
    assert promoted_cand["status"] == "PROMOTED"
    assert promoted_cand["shadow_traffic_percentage"] == 100
    assert promoted_cand["approved_by"] is not None

    # 9. Emergency / Safety Rollback
    rollback_res = await client.post(
        f"/evolution/candidates/{candidate_id}/rollback",
        headers=headers,
        json={"reason": "Simulated regression during peak operational load."},
    )
    assert rollback_res.status_code == 200
    rolled_back_cand = rollback_res.json()
    assert rolled_back_cand["status"] == "ROLLED_BACK"
    assert rolled_back_cand["shadow_traffic_percentage"] == 0
    assert "Simulated regression" in rolled_back_cand["reversion_reason"]
