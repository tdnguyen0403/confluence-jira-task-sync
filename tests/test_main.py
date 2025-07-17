import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from src.models.data_models import SyncContext

# Import the app and dependencies
from main import app
from src.dependencies import container, get_api_key
from src.exceptions import (
    InvalidInputError,
    SyncError,
    UndoError,
)
from src.models.data_models import (
    AutomationResult,
    ConfluenceTask,
    SyncProjectPageDetail,
)

# --- Fixtures for Mocks and Test Client ---


@pytest.fixture
def mock_sync_orchestrator():
    """Provides a mock for the SyncTaskOrchestrator."""
    mock = MagicMock()
    mock.results = [
        AutomationResult(
            task_data=ConfluenceTask(
                confluence_task_id="1",
                confluence_page_id="123",
                confluence_page_title="Test Page",
                confluence_page_url="http://page.url",
                task_summary="Test Task",
                status="incomplete",
                assignee_name=None,
                due_date="2025-01-01",
                original_page_version=1,
                original_page_version_by="user",
                original_page_version_when="now",
                context="",
            ),
            status="Success",
            new_jira_key="TEST-1",
            linked_work_package="WP-1",
            request_user="test_user",
        )
    ]
    return mock


@pytest.fixture
def mock_undo_orchestrator():
    """Provides a mock for the UndoSyncTaskOrchestrator."""
    return MagicMock()


@pytest.fixture
def mock_confluence_issue_updater_service():
    """Provides a mock for the ConfluenceIssueUpdaterService."""
    mock = MagicMock()
    # Return a Pydantic model instance to prevent validation errors
    mock.update_confluence_hierarchy_with_new_jira_project.return_value = [
        SyncProjectPageDetail(
            page_id="page123",
            page_title="Test Page",
            new_jira_keys=["NEWPROJ-1"],
            root_project_linked="OLDPROJ-1",
        )
    ]
    return mock


@pytest.fixture
def client(
    mocker,
    mock_sync_orchestrator,
    mock_undo_orchestrator,
    mock_confluence_issue_updater_service,
):
    """
    Configures the TestClient with mocked dependencies for each test.
    This fixture now handles all file I/O mocking.
    """
    # Prevent all file system interaction by mocking high-level functions
    mocker.patch("main.setup_logging")
    mocker.patch(
        "src.utils.dir_helpers.get_input_path", return_value="/mock/path/input.json"
    )
    mocker.patch(
        "src.utils.dir_helpers.get_output_path", return_value="/mock/path/output.json"
    )
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("json.dump")

    # Override service dependencies
    app.dependency_overrides[container.sync_orchestrator] = (
        lambda: mock_sync_orchestrator
    )
    app.dependency_overrides[container.undo_orchestrator] = (
        lambda: mock_undo_orchestrator
    )
    app.dependency_overrides[container.confluence_issue_updater_service] = (
        lambda: mock_confluence_issue_updater_service
    )
    app.dependency_overrides[get_api_key] = lambda: "test_api_key"

    yield TestClient(app)

    app.dependency_overrides = {}  # Cleanup


# --- Test Functions (All 11 original tests restored and corrected) ---


def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]


def test_sync_confluence_tasks_success(client, mock_sync_orchestrator):
    sync_request_payload = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "Unknown User", "days_to_due_date": 14},
    }
    expected_context = SyncContext(request_user="Unknown User", days_to_due_date=14)
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/sync_task", json=sync_request_payload, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    mock_sync_orchestrator.run.assert_called_once_with(
        sync_request_payload, expected_context
    )


def test_sync_confluence_tasks_no_tasks_processed(client, mock_sync_orchestrator):
    mock_sync_orchestrator.results = []
    sync_request_payload = {
        "confluence_page_urls": ["http://example.com/page1"],
        "context": {"request_user": "Unknown User", "days_to_due_date": 14},
    }
    headers = {"X-API-Key": "test_api_key"}
    response = client.post("/sync_task", json=sync_request_payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_sync_confluence_tasks_invalid_input_error(client, mock_sync_orchestrator):
    mock_sync_orchestrator.run.side_effect = InvalidInputError("Missing URLs")
    response = client.post(
        "/sync_task",
        json={
            "confluence_page_urls": [],
            "context": {},
        },
        headers={"X-API-Key": "test_api_key"},
    )
    assert response.status_code == 400
    assert "Invalid Request: Missing URLs" in response.json()["detail"]


def test_sync_confluence_tasks_sync_error(client, mock_sync_orchestrator):
    mock_sync_orchestrator.run.side_effect = SyncError("Jira API failed")
    response = client.post(
        "/sync_task",
        json={
            "confluence_page_urls": ["http://example.com/page1"],
            "context": {"request_user": "Unknown User", "days_to_due_date": 14},
        },
        headers={"X-API-Key": "test_api_key"},
    )
    assert response.status_code == 500
    assert "Synchronization failed" in response.json()["detail"]


def test_undo_sync_run_success(client, mock_undo_orchestrator):
    undo_payload = [
        {
            "Status": "Success",
            "confluence_page_id": "1",
            "original_page_version": 1,
            "New Jira Task Key": "J-1",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=undo_payload, headers={"X-API-Key": "test_api_key"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Undo operation completed successfully."
    mock_undo_orchestrator.run.assert_called_once()


def test_undo_sync_run_invalid_input_error(client, mock_undo_orchestrator):
    mock_undo_orchestrator.run.side_effect = InvalidInputError("No results provided")
    response = client.post(
        "/undo_sync_task", json=[], headers={"X-API-Key": "test_api_key"}
    )
    assert response.status_code == 400
    assert "Invalid Request: No results provided" in response.json()["detail"]


def test_undo_sync_run_undo_error(client, mock_undo_orchestrator):
    mock_undo_orchestrator.run.side_effect = UndoError("Confluence rollback failed")
    undo_payload = [
        {
            "Status": "Success",
            "confluence_page_id": "1",
            "original_page_version": 1,
            "New Jira Task Key": "J-1",
        }
    ]
    response = client.post(
        "/undo_sync_task", json=undo_payload, headers={"X-API-Key": "test_api_key"}
    )
    assert response.status_code == 500
    assert "Undo operation failed" in response.json()["detail"]


def test_update_confluence_project_success(
    client, mock_confluence_issue_updater_service
):
    update_payload = {
        "root_confluence_page_url": "http://ok",
        "root_project_issue_key": "OLD-1",
        "request_user": "test",
    }
    response = client.post(
        "/sync_project", json=update_payload, headers={"X-API-Key": "test_api_key"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["page_id"] == "page123"
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.assert_called_once()


def test_update_confluence_project_no_pages_modified(
    client, mock_confluence_issue_updater_service
):
    mock_confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project.return_value = []
    update_payload = {
        "root_confluence_page_url": "http://ok",
        "root_project_issue_key": "OLD-1",
        "request_user": "test",
    }
    response = client.post(
        "/sync_project", json=update_payload, headers={"X-API-Key": "test_api_key"}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_api_key_unauthorized(client):
    # Temporarily remove the global key override to test the real dependency
    app.dependency_overrides[get_api_key] = get_api_key

    valid_payload = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    headers = {"X-API-Key": "wrong_key"}
    response = client.post("/sync_task", json=valid_payload, headers=headers)

    assert response.status_code == 401
    # FIX: Assert against the exact error message from FastAPI's security utils
    assert response.json()["detail"] == "Invalid API Key"
