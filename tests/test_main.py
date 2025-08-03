# File: test/test_main.py

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
    ConfluencePageUpdateResult,
    JiraTaskCreationResult,
    SinglePageResult,
    SyncTaskResponse,
    UndoActionResult,
    UndoSyncTaskRequest,
    UndoSyncTaskResponse,
)


# --- Fixtures for common mocks ---
@pytest.fixture
def mock_sync_orchestrator():
    """Mocks the SyncTaskOrchestrator."""
    mock_orch = AsyncMock()

    async def run_sync_mock(*args, **kwargs):
        return SyncTaskResponse(
            request_id=kwargs.get("request_id", "mock-req-id"),
            overall_status="Success",
            overall_jira_task_creation_status="Success",
            overall_confluence_page_update_status="Success",
            jira_task_creation_results=[],
            confluence_page_update_results=[],
        )

    mock_orch.run.side_effect = run_sync_mock
    return mock_orch


@pytest.fixture
def mock_undo_orchestrator():
    """Mocks the UndoSyncTaskOrchestrator."""
    mock_orch = AsyncMock()

    async def run_undo_mock(*args, **kwargs):
        return UndoSyncTaskResponse(
            request_id=kwargs.get("request_id", "mock-req-id"),
            overall_status="Success",
            results=[
                UndoActionResult(
                    action_type="jira_transition",
                    target_id="JIRA-001",
                    success=True,
                    status_message="OK",  # FIX: Added missing required field
                )
            ],
        )

    mock_orch.run.side_effect = run_undo_mock
    return mock_orch


@pytest.fixture
def mock_confluence_issue_updater_service():
    """Mocks the ConfluenceIssueUpdaterService."""
    mock_service = AsyncMock()
    mock_service.update_confluence_hierarchy_with_new_jira_project.return_value = [
        SinglePageResult(
            page_id="123",
            page_title="sample title",
            new_jira_keys=["TEST-1"],
            project_linked="PROJ",
        )
    ]
    return mock_service


@pytest.fixture
def mock_jira_api():
    """Mocks the Jira API client."""
    return AsyncMock()


@pytest.fixture
def mock_confluence_api():
    """Mocks the Confluence API client."""
    return AsyncMock()


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

    with patch("httpx.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_http_helper.client

        app.dependency_overrides = {
            get_api_key: lambda: "valid_key",
            get_sync_task_orchestrator: lambda: mock_sync_orchestrator,
            get_undo_sync_task_orchestrator: lambda: mock_undo_orchestrator,
            get_confluence_issue_updater_service: (
                lambda: mock_confluence_issue_updater_service
            ),
            get_safe_jira_api: lambda: mock_jira_api,
            get_safe_confluence_api: lambda: mock_confluence_api,
            get_https_helper: lambda: mock_http_helper,
        }
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
    success_response = SyncTaskResponse(
        request_id="specific-req-id",
        overall_status="Success",
        overall_jira_task_creation_status="Success",
        overall_confluence_page_update_status="Success",
        jira_task_creation_results=[
            JiraTaskCreationResult(
                confluence_page_id="page123",
                task_summary="Sample Task",
                success=True,
                # FIX: Added missing required fields
                confluence_task_id="task-1",
                original_page_version=1,
                creation_status_text="Success",
            )
        ],
        confluence_page_update_results=[
            ConfluencePageUpdateResult(
                page_id="page123", page_title="Test Page", updated=True
            )
        ],
    )

    async def mock_run(*args, **kwargs):
        return success_response

    mock_sync_orchestrator.run.side_effect = mock_run

    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 200
    mock_sync_orchestrator.run.assert_awaited_once()
    response_data = response.json()
    assert response_data["overall_status"] == "Success"
    assert len(response_data["jira_task_creation_results"]) == 1


@pytest.mark.asyncio
async def test_unhandled_exception(mock_sync_orchestrator, client):
    mock_sync_orchestrator.run.side_effect = Exception("A critical unhandled error")
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {"request_user": "user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    assert response.json() == {
        "detail": "An unexpected internal server error occurred."
    }


@pytest.mark.asyncio
async def test_undo_sync_task_success(mock_undo_orchestrator, client):
    """Verify /undo_sync_task succeeds."""
    request_body = [
        UndoSyncTaskRequest(
            confluence_page_id="123",
            original_page_version=1,
            new_jira_task_key="JIRA-1",
            request_user="test_user",
        ).model_dump()
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 200
    mock_undo_orchestrator.run.assert_awaited_once()
    response_data = response.json()
    assert response_data["overall_status"] == "Success"
    assert len(response_data["results"]) == 1


@pytest.mark.asyncio
async def test_sync_project_success(
    mock_confluence_issue_updater_service, client
):
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


@pytest.mark.asyncio
async def test_health_check_returns_ok(client):
    """Verify the /health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": "Application is alive."}


@pytest.mark.asyncio
async def test_readiness_check_success(mock_jira_api, mock_confluence_api, client):
    """Verify /ready returns 200 OK when dependencies are healthy."""
    mock_jira_api.get_current_user.return_value = {}
    mock_confluence_api.get_all_spaces.return_value = {}
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["detail"] == "Application and dependencies are ready."


@pytest.mark.asyncio
async def test_readiness_check_jira_api_failure(mock_jira_api, client):
    """Verify /ready returns a 500 response when a dependency fails."""
    mock_jira_api.get_current_user.side_effect = httpx.RequestError(
        "Jira Down", request=httpx.Request("GET", "/")
    )
    response = client.get("/ready")
    assert response.status_code == 500


@pytest.mark.parametrize(
    "exception, expected_status, expected_message",
    [
        (InvalidInputError("Test Invalid Input"), 400, "Invalid input"),
        (SyncError("Test Sync Failure"), 500, "synchronization"),
        (MissingRequiredDataError("Test Missing Data"), 404, "Missing Data"),
    ],
)
@pytest.mark.asyncio
async def test_sync_task_custom_exceptions(
    exception, expected_status, expected_message, mock_sync_orchestrator, client
):
    """Verify custom exceptions are handled correctly for /sync_task."""
    mock_sync_orchestrator.run.side_effect = exception
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {"request_user": "user"},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == expected_status
    assert expected_message in response.json()["detail"]


@pytest.mark.parametrize(
    "exception, expected_status, expected_message",
    [
        (InvalidInputError("Invalid undo data"), 400, "Invalid input"),
        (UndoError("Test Undo Failure"), 500, "undo process"),
        (MissingRequiredDataError("Missing version"), 404, "Missing version"),
    ],
)
@pytest.mark.asyncio
async def test_undo_sync_task_custom_exceptions(
    exception, expected_status, expected_message, mock_undo_orchestrator, client
):
    """Verify custom exceptions are handled correctly for /undo_sync_task."""
    mock_undo_orchestrator.run.side_effect = exception
    request_body = [UndoSyncTaskRequest(confluence_page_id="123").model_dump()]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == expected_status
    assert expected_message in response.json()["detail"]
