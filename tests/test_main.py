import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, mock_open
import re  # Import the regex module

from main import app
from src.dependencies import (
    get_api_key,
    get_https_helper,
    get_safe_jira_api,
    get_safe_confluence_api,
    get_confluence_issue_updater_service,
    get_sync_task_orchestrator,
    get_undo_sync_task_orchestrator,
)
from src.models.data_models import (
    AutomationResult,
    ConfluenceTask,
    SyncProjectPageDetail,
)
from src.exceptions import (
    InvalidInputError,
    SyncError,
    UndoError,
    MissingRequiredDataError,
)
import httpx

# Disable actual logging for tests
# logging.disable(logging.CRITICAL)


# --- Fixtures for common mocks ---
@pytest.fixture
def mock_sync_orchestrator():
    """Mocks the SyncTaskOrchestrator and its results attribute."""
    mock_orch = AsyncMock()
    mock_orch.run.return_value = [
        AutomationResult(
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
    mock_orch = AsyncMock()
    return mock_orch


@pytest.fixture
def mock_confluence_issue_updater_service():
    """Mocks the ConfluenceIssueUpdaterService."""
    mock_service = AsyncMock()
    # Default success scenario
    mock_service.update_confluence_hierarchy_with_new_jira_project.return_value = [
        SyncProjectPageDetail(
            page_id="123",
            page_title="sample title",
            new_jira_keys=["JIRA-100", "JIRA-200"],
            root_project_linked="PROJ-123",
        )
    ]
    return mock_service


@pytest.fixture
def mock_jira_api():
    """Mocks the Jira API client for readiness checks."""
    mock_api = AsyncMock()
    mock_api.get_current_user.return_value = {"accountId": "test_jira_user"}
    return mock_api


@pytest.fixture
def mock_confluence_api():
    """Mocks the Confluence API client for readiness checks."""
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
    """
    Overrides FastAPI dependencies for testing.
    This fixture ensures that the patched dependencies are used by the FastAPI app.
    """

    # Mock get_https_helper to return an AsyncMock with a client attribute
    # This addresses the 'Event loop is closed' issue by preventing the real httpx client initialization
    # and ensures a controlled mock for tests that might indirectly use http_helper.client.aclose()
    mock_http_helper = AsyncMock()
    mock_http_helper.client = AsyncMock()
    mock_http_helper.client.aclose = AsyncMock(
        return_value=None
    )  # Ensure aclose is awaitable

    app.dependency_overrides[get_api_key] = lambda: "valid_key"
    app.dependency_overrides[get_sync_task_orchestrator] = (
        lambda: mock_sync_orchestrator
    )
    app.dependency_overrides[get_undo_sync_task_orchestrator] = (
        lambda: mock_undo_orchestrator
    )
    app.dependency_overrides[get_confluence_issue_updater_service] = (
        lambda: mock_confluence_issue_updater_service
    )
    app.dependency_overrides[get_safe_jira_api] = lambda: mock_jira_api
    app.dependency_overrides[get_safe_confluence_api] = lambda: mock_confluence_api
    app.dependency_overrides[get_https_helper] = lambda: mock_http_helper

    # Patch file I/O operations and logging configuration
    with patch("src.utils.logging_config.setup_logging", return_value=None), patch(
        "src.utils.dir_helpers.generate_timestamped_filename",
        return_value="mock_file.json",
    ), patch(
        "src.utils.dir_helpers.get_input_path",
        return_value="/mock/input/mock_file.json",
    ), patch(
        "src.utils.dir_helpers.get_output_path",
        return_value="/mock/output/mock_file.json",
    ), patch("builtins.open", mock_open()), patch("json.dump", return_value=None):
        yield

    # Clean up dependency overrides after each test
    app.dependency_overrides = {}


# New fixture for the TestClient itself, ensuring it's created with fresh overrides
@pytest.fixture(name="client")
def test_client_fixture(common_dependencies_override):
    """
    Provides a FastAPI TestClient for each test function.
    The client is created after dependency overrides are set up by common_dependencies_override.
    """
    with TestClient(app) as test_client:
        yield test_client


# --- Test Cases for /sync_task ---
@pytest.mark.asyncio
async def test_sync_task_success_response(mock_sync_orchestrator, client):
    """
    Verify that /sync_task successfully synchronizes and returns expected results.
    """
    request_body = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "test_user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status_text"] == "Success"
    assert response.json()[0]["new_jira_task_key"] == "JIRA-001"
    mock_sync_orchestrator.run.assert_awaited_once()

    # Verify that json.dump was called for input and output
    # The common_endpoint_mocks fixture patches builtins.open and json.dump.
    # We can inspect the mock calls if needed for more detailed verification,
    # but for basic success, checking orchestrator.run call is sufficient.


@pytest.mark.asyncio
async def test_sync_task_no_actionable_tasks(mock_sync_orchestrator, client):
    """
    Verify that /sync_task returns an empty list if no actionable tasks are processed.
    """
    mock_sync_orchestrator.run.return_value = []  # Simulate no tasks processed
    request_body = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "test_user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 200
    assert response.json() == []
    mock_sync_orchestrator.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_task_invalid_input_error(mock_sync_orchestrator, client):
    """
    Verify /sync_task handles InvalidInputError from the orchestrator.
    """
    mock_sync_orchestrator.run.side_effect = InvalidInputError(
        "Test Invalid Input Message"
    )
    request_body = {
        "confluence_page_urls": [],
        "context": {"request_user": "user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 400
    # Use re.fullmatch to match the entire string with the dynamic request ID
    assert re.fullmatch(
        r"Invalid Request: Test Invalid Input Message for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_sync_task_missing_required_data_error(mock_sync_orchestrator, client):
    """
    Verify /sync_task handles MissingRequiredDataError from the orchestrator.
    """
    mock_sync_orchestrator.run.side_effect = MissingRequiredDataError(
        "Missing context user"
    )
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {},  # Missing request_user
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 400
    # Use re.fullmatch to match the entire string with the dynamic request ID
    assert re.fullmatch(
        r"Missing Data: Missing context user for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_sync_task_sync_error(mock_sync_orchestrator, client):
    """
    Verify /sync_task handles SyncError from the orchestrator.
    """
    mock_sync_orchestrator.run.side_effect = SyncError("Test Sync Failure Message")
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {"request_user": "user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    # Use re.fullmatch to match the entire string with the dynamic request ID
    assert re.fullmatch(
        r"Synchronization failed due to an internal error: Test Sync Failure Message for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_sync_task_unhandled_exception(mock_sync_orchestrator, client):
    """
    Verify /sync_task handles generic Exception from the orchestrator.
    """
    mock_sync_orchestrator.run.side_effect = Exception("Unhandled Error")
    request_body = {
        "confluence_page_urls": ["http://page.com"],
        "context": {"request_user": "user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    # Use re.fullmatch to match the entire string with the dynamic request ID
    assert re.fullmatch(
        r"An unexpected server error occurred: Unhandled Error for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


# --- Test Cases for /undo_sync_task ---
@pytest.mark.asyncio
async def test_undo_sync_task_success(mock_undo_orchestrator, client):
    """
    Verify that /undo_sync_task successfully processes an undo request.
    """
    request_body = [
        {
            "status_text": "Success",
            "confluence_page_id": "p1",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-001",
            "request_user": "test_user",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 200
    # Use re.fullmatch for the message
    assert re.fullmatch(
        r"Undo operation completed successfully for request id [0-9a-fA-F]{32}",
        response.json()["message"],
    )


@pytest.mark.asyncio
async def test_undo_sync_task_invalid_input_error(mock_undo_orchestrator, client):
    """
    Verify /undo_sync_task handles InvalidInputError from the orchestrator.
    """
    mock_undo_orchestrator.run.side_effect = InvalidInputError(
        "Test Undo Invalid Input"
    )
    # Provide minimal but valid Pydantic input to bypass Pydantic validation for the test,
    # allowing the orchestrator's side_effect to be triggered.
    request_body = [
        {
            "status_text": "Success",
            "confluence_page_id": "p1",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-001",
            "linked_work_package": "WP-001",
            "request_user": "test_user",
            "confluence_page_title": "P1 Title",
            "confluence_page_url": "http://p1.url",
            "confluence_task_id": "t1",
            "task_summary": "Test Task 1",
            "status": "incomplete",
            "original_page_version_by": "test",
            "original_page_version_when": "2025-01-01T00:00:00Z",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 400
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"Invalid Request: Test Undo Invalid Input for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_undo_sync_task_missing_required_data_error(
    mock_undo_orchestrator, client
):
    """
    Verify /undo_sync_task handles MissingRequiredDataError from the orchestrator.
    """
    mock_undo_orchestrator.run.side_effect = MissingRequiredDataError(
        "Missing data in undo item"
    )
    request_body = [
        {
            "status_text": "Success",
            "confluence_page_id": "p1",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-001",
            "linked_work_package": "WP-001",
            "request_user": "test_user",
            "confluence_page_title": "P1 Title",
            "confluence_page_url": "http://p1.url",
            "confluence_task_id": "t1",
            "task_summary": "Test Task 1",
            "status": "incomplete",
            "original_page_version_by": "test",
            "original_page_version_when": "2025-01-01T00:00:00Z",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 400
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"Malformed Results Data: Missing data in undo item for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_undo_sync_task_undo_error(mock_undo_orchestrator, client):
    """
    Verify /undo_sync_task handles UndoError from the orchestrator.
    """
    mock_undo_orchestrator.run.side_effect = UndoError("Test Undo Failure Message")
    request_body = [
        {
            "status_text": "Success",
            "confluence_page_id": "p1",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-001",
            "request_user": "test_user",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"Undo operation failed due to an internal error: Test Undo Failure Message for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_undo_sync_task_unhandled_exception(mock_undo_orchestrator, client):
    """
    Verify /undo_sync_task handles generic Exception from the orchestrator.
    """
    mock_undo_orchestrator.run.side_effect = Exception("Unhandled Undo Error")
    request_body = [
        {
            "status_text": "Success",
            "confluence_page_id": "p1",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-001",
            "request_user": "test_user",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"An unexpected server error occurred: Unhandled Undo Error for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


# --- Test Cases for /sync_project ---
@pytest.mark.asyncio
async def test_sync_project_success(mock_confluence_issue_updater_service, client):
    """
    Verify that /sync_project successfully updates Confluence pages.
    """
    request_body = {
        "root_confluence_page_url": "http://example.com/project_root",
        "root_project_issue_key": "PROJ-123",
        "project_issue_type_id": "10001",
        "phase_issue_type_id": "10002",
        "request_user": "test_user",
    }
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["page_id"] == "123"
    assert response.json()[0]["page_title"] == "sample title"
    assert response.json()[0]["new_jira_keys"] == ["JIRA-100", "JIRA-200"]
    assert response.json()[0]["root_project_linked"] == "PROJ-123"
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_project_no_pages_modified(
    mock_confluence_issue_updater_service, client
):
    """
    Verify that /sync_project returns an empty list if no pages are modified.
    """
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.return_value = []
    request_body = {
        "root_confluence_page_url": "http://example.com/project_root",
        "root_project_issue_key": "PROJ-123",
        "project_issue_type_id": "10001",
        "phase_issue_type_id": "10002",
        "request_user": "test_user",
    }
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 200
    assert response.json() == []
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_project_invalid_input_error(
    mock_confluence_issue_updater_service, client
):
    """
    Verify /sync_project handles InvalidInputError from the service.
    """
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.side_effect = InvalidInputError(
        "Invalid project key format"
    )
    request_body = {
        "root_confluence_page_url": "invalid_url",  # Invalid URL to trigger Pydantic error
        "root_project_issue_key": "PROJ-123",
        "project_issue_type_id": "10001",
        "phase_issue_type_id": "10002",
        "request_user": "test_user",
    }
    # Send request with a valid URL so the error comes from the service, not Pydantic
    request_body["root_confluence_page_url"] = "http://example.com/page"
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 400
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"Invalid Request: Invalid project key format for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_sync_project_sync_error(mock_confluence_issue_updater_service, client):
    """
    Verify /sync_project handles SyncError from the service.
    """
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.side_effect = SyncError(
        "Confluence API failure"
    )
    request_body = {
        "root_confluence_page_url": "http://example.com/project_root",
        "root_project_issue_key": "PROJ-123",
        "project_issue_type_id": "10001",
        "phase_issue_type_id": "10002",
        "request_user": "test_user",
    }
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"Confluence update failed due to an internal error: Confluence API failure for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


@pytest.mark.asyncio
async def test_sync_project_unhandled_exception(
    mock_confluence_issue_updater_service, client
):
    """
    Verify /sync_project handles generic Exception from the service.
    """
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.side_effect = Exception(
        "Unexpected service error"
    )
    request_body = {
        "root_confluence_page_url": "http://example.com/project_root",
        "root_project_issue_key": "PROJ-123",
        "project_issue_type_id": "10001",
        "phase_issue_type_id": "10002",
        "request_user": "test_user",
    }
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )
    assert response.status_code == 500
    # Use re.fullmatch for the detail message
    assert re.fullmatch(
        r"An unexpected server error occurred: Unexpected service error for request id [0-9a-fA-F]{32}",
        response.json()["detail"],
    )


# --- Test Cases for Health and Readiness ---
@pytest.mark.asyncio
async def test_health_check_returns_ok(client):
    """
    Verify that the /health endpoint always returns 200 OK.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Application is alive."}


@pytest.mark.asyncio
async def test_readiness_check_success(mock_jira_api, mock_confluence_api, client):
    """
    Verify that the /ready endpoint returns 200 OK when all dependencies are healthy.
    """
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["message"] == "Application and dependencies are ready."
    mock_jira_api.get_current_user.assert_awaited_once()
    mock_confluence_api.get_all_spaces.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_check_jira_api_failure(
    mock_jira_api, mock_confluence_api, client
):
    """
    Verify that /ready returns 503 when Jira API is unreachable.
    """
    mock_jira_api.get_current_user.side_effect = httpx.RequestError(
        "Jira Connection Refused", request=httpx.Request("GET", "http://jira.com")
    )
    response = client.get("/ready")
    assert response.status_code == 503
    # Use 'in' for these specific checks as they don't have the UUID appended
    assert "Jira Connection Refused" in response.json()["detail"]
    mock_jira_api.get_current_user.assert_awaited_once()
    # Confluence API should not be called if Jira API check fails first
    mock_confluence_api.get_all_spaces.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_check_confluence_api_failure(
    mock_jira_api, mock_confluence_api, client
):
    """
    Verify that /ready returns 503 when Confluence API is unreachable.
    """
    mock_confluence_api.get_all_spaces.side_effect = httpx.RequestError(
        "Confluence Timeout", request=httpx.Request("GET", "http://confluence.com")
    )
    response = client.get("/ready")
    assert response.status_code == 503
    # Use 'in' for these specific checks as they don't have the UUID appended
    assert "Confluence Timeout" in response.json()["detail"]
    mock_jira_api.get_current_user.assert_awaited_once()
    mock_confluence_api.get_all_spaces.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_root(client):
    """
    Verify that the root endpoint returns a welcome message.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Welcome to the Jira-Confluence Automation API. Visit /docs for API documentation."
    }


@pytest.mark.asyncio
async def test_undo_sync_task_invalid_request_body(client):
    """
    Verify that /undo_sync_task returns a 422 error for an invalid request body.
    """
    # Request body is a dictionary instead of a list of items
    request_body = {
        "status_text": "Success",
        "confluence_page_id": "p1",
        "original_page_version": 1,
        "new_jira_task_key": "JIRA-001",
        "request_user": "test_user",
    }
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_undo_sync_task_empty_list(mock_undo_orchestrator, client):
    """
    Verify /undo_sync_task handles an empty list in the request.
    """
    mock_undo_orchestrator.run.side_effect = InvalidInputError(
        "Undo data cannot be empty."
    )
    request_body = []  # Empty list
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 400
    # Use 'in' as this is an InvalidInputError
    assert "Invalid Request: Undo data cannot be empty." in response.json()["detail"]


@pytest.mark.asyncio
async def test_undo_sync_task_missing_request_user(mock_undo_orchestrator, client):
    """
    Verify /undo_sync_task handles missing 'request_user' in the payload.
    """
    mock_undo_orchestrator.run.side_effect = MissingRequiredDataError(
        "Missing 'request_user' in undo data."
    )
    # The item in the list is missing the 'request_user' field.
    request_body = [
        {
            "status_text": "Success",
            "confluence_page_id": "p1",
            "original_page_version": 1,
            "new_jira_task_key": "JIRA-001",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    # A 422 error is expected because the Pydantic model validation will fail.
    assert response.status_code == 400
    # This specific assertion might also need to use re.fullmatch if your Pydantic validation adds a request_id to the detail,
    # but based on the provided main.py, it seems it doesn't.
    # If it fails, you'd change it to:
    # assert re.fullmatch(r"Malformed Results Data: Missing 'request_user' in undo data\. for request id [0-9a-fA-F]{32}", response.json()["detail"])
    assert (
        "Malformed Results Data: Missing 'request_user' in undo data."
        in response.json()["detail"]
    )


@pytest.mark.asyncio
async def test_readiness_check_confluence_failure_after_jira_success(
    mock_jira_api, mock_confluence_api, client
):
    """
    Verify /ready returns 503 if Jira is ready but Confluence is not.
    """
    # Jira API is fine
    mock_jira_api.get_current_user.return_value = {"accountId": "test_jira_user"}
    # Confluence API fails
    mock_confluence_api.get_all_spaces.side_effect = httpx.RequestError(
        "Confluence is down", request=httpx.Request("GET", "http://confluence.com")
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert "Confluence is down" in response.json()["detail"]
    mock_jira_api.get_current_user.assert_awaited_once()
    mock_confluence_api.get_all_spaces.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_task_invalid_request_body(client):
    """
    Verify that /sync_task returns a 422 error for an invalid request body.
    """
    # Request body is missing the required 'confluence_page_urls' field
    request_body = {
        "context": {"request_user": "test_user", "days_to_due_date": 7},
    }
    response = client.post(
        "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sync_project_invalid_request_body(client):
    """
    Verify that /sync_project returns a 422 error for an invalid request body.
    """
    # Request body is missing the required 'root_confluence_page_url' field
    request_body = {
        "root_project_issue_key": "PROJ-123",
        "project_issue_type_id": "10001",
        "phase_issue_type_id": "10002",
        "request_user": "test_user",
    }
    response = client.post(
        "/sync_project", json=request_body, headers={"X-API-Key": "valid_key"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_readiness_check_unhandled_exception(mock_jira_api, client):
    """
    Verify /ready returns 503 on an unexpected exception.
    """
    # Simulate a generic, unexpected error during the readiness check
    mock_jira_api.get_current_user.side_effect = Exception(
        "A rare, unexpected error occurred"
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert "A rare, unexpected error occurred" in response.json()["detail"]
    mock_jira_api.get_current_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_task_continues_on_input_file_error(mock_sync_orchestrator, client):
    """
    Verify /sync_task continues and succeeds even if writing the input file fails.
    The logic should log the file-write error but not crash the operation.
    """
    request_body = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "test_user", "days_to_due_date": 7},
    }

    # The known path of the input file from the common_dependencies_override fixture
    target_input_file_path = "/mock/input/mock_file.json"

    # We need a reference to the real open to use for non-matching files
    original_open = open

    def selective_mock_open(filename, *args, **kwargs):
        """This function will act as our mock for the 'open' call."""
        if filename == target_input_file_path:
            # If the filename matches our target, raise the error.
            raise IOError("Disk full")
        else:
            # For any other filename (like logs), use the real 'open'.
            return original_open(filename, *args, **kwargs)

    # Use a context manager to patch 'builtins.open' with our selective mock
    with patch("builtins.open", side_effect=selective_mock_open):
        response = client.post(
            "/sync_task", json=request_body, headers={"X-API-Key": "valid_key"}
        )

    # The operation should still be successful because the file-write error is caught
    assert response.status_code == 200
    # The main logic should still run and return the mocked orchestrator's results
    assert len(response.json()) == 1
    assert response.json()[0]["new_jira_task_key"] == "JIRA-001"
    mock_sync_orchestrator.run.assert_awaited_once()


def test_api_key_missing():
    """Test that endpoints return 403 if X-API-Key is missing."""
    request_body = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "test_user", "days_to_due_date": 7},
    }
    app.dependency_overrides = {}
    with TestClient(app) as local_client:
        response = local_client.post("/sync_task", json=request_body)
        assert response.status_code == 403  # FastAPI returns 403 for missing dependency


def test_ready_missing_dependencies():
    """Test /ready endpoint when dependencies are missing."""

    # Dummy classes whose methods raise exceptions when called
    class DummyJiraApi:
        async def get_current_user(self):
            raise Exception("Jira dependency missing")

    class DummyConfluenceApi:
        async def get_all_spaces(self):
            raise Exception("Confluence dependency missing")

    app.dependency_overrides = {
        get_safe_jira_api: lambda: DummyJiraApi(),
        get_safe_confluence_api: lambda: DummyConfluenceApi(),
    }
    with TestClient(app) as local_client:
        response = local_client.get("/ready")
        assert response.status_code == 503
        assert "Jira dependency missing" in response.json()["detail"]


def test_invalid_endpoint(client):
    """Test that an invalid endpoint returns 404."""
    response = client.get("/nonexistent_endpoint")
    assert response.status_code == 404


def test_health_wrong_method(client):
    """Test /health endpoint with POST (should return 405)."""
    response = client.post("/health")
    assert response.status_code == 405
