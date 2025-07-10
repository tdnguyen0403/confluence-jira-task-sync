import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import json
import os

from main import app
from src.dependencies import container, get_api_key
from src.config import config
from src.exceptions import (
    InvalidInputError,
    SyncError,
    UndoError,
)
from src.models.data_models import AutomationResult, ConfluenceTask
from fastapi import HTTPException, status, Depends  # Ensure Depends is imported
from fastapi.security import APIKeyHeader  # Ensure APIKeyHeader is imported


@pytest.fixture(autouse=True)
def setup_config_for_tests(monkeypatch):
    """Sets up minimal config values for tests and ensures test-specific paths."""
    monkeypatch.setattr(config, "API_SECRET_KEY", "test_api_key")

    # Mock the timestamp generation to be consistent for testing file paths
    fixed_timestamp = "20240101_120000"
    monkeypatch.setattr(
        config,
        "generate_timestamped_filename",
        lambda prefix,
        suffix,
        user=None: f"{prefix}_{user or 'default'}_{fixed_timestamp}{suffix}",
    )

    # Mock the get_input_path and get_output_path methods
    def mock_get_input_path(endpoint_name, filename):
        # Create a dummy test directory for inputs
        test_input_dir = os.path.join("test_data", "inputs")
        os.makedirs(test_input_dir, exist_ok=True)
        return os.path.join(test_input_dir, filename)

    def mock_get_output_path(endpoint_name, filename):
        # Create a dummy test directory for outputs
        test_output_dir = os.path.join("test_data", "outputs")
        os.makedirs(test_output_dir, exist_ok=True)
        return os.path.join(test_output_dir, filename)

    monkeypatch.setattr(config, "get_input_path", mock_get_input_path)
    monkeypatch.setattr(config, "get_output_path", mock_get_output_path)

    # Clean up test_data directory after each test
    yield
    import shutil

    if os.path.exists("test_data"):
        shutil.rmtree("test_data")


@pytest.fixture
def mock_sync_orchestrator():
    mock = MagicMock()
    # Populate mock.results for successful sync with all required fields for ConfluenceTask
    mock.results = [
        AutomationResult(
            task_data=ConfluenceTask(
                confluence_task_id="1",
                confluence_page_id="123",
                confluence_page_title="Test Page Title",
                confluence_page_url="http://example.com/test_page",
                task_summary="Test Task",
                status="incomplete",  # ConfluenceTask status
                assignee_name="test_assignee",
                due_date="2025-12-31",
                original_page_version=1,
                original_page_version_by="test_user",
                original_page_version_when="2024-01-01T10:00:00.000Z",
            ),
            status="Success",  # This is the AutomationResult status
            new_jira_key="TEST-1",
            linked_work_package="WP-001",
            request_user="test_user",
        )
    ]
    mock.run.return_value = (
        None  # No explicit return value needed, just modify .results
    )
    return mock


@pytest.fixture
def mock_undo_orchestrator():
    mock = MagicMock()
    mock.run.return_value = None
    return mock


@pytest.fixture
def mock_confluence_issue_updater_service():
    mock = MagicMock()
    mock.update_confluence_hierarchy_with_new_jira_project.return_value = [
        {
            "page_id": "page123",
            "page_title": "Test Page",
            "new_jira_keys": ["NEWPROJ-1"],
            "root_project_linked": "OLDPROJ-1",
        }
    ]
    return mock


@pytest.fixture
def client(
    mock_sync_orchestrator,
    mock_undo_orchestrator,
    mock_confluence_issue_updater_service,
):
    """Configures the TestClient with mocked dependencies."""
    app.dependency_overrides[container.sync_orchestrator] = (
        lambda: mock_sync_orchestrator
    )
    app.dependency_overrides[container.undo_orchestrator] = (
        lambda: mock_undo_orchestrator
    )
    app.dependency_overrides[container.confluence_issue_updater_service] = (
        lambda: mock_confluence_issue_updater_service
    )
    # Global override for get_api_key. Specific tests can override this further.
    app.dependency_overrides[get_api_key] = lambda: "test_api_key"
    yield TestClient(app)
    app.dependency_overrides = {}  # Clean up overrides


