import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "start_workflow" in data["endpoints"]


@patch("backend.services.github_service.GitHubService.check_repository_access")
def test_validate_repository_endpoint(mock_check):
    mock_check.return_value = {
        "success": True,
        "message": "Repository exists.",
        "data": {
            "owner": "pallets",
            "repo": "flask",
            "html_url": "https://github.com/pallets/flask",
            "is_private": False
        }
    }
    response = client.post("/validate-repository", json={"repo_url": "https://github.com/pallets/flask"})
    assert response.status_code == 200
    data = response.json()
    assert "checks" in data
    assert "url_validation" in data["checks"]
    assert data["checks"]["url_validation"]["status"] == "completed"
    assert data["checks"]["repo_existence"]["status"] == "completed"


@patch("backend.orchestrator.workflow.WorkflowOrchestrator.run")
def test_workflow_start_and_status(mock_run):
    req_payload = {
        "repo_url": "https://github.com/pallets/flask",
        "issue_url_or_number": "6188",
        "github_token": "dummy_test_token"
    }
    response = client.post("/api/workflow/start", json=req_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "workflow_id" in data

    wf_id = data["workflow_id"]
    status_res = client.get(f"/api/workflow/{wf_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["workflow_id"] == wf_id
    assert "stages" in status_data
    assert "validation" in status_data["stages"]
