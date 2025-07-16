"""
Tests for the SyncTaskOrchestrator using stubs for service dependencies.
"""

import pytest
from typing import Any, Dict, List, Optional

from src.services.orchestration.sync_task_orchestrator import SyncTaskOrchestrator
from src.models.data_models import ConfluenceTask
from src.exceptions import InvalidInputError, SyncError
from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface

# --- Test Data ---


@pytest.fixture
def sample_task():
    """A sample ConfluenceTask for use in tests."""
    return ConfluenceTask(
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
        original_page_version_when="2025-01-01T12:00:00.000Z",
        context="Mock context.",
    )


# --- Stubs for Service Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self, task_to_return):
        self._task = task_to_return
        self.updated_with_links = False

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        return "page123" if "nonexistent" not in url else None

    def get_all_descendants(self, page_id: str) -> List[str]:
        return []  # Keep it simple for these tests

    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        return {
            "id": page_id,
            "body": {"storage": {"value": "content"}},
            "version": {"number": 1},
        }

    def get_tasks_from_page(self, page_details: Dict[str, Any]) -> List[ConfluenceTask]:
        # Return the predefined task for the test
        return [self._task] if self._task else []

    def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> bool:
        self.updated_with_links = True
        return True

    # --- Methods not used in these tests, but required by the interface ---
    def create_page(self, **kwargs) -> dict:
        pass

    def update_page_content(self, page_id: str, title: str, body: str) -> bool:
        pass

    def get_user_details_by_username(self, username: str) -> dict:
        pass


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self.created_issue_key = "JIRA-100"
        self.transitioned_issue_key = None
        self.transitioned_to_status = None

    def create_issue(
        self,
        task: ConfluenceTask,
        parent_key: str,
        request_user: Optional[str] = "jira-user",
    ) -> Optional[Dict[str, Any]]:
        return {"key": self.created_issue_key} if self.created_issue_key else None

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        self.transitioned_issue_key = issue_key
        self.transitioned_to_status = target_status
        return True

    # --- Methods not used in these tests, but required by the interface ---
    def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        pass

    def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, request_user: str
    ) -> dict:
        pass

    def get_current_user_display_name(self) -> str:
        pass

    def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> list:
        pass

    def get_issue_type_name_by_id(self, type_id: str) -> str:
        pass


class IssueFinderServiceStub(IssueFinderServiceInterface):
    def __init__(self):
        self.found_issue_key = "WP-001"

    def find_issue_on_page(
        self, page_id: str, issue_type_map: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        return {"key": self.found_issue_key} if self.found_issue_key else None


# --- Pytest Fixtures ---


@pytest.fixture
def confluence_stub(sample_task):
    return ConfluenceServiceStub(sample_task)


@pytest.fixture
def jira_stub():
    return JiraServiceStub()


@pytest.fixture
def issue_finder_stub():
    return IssueFinderServiceStub()


@pytest.fixture
def sync_orchestrator(confluence_stub, jira_stub, issue_finder_stub):
    """Provides a SyncTaskOrchestrator instance with stubbed services."""
    return SyncTaskOrchestrator(
        confluence_service=confluence_stub,
        jira_service=jira_stub,
        issue_finder=issue_finder_stub,
    )


# --- Pytest Test Functions ---


def test_run_success(sync_orchestrator, confluence_stub, jira_stub):
    """Test the main success path where a task is found and synced."""
    # Arrange
    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }

    # Act
    sync_orchestrator.run(input_data)

    # Assert
    assert len(sync_orchestrator.results) == 1
    result = sync_orchestrator.results[0]
    assert result.status == "Success"
    assert result.new_jira_key == "JIRA-100"
    assert confluence_stub.updated_with_links is True


def test_run_no_input(sync_orchestrator):
    """Test that an error is raised for empty input."""
    with pytest.raises(InvalidInputError, match="No input JSON provided"):
        sync_orchestrator.run({})


def test_run_no_urls(sync_orchestrator):
    """Test that an error is raised if no URLs are provided."""
    with pytest.raises(InvalidInputError, match="No 'confluence_page_urls' found"):
        sync_orchestrator.run({"confluence_page_urls": []})


def test_process_page_hierarchy_no_page_id(sync_orchestrator):
    """Test that an error is raised if a Confluence URL cannot be resolved."""
    with pytest.raises(SyncError, match="Could not find Confluence page ID"):
        sync_orchestrator.process_page_hierarchy("http://example.com/nonexistent")


def test_no_work_package_found(sync_orchestrator, issue_finder_stub, sample_task):
    """Test that a task is skipped if no parent Work Package is found."""
    # Arrange
    issue_finder_stub.found_issue_key = None  # Simulate not finding a WP
    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }

    # Act
    sync_orchestrator.run(input_data)

    # Assert
    assert len(sync_orchestrator.results) == 1
    result = sync_orchestrator.results[0]
    assert result.status == "Skipped - No Work Package found"
    assert result.task_data.task_summary == sample_task.task_summary


def test_jira_creation_failure(sync_orchestrator, jira_stub):
    """Test that an error is raised if the Jira issue creation fails."""
    # Arrange
    jira_stub.created_issue_key = None  # Simulate Jira API failure
    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }

    # Act & Assert
    with pytest.raises(SyncError, match="Failed to create Jira task"):
        sync_orchestrator.run(input_data)

    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Failed - Jira task creation"


def test_completed_task_transition(
    sync_orchestrator, confluence_stub, jira_stub, sample_task
):
    """Test that a completed Confluence task is transitioned to 'Done' in Jira."""
    # Arrange
    sample_task.status = "complete"  # Mark the task as complete
    confluence_stub._task = sample_task
    jira_stub.created_issue_key = "JIRA-200"
    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }

    # Act
    sync_orchestrator.run(input_data)

    # Assert
    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Success - Completed Task Created"
    assert jira_stub.transitioned_issue_key == "JIRA-200"
    assert (
        jira_stub.transitioned_to_status
        == config.JIRA_TARGET_STATUSES["completed_task"]
    )


def test_dev_mode_new_task_transition(sync_orchestrator, jira_stub, monkeypatch):
    """Test that in dev mode, a new task is transitioned to 'Backlog'."""
    # Arrange
    monkeypatch.setattr(config, "DEV_ENVIRONMENT", False)  # Set dev mode
    jira_stub.created_issue_key = "JIRA-300"
    input_data = {
        "confluence_page_urls": ["http://example.com/page1"],
        "request_user": "test_user",
    }

    # Act
    sync_orchestrator.run(input_data)

    # Assert
    assert len(sync_orchestrator.results) == 1
    assert sync_orchestrator.results[0].status == "Success"
    assert jira_stub.transitioned_issue_key == "JIRA-300"
    assert (
        jira_stub.transitioned_to_status == config.JIRA_TARGET_STATUSES["new_task_dev"]
    )
