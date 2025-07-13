import pytest
from unittest.mock import Mock, MagicMock
from src.services.orchestration.sync_task_orchestrator import SyncTaskOrchestrator
from src.models.data_models import ConfluenceTask
from src.exceptions import InvalidInputError, SyncError
from src.config import config
import logging

# Configure logger for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_confluence_service():
    mock = MagicMock()
    mock.get_page_id_from_url.return_value = "page123"
    mock.get_all_descendants.return_value = []
    # mock.get_all_descendants.return_value = ["page456"]
    mock.get_page_by_id.side_effect = [
        {
            "id": "page123",
            "body": {"storage": {"value": "content"}},
            "version": {"number": 1},
        },
        {
            "id": "page456",
            "body": {"storage": {"value": "content"}},
            "version": {"number": 1},
        },
    ]
    mock.get_tasks_from_page.return_value = [
        ConfluenceTask(
            confluence_task_id="task1",
            confluence_page_id="page123",
            task_summary="Test Task 1",
            status="incomplete",
            original_page_version=1,
            confluence_page_title="Mock Page Title",
            confluence_page_url="http://mock.confluence.com/mock-page-url",
            assignee_name="test_user",
            due_date="2025-01-01",
            original_page_version_by="Mock Author",
            original_page_version_when="2025-01-01T12:00:00.000Z",  # A valid datetime string
            context="Mock context.",  # Assuming context is also a required field
        )
    ]
    mock.update_page_with_jira_links.return_value = True
    return mock


@pytest.fixture
def mock_jira_service():
    mock = MagicMock()
    mock.create_issue.return_value = {"key": "JIRA-100", "id": "10000"}
    mock.transition_issue.return_value = True
    return mock


@pytest.fixture
def mock_issue_finder_service():
    mock = MagicMock()
    # Mocking that a Work Package is found
    mock.find_issue_on_page.return_value = {"key": "WP-001"}
    return mock


@pytest.fixture
def sync_orchestrator(
    mock_confluence_service, mock_jira_service, mock_issue_finder_service
):
    return SyncTaskOrchestrator(
        confluence_service=mock_confluence_service,
        jira_service=mock_jira_service,
        issue_finder=mock_issue_finder_service,
    )


def test_sync_orchestrator_run_success(
    sync_orchestrator, mock_confluence_service, mock_jira_service
):
    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    sync_orchestrator.run(input_data)

    assert len(sync_orchestrator.results) == 1
    assert (
        sync_orchestrator.results[0].status == "Success"
        or sync_orchestrator.results[0].status == "Success - Completed Task Created"
    )
    mock_confluence_service.get_page_id_from_url.assert_called_once_with(
        "http://example.com/page1"
    )
    mock_confluence_service.get_all_descendants.assert_called_once_with("page123")
    mock_jira_service.create_issue.assert_called_once()
    mock_confluence_service.update_page_with_jira_links.assert_called_once()


def test_sync_orchestrator_run_no_input():
    mock_confluence = Mock()
    mock_jira = Mock()
    mock_issue_finder = Mock()
    orchestrator = SyncTaskOrchestrator(mock_confluence, mock_jira, mock_issue_finder)

    with pytest.raises(InvalidInputError, match="No input JSON provided"):
        orchestrator.run({})


def test_sync_orchestrator_run_no_urls():
    mock_confluence = Mock()
    mock_jira = Mock()
    mock_issue_finder = Mock()
    orchestrator = SyncTaskOrchestrator(mock_confluence, mock_jira, mock_issue_finder)

    with pytest.raises(InvalidInputError, match="No 'confluence_page_urls' found"):
        orchestrator.run({"confluence_page_urls": []})


def test_sync_orchestrator_process_page_hierarchy_no_page_id(
    sync_orchestrator, mock_confluence_service
):
    mock_confluence_service.get_page_id_from_url.return_value = None
    with pytest.raises(SyncError, match="Could not find Confluence page ID"):
        sync_orchestrator.process_page_hierarchy("http://example.com/nonexistent")


def test_sync_orchestrator_no_work_package_found(
    sync_orchestrator, mock_issue_finder_service
):
    # Mocking that no Work Package is found for a task
    mock_issue_finder_service.find_issue_on_page.return_value = None

    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    sync_orchestrator.run(input_data)

    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Skipped - No Work Package found"
    assert sync_orchestrator.results[0].task_data.task_summary == "Test Task 1"


def test_sync_orchestrator_jira_creation_failure(sync_orchestrator, mock_jira_service):
    # Mock Jira service to return None on issue creation
    mock_jira_service.create_issue.return_value = None

    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }

    with pytest.raises(SyncError, match="Failed to create Jira task"):
        sync_orchestrator.run(input_data)

    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Failed - Jira task creation"


def test_sync_orchestrator_completed_task_transition(
    sync_orchestrator, mock_jira_service, mock_confluence_service
):
    # Setup a completed task
    mock_confluence_service.get_tasks_from_page.return_value = [
        ConfluenceTask(
            confluence_task_id="task1",
            confluence_page_id="page123",
            task_summary="Test Task 1",
            status="complete",
            original_page_version=1,
            confluence_page_title="Mock Page Title",
            confluence_page_url="http://mock.confluence.com/mock-page",
            assignee_name="mock_assignee",
            due_date="2025-12-31",  # Ensure this matches the format your model expects if not Optional
            original_page_version_by="Mock Test Author",
            original_page_version_when="2025-01-01T10:00:00Z",  # Ensure this matches the format your model expects
            context="Mock task context.",
        )
    ]
    mock_jira_service.create_issue.return_value = {"key": "JIRA-200", "id": "20000"}

    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    sync_orchestrator.run(input_data)

    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Success - Completed Task Created"
    mock_jira_service.transition_issue.assert_called_with(
        "JIRA-200", config.JIRA_TARGET_STATUSES["completed_task"]
    )


def test_sync_orchestrator_dev_mode_new_task_transition(
    sync_orchestrator, mock_jira_service, monkeypatch
):
    # Temporarily set PRODUCTION_MODE to False
    monkeypatch.setattr(config, "PRODUCTION_MODE", False)

    mock_jira_service.create_issue.return_value = {"key": "JIRA-300", "id": "30000"}

    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }
    sync_orchestrator.run(input_data)

    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Success"
    mock_jira_service.transition_issue.assert_called_with(
        "JIRA-300", config.JIRA_TARGET_STATUSES["new_task_dev"]
    )
