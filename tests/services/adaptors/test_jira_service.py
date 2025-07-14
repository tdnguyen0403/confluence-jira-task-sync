"""
Tests for the high-level JiraService, using stubs and modern pytest practices.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

# Import the code to be tested and its dependencies
from src.api.safe_jira_api import SafeJiraApi
from src.models.data_models import ConfluenceTask
from src.services.adaptors.jira_service import JiraService


# --- Updated Stub for the underlying SafeJiraApi ---
class SafeJiraApiStub(SafeJiraApi):
    """A controlled stub for the Jira API to provide predictable test data."""

    def __init__(self):
        self.mock = Mock()
        self._issues = {}
        self._issue_types = {}
        self._jql_results = {}
        self._myself_response = {"displayName": "AutomationBot"}

    def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        self.mock.get_issue(issue_key, fields)
        return self._issues.get(issue_key)

    def create_issue(self, issue_fields: dict) -> str:
        self.mock.create_issue(issue_fields)
        if "Failing Task" in issue_fields.get("fields", {}).get("summary", ""):
            return None
        return "JIRA-STUB-1"

    def get_myself(self) -> dict:
        self.mock.get_myself()
        return self._myself_response

    def search_issues(self, jql: str, fields: str = "*all", **kwargs) -> list:
        self.mock.search_issues(jql, fields=fields, **kwargs)
        return self._jql_results.get(jql, [])

    def get_issue_type_details_by_id(self, type_id: str) -> dict:
        self.mock.get_issue_type_details_by_id(type_id)
        return self._issue_types.get(type_id)

    # --- Helper methods for test setup ---
    def add_issue(self, key, data):
        self._issues[key] = data

    def add_issue_type(self, type_id, data):
        self._issue_types[type_id] = data


# --- Pytest Fixtures ---


@pytest.fixture
def mock_task():
    """Provides a standard ConfluenceTask object for tests."""
    return ConfluenceTask(
        confluence_page_id="1",
        confluence_page_title="My Page",
        confluence_page_url="http://page.url",
        confluence_task_id="t1",
        task_summary="My Summary",
        status="incomplete",
        assignee_name="assignee_user_name",
        due_date="2025-01-15",
        original_page_version=1,
        original_page_version_by="ConfluenceUser",
        original_page_version_when="now",
        context="This is the context.",
    )


@pytest.fixture
def jira_service(monkeypatch):
    """Provides a JiraService instance with a stubbed API and mocked config."""
    monkeypatch.setattr(
        "src.services.adaptors.jira_service.config.TASK_ISSUE_TYPE_ID", "10002"
    )
    monkeypatch.setattr(
        "src.services.adaptors.jira_service.config.JIRA_PARENT_WP_CUSTOM_FIELD_ID",
        "customfield_10207",
    )
    monkeypatch.setattr(
        "src.services.adaptors.jira_service.config.DEFAULT_DUE_DATE", "2025-01-01"
    )
    safe_api_stub = SafeJiraApiStub()
    service = JiraService(safe_api_stub)
    yield service, safe_api_stub


# --- All 12 Original Tests, Now Correctly Refactored ---


def test_get_issue_delegates(jira_service):
    service, api_stub = jira_service
    api_stub.add_issue("TEST-1", {"key": "TEST-1"})
    issue = service.get_issue("TEST-1", fields="summary")
    assert issue["key"] == "TEST-1"
    api_stub.mock.get_issue.assert_called_once_with("TEST-1", "summary")


def test_prepare_jira_task_fields(jira_service, mock_task, mocker):
    service, _ = jira_service
    # FIX: Patch the entire datetime module where it's used
    mock_dt = mocker.patch("src.services.adaptors.jira_service.datetime")
    mock_dt.now.return_value = datetime(2025, 1, 1, 12, 0, 0)

    result = service.prepare_jira_task_fields(mock_task, "PROJ-123", "APIRequester")
    assert result["fields"]["summary"] == "My Summary"
    assert result["fields"]["assignee"]["name"] == "assignee_user_name"
    assert (
        "Created by AutomationBot on 2025-01-01 12:00:00 requested by APIRequester"
        in result["fields"]["description"]
    )


def test_prepare_jira_task_fields_with_defaults(jira_service, mock_task, mocker):
    service, _ = jira_service
    mock_dt = mocker.patch("src.services.adaptors.jira_service.datetime")
    mock_dt.now.return_value = datetime(2025, 1, 1, 12, 0, 0)

    mock_task.assignee_name = None
    mock_task.context = None
    result = service.prepare_jira_task_fields(mock_task, "ANOTHER-456", "jira-user")
    assert "assignee" not in result["fields"]
    assert "Context from Confluence" not in result["fields"]["description"]


def test_create_issue_delegates(jira_service, mock_task, mocker):
    service, api_stub = jira_service
    mocker.patch.object(
        service, "prepare_jira_task_fields", return_value={"fields": {}}
    )
    jira_key = service.create_issue(mock_task, "PARENT-1", "ExplicitUser")
    assert jira_key == "JIRA-STUB-1"
    api_stub.mock.create_issue.assert_called_once_with({"fields": {}})


def test_create_issue_api_failure(jira_service, mock_task, mocker):
    service, _ = jira_service
    mock_task.task_summary = "Failing Task"
    mocker.patch.object(
        service,
        "prepare_jira_task_fields",
        return_value={"fields": {"summary": "Failing Task"}},
    )
    result_key = service.create_issue(mock_task, "FAIL-1", "TestUser")
    assert result_key is None


def test_search_issues_by_jql_delegation(jira_service):
    service, api_stub = jira_service
    api_stub._jql_results["project = ABC"] = [{"key": "JQL-1"}]
    result = service.search_issues_by_jql("project = ABC", fields="key")
    assert result == [{"key": "JQL-1"}]
    api_stub.mock.search_issues.assert_called_once_with("project = ABC", fields="key")


def test_get_issue_type_name_by_id_success(jira_service):
    service, api_stub = jira_service
    api_stub.add_issue_type("10000", {"id": "10000", "name": "Epic"})
    type_name = service.get_issue_type_name_by_id("10000")
    assert type_name == "Epic"
    api_stub.mock.get_issue_type_details_by_id.assert_called_once_with("10000")


def test_get_issue_type_name_by_id_failure(jira_service):
    service, api_stub = jira_service
    api_stub.add_issue_type("99999", None)
    type_name = service.get_issue_type_name_by_id("99999")
    assert type_name is None


def test_get_current_user_display_name_success(jira_service):
    service, _ = jira_service
    display_name = service.get_current_user_display_name()
    assert display_name == "AutomationBot"


def test_get_current_user_display_name_caching(jira_service):
    service, api_stub = jira_service
    service.get_current_user_display_name()
    service.get_current_user_display_name()
    api_stub.mock.get_myself.assert_called_once()


def test_get_current_user_display_name_fallback(jira_service):
    service, api_stub = jira_service
    api_stub._myself_response = None
    display_name = service.get_current_user_display_name()
    assert display_name == "Unknown User"


def test_prepare_fields_with_jira_key_context(jira_service, mock_task):
    service, api_stub = jira_service
    mock_task.context = "JIRA_KEY_CONTEXT::PARENT-1"
    api_stub.add_issue("PARENT-1", {"fields": {"description": "Parent description."}})
    result = service.prepare_jira_task_fields(mock_task, "WP-123", "test_user")
    assert "Context from parent issue PARENT-1" in result["fields"]["description"]
    assert "Parent description." in result["fields"]["description"]
