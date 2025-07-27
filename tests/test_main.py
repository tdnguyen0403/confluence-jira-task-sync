from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.dependencies import (
    get_api_key,
    get_confluence_issue_updater_service,
    get_https_helper,
    get_safe_confluence_api,
    get_safe_jira_api,
    get_sync_task_orchestrator,
    get_undo_sync_task_orchestrator,
)
from src.exceptions import (
    InvalidInputError,
    MissingRequiredDataError,
    SyncError,
    UndoError,
)
from src.main import app
from src.models.api_models import (
    SinglePageResult,
    SingleTaskResult,
)
from src.models.data_models import ConfluenceTask


# --- Fixtures for common mocks ---
@pytest.fixture
def mock_sync_orchestrator():
    """Mocks the SyncTaskOrchestrator."""
    mock_orch = AsyncMock()
    mock_orch.run.return_value = [
        SingleTaskResult(
            task_data=ConfluenceTask(
                confluence_page_id="p1",
                confluence_page_title="P1 Title",
                confluence_page_url="http://p1.url",
                confluence_task_id="t1",
                task_summary="Test Task 1",
                status="incomplete",
                assignee_name="test_user",
                original_page_version=1,
                original_page_version_by="test",
                original_page_version_when="2025-01-01T00:00:00Z",
            ),
            status_text="Success",
            new_jira_task_key="JIRA-001",
            linked_work_package="WP-001",
            request_user="test_user",
        )
    ]
    return mock_orch


@pytest.fixture
def mock_undo_orchestrator():
    """Mocks the UndoSyncTaskOrchestrator."""
    return AsyncMock()


@pytest.fixture
def mock_confluence_issue_updater_service():
    """Mocks the ConfluenceIssueUpdaterService."""
    mock_service = AsyncMock()
    mock_service.update_confluence_hierarchy_with_new_jira_project.return_value = [
        SinglePageResult(
            page_id="123",
            page_title="sample title",
            new_jira_keys=["JIRA-100", "JIRA-200"],
            project_linked="PROJ-123",
        )
    ]
    return mock_service


@pytest.fixture
def mock_jira_api():
    """Mocks the Jira API client."""
    mock_api = AsyncMock()
    mock_api.get_current_user.return_value = {"accountId": "test_jira_user"}
    return mock_api


@pytest.fixture
def mock_confluence_api():
    """Mocks the Confluence API client."""
    mock_api = AsyncMock()
    mock_api.get_all_spaces.return_value = [{"id": "s1", "name": "Space 1"}]
    return mock_api


@pytest.fixture(autouse=True)
def common_dependencies_override(
    mock_sync_orchestrator,
    mock_undo_orchestrator,
    mock_confluence_issue_updater_service,
    mock_jira_api,
    mock_confluence_api,
):
    """Overrides FastAPI dependencies for all tests."""
    mock_http_helper = AsyncMock()
    mock_http_helper.client = AsyncMock()
    mock_http_helper.client.aclose = AsyncMock(return_value=None)

    app.dependency_overrides = {
        get_api_key: lambda: "valid_key",
        get_sync_task_orchestrator: lambda: mock_sync_orchestrator,
        get_undo_sync_task_orchestrator: lambda: mock_undo_orchestrator,
        get_confluence_issue_updater_service: lambda: mock_confluence_issue_updater_service,
        get_safe_jira_api: lambda: mock_jira_api,
        get_safe_confluence_api: lambda: mock_confluence_api,
        get_https_helper: lambda: mock_http_helper,
    }
    # Patch setup_logging to prevent it from running during tests
    with patch("src.main.setup_logging", return_value=None):
        yield
    app.dependency_overrides = {}


@pytest.fixture(name="client")
def test_client_fixture():
    """Provides a FastAPI TestClient."""
    with TestClient(app) as test_client:
        yield test_client


# --- Test Cases ---