def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]


def test_sync_confluence_tasks_success(client, mock_sync_orchestrator):
    sync_request_payload = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/sync_task", json=sync_request_payload, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
    # Changed assertion key to "status" as per AutomationResult.to_dict() flattening
    assert (
        response.json()[0]["status"] == "incomplete"
    )  # Asserting original task status
    assert (
        response.json()[0]["Status"] == "Success"
    )  # Asserting automation result status
    mock_sync_orchestrator.run.assert_called_once_with(sync_request_payload)

    # Verify input and output files are created in the mocked paths
    fixed_timestamp = "20240101_120000"
    input_file = os.path.join(
        "test_data", "inputs", f"sync_task_request_test_user_{fixed_timestamp}.json"
    )
    output_file = os.path.join(
        "test_data", "outputs", f"sync_task_result_test_user_{fixed_timestamp}.json"
    )
    assert os.path.exists(input_file)
    assert os.path.exists(output_file)

    with open(output_file, "r") as f:
        output_data = json.load(f)
        assert len(output_data) == 1
        assert (
            output_data[0]["status"] == "incomplete"
        )  # Asserting original task status
        assert (
            output_data[0]["Status"] == "Success"
        )  # Asserting automation result status


def test_sync_confluence_tasks_no_tasks_processed(client, mock_sync_orchestrator):
    mock_sync_orchestrator.results = []  # No tasks processed
    sync_request_payload = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/sync_task", json=sync_request_payload, headers=headers)

    assert response.status_code == 200
    assert response.json() == []
    mock_sync_orchestrator.run.assert_called_once_with(sync_request_payload)


