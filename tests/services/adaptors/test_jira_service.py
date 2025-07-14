"""
Tests for the high-level JiraService.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

# Assuming your project structure allows this import path
from src.api.safe_jira_api import SafeJiraApi
from src.models.data_models import ConfluenceTask
from src.services.adaptors.jira_service import JiraService


# --- Stub for the underlying SafeJiraApi ---
class SafeJiraApiStub(SafeJiraApi):
    def __init__(self):
        self.mock = Mock()
        self.base_url = "http://stub.jira.example.com"
        self._should_fail_create = False

    def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        self.mock.get_issue(issue_key, fields)
        return {"key": issue_key, "fields": {"summary": "Stubbed Issue"}}

    def create_issue(self, issue_fields: dict) -> str:
        self.mock.create_issue(issue_fields)
        if self._should_fail_create:
            return None  # Simulate API failure
        project_key = (
            issue_fields.get("fields", {}).get("project", {}).get("key", "STUB")
        )
        return f"{project_key}-1"

    def get_myself(self) -> dict:
        self.mock.get_myself()
        return {"displayName": "AutomationBot"}

    def search_issues(self, jql: str, fields: str = "*all", **kwargs) -> list:
        self.mock.search_issues(jql, fields, **kwargs)
        return [{"key": "JQL-1"}]

    def get_issue_type_details_by_id(self, type_id: str) -> dict:
        self.mock.get_issue_type_details_by_id(type_id)
        return {"id": type_id, "name": "Epic"} if type_id == "10000" else None

    def simulate_create_failure(self):
        """Helper method to make the stub fail the next create_issue call."""
        self._should_fail_create = True


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
def jira_service_with_stub(monkeypatch):
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


# --- Pytest Test Functions ---


def test_get_issue_delegates_to_safe_api(jira_service_with_stub):
    service, mock_api = jira_service_with_stub
    issue = service.get_issue("TEST-1", fields="summary")
    assert issue["key"] == "TEST-1"
    mock_api.mock.get_issue.assert_called_once_with("TEST-1", "summary")


def test_prepare_jira_task_fields(jira_service_with_stub, mock_task, mocker):
    """Test that prepare_jira_task_fields correctly constructs the payload."""
    service, _ = jira_service_with_stub
    mocked_dt = mocker.patch("src.services.adaptors.jira_service.datetime")
    mocked_dt.now.return_value = datetime(2025, 1, 1, 12, 0, 0)

    parent_key = "PROJ-123"
    test_request_user = "APIRequester"

    result = service.prepare_jira_task_fields(mock_task, parent_key, test_request_user)

    assert result["fields"]["project"]["key"] == "PROJ"
    assert result["fields"]["summary"] == "My Summary"
    expected_description = (
        "Context from Confluence:\nThis is the context.\n\n"
        f"Created by AutomationBot on 2025-01-01 12:00:00 requested by {test_request_user}"
    )
    assert result["fields"]["description"] == expected_description


# --- TEST RESTORED ---
def test_prepare_jira_task_fields_with_default_user_and_no_assignee(
    jira_service_with_stub, mock_task, mocker
):
    """Test prepare_jira_task_fields with default user and None for assignee/context."""
    service, _ = jira_service_with_stub
    mocked_dt = mocker.patch("src.services.adaptors.jira_service.datetime")
    mocked_dt.now.return_value = datetime(2025, 1, 1, 12, 0, 0)

    # Modify task for this specific test case
    mock_task.assignee_name = None
    mock_task.context = None
    mock_task.due_date = None  # Test default due date

    result = service.prepare_jira_task_fields(mock_task, "PROJ-123", "jira-user")

    assert "assignee" not in result["fields"]
    assert result["fields"]["duedate"] == "2025-01-01"
    expected_description = (
        "Created by AutomationBot on 2025-01-01 12:00:00 requested by jira-user"
    )
    assert result["fields"]["description"] == expected_description


def test_create_issue_delegates_and_prepares_fields(jira_service_with_stub, mock_task):
    service, mock_api = jira_service_with_stub
    parent_key = "PARENT-1"

    jira_key = service.create_issue(mock_task, parent_key, "ExplicitUser")

    mock_api.mock.create_issue.assert_called_once()
    assert jira_key == "PARENT-1"


def test_create_issue_with_default_user(jira_service_with_stub, mock_task):
    """Test create_issue delegates correctly with the default request_user."""
    service, mock_api = jira_service_with_stub
    mocker_prepare = Mock(
        return_value={"fields": {}}
    )  # Mock the prepare method to isolate create_issue
    service.prepare_jira_task_fields = mocker_prepare

    service.create_issue(mock_task, "PARENT-1")  # No request_user passed

    # Assert that when no user is passed to create_issue, it calls prepare_fields with the default
    mocker_prepare.assert_called_once_with(mock_task, "PARENT-1", "jira-user")
    mock_api.mock.create_issue.assert_called_once()


def test_create_issue_api_failure(jira_service_with_stub, mock_task):
    """Test that create_issue handles API failures gracefully."""
    service, mock_api = jira_service_with_stub
    # Tell the stub to fail the next API call
    mock_api.simulate_create_failure()

    result_key = service.create_issue(mock_task, "FAIL-1", "TestUser")

    assert result_key is None
    mock_api.mock.create_issue.assert_called_once()


def test_search_issues_by_jql_delegation(jira_service_with_stub):
    """Test that search_issues_by_jql delegates to the stub correctly."""
    service, mock_api = jira_service_with_stub
    jql_query = "project = ABC AND status = Done"

    result = service.search_issues_by_jql(jql_query, fields="key")

    assert result == [{"key": "JQL-1"}]
    mock_api.mock.search_issues.assert_called_once_with(jql_query, "key")


def test_get_issue_type_name_by_id(jira_service_with_stub):
    """Test get_issue_type_name_by_id returns the correct name from the stub."""
    service, _ = jira_service_with_stub
    type_name_success = service.get_issue_type_name_by_id("10000")
    type_name_failure = service.get_issue_type_name_by_id("99999")

    assert type_name_success == "Epic"
    assert type_name_failure is None