@pytest.mark.asyncio
async def test_sync_task_success_response(mock_sync_orchestrator, client):
    """Verify /sync_task succeeds and returns expected results."""
    request_body = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "test_user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 200
    response_data = response.json()
    assert "request_id" in response_data
    assert "results" in response_data
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["new_jira_task_key"] == "JIRA-001"
    mock_sync_orchestrator.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_unhandled_exception(mock_sync_orchestrator, client):
    """
    Verify the global exception handler catches unhandled errors and returns a 500 response.
    """
    # Arrange: Configure the mock to raise a generic, unhandled exception.
    mock_sync_orchestrator.run.side_effect = Exception("A critical unhandled error")
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {"request_user": "user", "days_to_due_date": 7},
    }

    # Act: Make the request that will trigger the exception.
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    # Assert: Verify that the unhandled_exception_handler caught the error
    # and returned the correct HTTP 500 response. The exception does not
    # bubble up to the test client itself.
    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected internal server error occurred."
    }


@pytest.mark.asyncio
async def test_undo_sync_task_success(mock_undo_orchestrator, client):
    """Verify /undo_sync_task succeeds."""
    request_body = [
        {
            "status_text": "Success",
            "request_user": "test",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-1",
            "confluence_page_id": "123",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 200
    response_data = response.json()
    assert "request_id" in response_data
    assert response_data["detail"] == "Undo operation completed successfully."
    mock_undo_orchestrator.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_project_success(mock_confluence_issue_updater_service, client):
    """Verify /sync_project succeeds."""
    request_body = {
        "project_page_url": "http://example.com/project_root",
        "project_key": "PROJ-123",
        "request_user": "test_user",
    }
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 200
    response_data = response.json()
    assert "request_id" in response_data
    assert "results" in response_data
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["page_id"] == "123"
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_returns_ok(client):
    """Verify the /health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "Application is alive."}


@pytest.mark.asyncio
async def test_readiness_check_success(mock_jira_api, mock_confluence_api, client):
    """Verify /ready returns 200 OK when dependencies are healthy."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["detail"] == "Application and dependencies are ready."
    mock_jira_api.get_current_user.assert_awaited_once()
    mock_confluence_api.get_all_spaces.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_check_jira_api_failure(mock_jira_api, client):
    """
    Verify /ready returns a 500 response when a dependency like the Jira API fails.
    """
    # Arrange: Configure the mock Jira API to raise an exception, simulating
    # a connection failure.
    mock_jira_api.get_current_user.side_effect = httpx.RequestError(
        "Jira Down", request=httpx.Request("GET", "/")
    )

    # Act: Make the request to the readiness endpoint.
    response = client.get("/ready")

    # Assert: The httpx.RequestError is caught by the generic exception handler,
    # which should return a 500 status, indicating the service is not "ready"
    # due to an internal error.
    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected internal server error occurred."
    }


# --- Parameterized Tests for Custom Exception Handlers ---


@pytest.mark.parametrize(
    "exception, expected_status, expected_message",
    [
        (
            InvalidInputError("Test Invalid Input"),
            400,
            "Invalid input: Test Invalid Input",
        ),
        (
            SyncError("Test Sync Failure"),
            500,
            "An error occurred during synchronization: Test Sync Failure",
        ),
        (MissingRequiredDataError("Test Missing Data"), 404, "Test Missing Data"),
    ],
)
@pytest.mark.asyncio
async def test_sync_task_custom_exceptions(
    exception, expected_status, expected_message, mock_sync_orchestrator, client
):
    """Verify that custom exceptions are handled correctly for the /sync_task endpoint."""
    mock_sync_orchestrator.run.side_effect = exception
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {"request_user": "user", "days_to_due_date": 7},
    }

    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == expected_status
    assert expected_message in response.json()["detail"]


@pytest.mark.parametrize(
    "exception, expected_status, expected_message",
    [
        (
            InvalidInputError("Invalid undo data"),
            400,
            "Invalid input: Invalid undo data",
        ),
        (
            UndoError("Test Undo Failure"),
            500,
            "An error occurred during the undo process: Test Undo Failure",
        ),
        (
            MissingRequiredDataError("Missing original version"),
            404,
            "Missing original version",
        ),
    ],
)
@pytest.mark.asyncio
async def test_undo_sync_task_custom_exceptions(
    exception, expected_status, expected_message, mock_undo_orchestrator, client
):
    """Verify that custom exceptions are handled correctly for the /undo_sync_task endpoint."""
    mock_undo_orchestrator.run.side_effect = exception
    request_body = [
        {
            "status_text": "Success",
            "request_user": "test",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-1",
            "confluence_page_id": "123",
        }
    ]

    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == expected_status
    assert expected_message in response.json()["detail"]
