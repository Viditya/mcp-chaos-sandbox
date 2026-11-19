"""
test_api_endpoints.py — Integration test suite for FastAPI + FastMCP endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer sandbox-test-token-12345"}


def test_health_check_endpoint() -> None:
    """Verifies /health returns healthy status and environment configuration."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["sandbox_mode"] == "docker-cloud-microvm"
    assert "environment" in data


def test_mcp_register_tool_auth_required() -> None:
    """Verifies that tool registration requires valid bearer token."""
    contract = {
        "tool_name": "db_query",
        "description": "Executes read-only SQL queries against the database.",
        "allowed_scopes": ["sandbox:read"],
    }
    # No auth header -> 401
    resp_no_auth = client.post("/api/v1/mcp/register-tool", json=contract)
    assert resp_no_auth.status_code in (401, 403)

    # Valid auth header -> 200
    resp_authed = client.post("/api/v1/mcp/register-tool", json=contract, headers=AUTH_HEADERS)
    assert resp_authed.status_code == 200
    assert resp_authed.json()["registered"] is True
    assert resp_authed.json()["tool_name"] == "db_query"


def test_aggregator_ground_truth_interception() -> None:
    """Verifies that the verifier catches aggregator value corruption and overrides it."""
    url = (
        "/api/v1/chaos/verify-aggregator"
        "?experiment_id=exp-integration-test"
        "&aggregator_reported_sum=600.00"
        "&fault_triggered_in_run=true"
    )
    worker_outputs = [120.50, 45.25, 84.25]  # sum is 250.00
    response = client.post(url, json=worker_outputs, headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["ground_truth_sum"] == 250.0
    assert data["aggregator_reported_sum"] == 600.0
    assert data["stage_validation_passed"] is False
    assert data["final_verified_value"] == 250.0
    assert "Aggregator Value Fault intercepted" in data["remediation_note"]


def test_chaos_execute_clean_run() -> None:
    """Verifies executing a tool task with clean baseline configuration."""
    payload = {
        "session_id": "test-session-1",
        "idempotency_key": "idem-99998888",
        "intent_query": "Diagnose network latency",
        "intent_confidence": 0.95,
        "chaos_config": {
            "experiment_id": "clean-exp",
            "fault_category": "none",
            "strategy": "single",
            "target_call_index": 1,
        },
    }
    response = client.post("/api/v1/chaos/execute", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-1"
    assert data["gatekeeper_action"] == "proceed"
    assert data["recovered"] is True


def test_frontend_root_static_serving() -> None:
    """Verifies that GET / serves the built React frontend application."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text
    assert "root" in response.text
