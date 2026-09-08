"""Integration tests for Phase 6: Judging Council, Rubrics, and Deliberation APIs."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_judging_and_rubrics_api_lifecycle(client: AsyncClient, auth_tokens: dict):
    """End-to-end integration test of rubrics, submissions, and council consensus."""
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}

    # 1. Verify seeded rubrics
    rubrics_res = await client.get("/judging/rubrics", headers=headers)
    assert rubrics_res.status_code == 200
    rubrics = rubrics_res.json()
    assert len(rubrics) >= 2
    rubric = rubrics[0]
    rubric_id = rubric["id"]

    # 2. Fetch departments
    dept_res = await client.get("/departments", headers=headers)
    assert dept_res.status_code == 200
    depts = dept_res.json()
    eng_dept = next(d for d in depts if d["name"] == "Engineering")
    judging_dept = next(d for d in depts if d["name"] == "Judging")
    sec_dept = next(d for d in depts if d["name"] == "Security")

    # 3. Provision Author Agent (Engineering)
    author_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Senior Software Crafter",
            "role": "WORKER",
            "department_id": eng_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert author_res.status_code == 200
    author_id = author_res.json()["id"]

    # 4. Provision Task
    task_res = await client.post(
        "/tasks",
        headers=headers,
        json={
            "title": "Implement Quantum Encryption Protocol",
            "description": "Post-quantum cryptographic key exchange deliverable",
            "origin_department_id": eng_dept["id"],
            "assigned_department_id": eng_dept["id"],
            "assigned_agent_id": author_id,
        },
    )
    assert task_res.status_code == 200
    task_id = task_res.json()["id"]

    # 5. Submit Deliverable to Council
    sub_res = await client.post(
        f"/judging/submissions?author_agent_id={author_id}",
        headers=headers,
        json={
            "task_id": task_id,
            "title": "Quantum Key Exchange Deliverable v1.0",
            "deliverable_payload": {
                "repository": "github.com/mercury/quantum-crypto",
                "commit_hash": "e1f2a3b4c5",
                "test_pass_rate": 100.0,
            },
        },
    )
    assert sub_res.status_code == 200, sub_res.text
    submission = sub_res.json()
    submission_id = submission["id"]

    # 6. Provision two Judges (one from Judging department, one from Security department)
    judge1_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Lead Council Magistrate",
            "role": "JUDGE",
            "department_id": judging_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert judge1_res.status_code == 200
    judge1_id = judge1_res.json()["id"]

    judge2_res = await client.post(
        "/agents",
        headers=headers,
        json={
            "display_name": "Security Auditor Principal",
            "role": "JUDGE",
            "department_id": sec_dept["id"],
            "system_prompt_version": "1.0.0",
        },
    )
    assert judge2_res.status_code == 200
    judge2_id = judge2_res.json()["id"]

    # 7. Create Judging Council Session (2 required judges for consensus)
    session_create_res = await client.post(
        "/judging/sessions",
        headers=headers,
        json={
            "submission_id": submission_id,
            "rubric_id": rubric_id,
            "required_judges": 2,
        },
    )
    assert session_create_res.status_code == 200, session_create_res.text
    j_session = session_create_res.json()
    session_id = j_session["id"]
    assert j_session["status"] == "PENDING_REVIEW"

    # 8. Judge 1 submits scorecard
    card1_res = await client.post(
        f"/judging/sessions/{session_id}/score?judge_agent_id={judge1_id}",
        headers=headers,
        json={
            "scores": {"CORRECTNESS": 90.0, "TEST_COVERAGE": 95.0, "CODE_QUALITY": 85.0},
            "total_score": 90.0,
            "verdict": "PASSED",
            "feedback": "Outstanding cryptographic clarity and defensive design",
        },
    )
    assert card1_res.status_code == 200, card1_res.text
    assert card1_res.json()["verdict"] == "PASSED"

    # Check session state in deliberation
    s_mid = await client.get(f"/judging/sessions/{session_id}", headers=headers)
    assert s_mid.status_code == 200
    assert s_mid.json()["status"] == "IN_DELIBERATION"

    # 9. Judge 2 submits scorecard -> Reaching Consensus!
    card2_res = await client.post(
        f"/judging/sessions/{session_id}/score?judge_agent_id={judge2_id}",
        headers=headers,
        json={
            "scores": {"CORRECTNESS": 88.0, "TEST_COVERAGE": 92.0, "CODE_QUALITY": 84.0},
            "total_score": 88.0,
            "verdict": "PASSED",
            "feedback": "Verified threat model mitigations",
        },
    )
    assert card2_res.status_code == 200, card2_res.text

    # 10. Check session completed
    s_final = await client.get(f"/judging/sessions/{session_id}", headers=headers)
    assert s_final.status_code == 200
    final_session = s_final.json()
    assert final_session["status"] == "CONSENSUS_REACHED"
    assert final_session["final_verdict"] == "PASSED"
    assert final_session["aggregate_score"] == 89.0  # (90 + 88)/2
    assert final_session["closed_at"] is not None