def test_sync_confluence_tasks_invalid_input_error(client, mock_sync_orchestrator):
    mock_sync_orchestrator.run.side_effect = InvalidInputError("Missing URLs")
    sync_request_payload = {
        "confluence_page_urls": [],
        "request_user": "test_user",
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/sync_task", json=sync_request_payload, headers=headers)

    assert response.status_code == 400
    assert "Invalid Request: Missing URLs" in response.json()["detail"]


def test_sync_confluence_tasks_sync_error(client, mock_sync_orchestrator):
    mock_sync_orchestrator.run.side_effect = SyncError("Jira API failed")
    sync_request_payload = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/sync_task", json=sync_request_payload, headers=headers)

    assert response.status_code == 500
    assert (
        "Synchronization failed due to an internal error: Jira API failed"
        in response.json()["detail"]
    )


def test_undo_sync_run_success(client, mock_undo_orchestrator):
    undo_request_payload = [
        {
            # Required fields as per UndoRequestItem
            "Status": "Success",
            "confluence_page_id": "12345",
            "original_page_version": 1,
            # Aliased fields from AutomationResult.to_dict()
            "New Jira Task Key": "JIRA-1",
            "Linked Work Package": "WP-1",
            "Request User": "user1",
            # Other optional fields that might be present in AutomationResult.to_dict()
            "confluence_task_id": "task1",
            "confluence_page_title": "Page Title",
            "confluence_page_url": "http://example.com/page",
            "task_summary": "Task 1",
            "status": "incomplete",  # ConfluenceTask status
            "assignee_name": "test_assignee",
            "due_date": "2025-12-31",
            "original_page_version_by": "test_user",
            "original_page_version_when": "2024-01-01T00:00:00Z",
            "context": "some context",
        }
    ]
    headers = {"X-API-Key": "test_api_key"}
    response = client.post(
        "/undo_sync_task", json=undo_request_payload, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Undo operation completed successfully."
    mock_undo_orchestrator.run.assert_called_once()
    # Check if a file was created in input_dir for undo request
    fixed_timestamp = "20240101_120000"
    input_file = os.path.join(
        "test_data", "inputs", f"undo_sync_task_request_default_{fixed_timestamp}.json"
    )
    assert os.path.exists(input_file)


def test_undo_sync_run_invalid_input_error(client, mock_undo_orchestrator):
    mock_undo_orchestrator.run.side_effect = InvalidInputError("No results provided")
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/undo_sync_task", json=[], headers=headers)

    assert response.status_code == 400
    assert "Invalid Request: No results provided" in response.json()["detail"]


def test_undo_sync_run_undo_error(client, mock_undo_orchestrator):
    mock_undo_orchestrator.run.side_effect = UndoError("Confluence rollback failed")
    undo_request_payload = [
        {
            # Required fields as per UndoRequestItem
            "Status": "Success",
            "confluence_page_id": "12345",
            "original_page_version": 1,
            # Aliased fields from AutomationResult.to_dict()
            "New Jira Task Key": "JIRA-1",
            "Linked Work Package": "WP-1",
            "Request User": "user1",
            # Other optional fields that might be present in AutomationResult.to_dict()
            "confluence_task_id": "task1",
            "confluence_page_title": "Page Title",
            "confluence_page_url": "http://example.com/page",
            "task_summary": "Task 1",
            "status": "incomplete",  # ConfluenceTask status
            "assignee_name": "test_assignee",
            "due_date": "2025-12-31",
            "original_page_version_by": "test_user",
            "original_page_version_when": "2024-01-01T00:00:00Z",
            "context": "some context",
        }
    ]
    headers = {"X-API-Key": "test_api_key"}
    response = client.post(
        "/undo_sync_task", json=undo_request_payload, headers=headers
    )

    assert response.status_code == 500
    assert (
        "Undo operation failed due to an internal error: Confluence rollback failed"
        in response.json()["detail"]
    )


def test_update_confluence_project_success(
    client, mock_confluence_issue_updater_service
):
    update_request_payload = {
        "root_confluence_page_url": "http://example.com/root_page",
        "root_project_issue_key": "OLDPROJ-1",
        "request_user": "test_user_project_sync",
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post(
        "/sync_project", json=update_request_payload, headers=headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["page_id"] == "page123"
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.assert_called_once_with(
        root_confluence_page_url=update_request_payload["root_confluence_page_url"],
        root_project_issue_key=update_request_payload["root_project_issue_key"],
        project_issue_type_id=None,
        phase_issue_type_id=None,
    )

    # Verify input and output files are created
    fixed_timestamp = "20240101_120000"
    input_file = os.path.join(
        "test_data",
        "inputs",
        f"sync_project_request_test_user_project_sync_{fixed_timestamp}.json",
    )
    output_file = os.path.join(
        "test_data",
        "outputs",
        f"sync_project_result_test_user_project_sync_{fixed_timestamp}.json",
    )
    assert os.path.exists(input_file)
    assert os.path.exists(output_file)


def test_update_confluence_project_no_pages_modified(
    client, mock_confluence_issue_updater_service
):
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.return_value = []
    update_request_payload = {
        "root_confluence_page_url": "http://example.com/root_page",
        "root_project_issue_key": "OLDPROJ-1",
        "request_user": "test_user_project_sync",
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post(
        "/sync_project", json=update_request_payload, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == []


def test_api_key_unauthorized(client):
    # Temporarily override get_api_key for this specific test
    # This mock will raise an HTTPException if the API key is not valid, as per original get_api_key logic
    def mock_get_api_key_for_unauthorized(
        api_key: str = Depends(APIKeyHeader(name="X-API-Key", auto_error=True)),
    ):  # Restored Depends and APIKeyHeader
        if config.API_SECRET_KEY is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server API key not configured.",
            )
        if api_key == config.API_SECRET_KEY:
            return api_key
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    # Manually set and clear the dependency override
    original_get_api_key = app.dependency_overrides.get(get_api_key)
    app.dependency_overrides[get_api_key] = mock_get_api_key_for_unauthorized
    try:
        sync_request_payload = {
            "confluence_page_urls": ["http://example.com/page1"],
            "request_user": "test_user",
        }
        headers = {"X-API-Key": "wrong_key"}
        response = client.post("/sync_task", json=sync_request_payload, headers=headers)
        # Debugging: print the response JSON for 422 errors
        if response.status_code == 422:
            print(f"422 Response Detail: {response.json()}")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API Key"
    finally:
        # Restore the original dependency after the test
        if original_get_api_key is None:
            del app.dependency_overrides[get_api_key]
        else:
            app.dependency_overrides[get_api_key] = original_get_api_key
