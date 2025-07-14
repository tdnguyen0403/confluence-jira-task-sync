"""
Tests for the UndoSyncTaskOrchestrator using stubs for service dependencies.
"""

import pytest
from typing import Any, Dict, Optional

from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)
from src.exceptions import InvalidInputError, MissingRequiredDataError
from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import ConfluenceTask

# --- Stubs for Service Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self):
        self._pages = {}
        self.updated_pages = set()
        self.should_fail_get = False

    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        if self.should_fail_get:
            return None
        if "version" in kwargs:
            return self._pages.get(page_id, {}).get("historical")
        return self._pages.get(page_id, {}).get("current")

    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool:
        self.updated_pages.add(page_id)
        return True

    def add_page_version(
        self, page_id: str, historical_content: str, current_title: str
    ):
        self._pages[page_id] = {
            "historical": {"body": {"storage": {"value": historical_content}}},
            "current": {"title": current_title},
        }

    def get_all_descendants(self, page_id: str) -> list:
        pass

    def get_page_id_from_url(self, url: str) -> str:
        pass

    def get_tasks_from_page(self, page_details: dict) -> list:
        pass

    def update_page_with_jira_links(self, page_id: str, mappings: list) -> None:
        pass

    def create_page(self, **kwargs) -> dict:
        pass

    def get_user_details_by_username(self, username: str) -> dict:
        pass


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self.transitioned_issues = {}
        self._should_fail_transition = False

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        if self._should_fail_transition:
            raise Exception("Jira API Error")
        self.transitioned_issues[issue_key] = target_status
        return True

    def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        pass

    def create_issue(
        self, task: ConfluenceTask, parent_key: str, request_user: str = "jira-user"
    ) -> str:
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


# --- Pytest Fixtures ---


@pytest.fixture
def confluence_stub():
    return ConfluenceServiceStub()


@pytest.fixture
def jira_stub():
    return JiraServiceStub()


@pytest.fixture
def undo_orchestrator(confluence_stub, jira_stub):
    return UndoSyncTaskOrchestrator(
        confluence_service=confluence_stub, jira_service=jira_stub
    )


# --- Pytest Test Functions ---


def test_run_success(undo_orchestrator, jira_stub, confluence_stub):
    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-100",
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]
    confluence_stub.add_page_version("1", "old content", "Current Title")
    undo_orchestrator.run(results_data)
    assert (
        jira_stub.transitioned_issues.get("JIRA-100")
        == config.JIRA_TARGET_STATUSES["undo"]
    )
    assert "1" in confluence_stub.updated_pages


def test_run_no_input(undo_orchestrator):
    with pytest.raises(InvalidInputError, match="No results JSON data provided"):
        undo_orchestrator.run([])


# --- TEST RESTORED ---
def test_run_empty_data(undo_orchestrator):
    """Test that an InvalidInputError is raised for a list with empty data."""
    with pytest.raises(InvalidInputError, match="Provided JSON data is empty"):
        undo_orchestrator.run([{}])


def test_run_missing_required_columns(undo_orchestrator):
    results_data = [{"Status": "Success"}]
    with pytest.raises(
        MissingRequiredDataError, match="Results data is missing required columns"
    ):
        undo_orchestrator.run(results_data)


def test_transition_jira_tasks_failure(
    undo_orchestrator, jira_stub, confluence_stub, caplog
):
    # Arrange
    jira_stub._should_fail_transition = True
    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-FAIL",
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]
    confluence_stub.add_page_version("1", "old content", "Current Title")

    # Act
    with caplog.at_level("INFO"):
        undo_orchestrator.run(results_data)

    # Assert
    assert "Failed to transition Jira issue 'JIRA-FAIL'" in caplog.text
    # --- FIX: Assert against the correct log message ---
    assert "Attempting to roll back page 1 to version 1" in caplog.text


def test_rollback_confluence_failure(undo_orchestrator, confluence_stub, caplog):
    confluence_stub.should_fail_get = True
    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-100",
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]
    with caplog.at_level("ERROR"):
        undo_orchestrator.run(results_data)
    assert "Failed to get content for page '1' version 1" in caplog.text
    assert not confluence_stub.updated_pages


def test_no_actions_on_skipped_or_failed_status(
    undo_orchestrator, jira_stub, confluence_stub
):
    results_data = [
        {
            "Status": "Skipped",
            "New Jira Task Key": None,
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]
    undo_orchestrator.run(results_data)
    assert not jira_stub.transitioned_issues
    assert not confluence_stub.updated_pages
