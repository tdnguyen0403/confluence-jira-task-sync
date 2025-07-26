"""
Tests for the high-level JiraService, using stubs and modern pytest practices.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock  # Changed to AsyncMock

import pytest
import pytest_asyncio

from src.api.safe_jira_api import SafeJiraApi

# Import the code to be tested and its dependencies
from src.config import config
from src.models.data_models import ConfluenceTask, SyncContext
from src.services.adaptors.jira_service import JiraService


# --- Updated Stub for the underlying SafeJiraApi ---
class SafeJiraApiStub(SafeJiraApi):
    """A controlled stub for the Jira API to provide predictable test data."""

    def __init__(self):
        # Changed to AsyncMock
        self.mock = AsyncMock()
        self._issues = {}
        self._issue_types = {}
        self._jql_results = {}
        self._myself_response = {"displayName": "AutomationBot"}

    async def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        await self.mock.get_issue(issue_key, fields)
        return self._issues.get(issue_key)

    async def create_issue(self, issue_fields: dict) -> dict:
        await self.mock.create_issue(issue_fields)
        if "Failing Task" in issue_fields.get("fields", {}).get("summary", ""):
            return None
        return {"key": "JIRA-STUB-1"}

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        await self.mock.transition_issue(issue_key, target_status)
        return True

    async def get_current_user(self) -> dict:
        await self.mock.get_current_user()
        return self._myself_response

    async def search_issues(self, jql: str, fields: str = "*all", **kwargs) -> dict:
        await self.mock.search_issues(jql, fields=fields, **kwargs)
        return self._jql_results.get(jql, {"issues": []})

    async def get_issue_type_details_by_id(self, type_id: str) -> dict:
        await self.mock.get_issue_type_details_by_id(type_id)
        return self._issue_types.get(type_id)

    async def assign_issue(self, issue_key: str, assignee_name: str) -> dict:
        """Stub for assign_issue method."""
        await self.mock.assign_issue(issue_key, assignee_name)
        return {}  # Jira often returns an empty dict or 204 No Content

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


# Changed to pytest_asyncio.fixture
@pytest_asyncio.fixture
async def jira_service(monkeypatch):
    """Provides a JiraService instance with a stubbed API and mocked config."""
    monkeypatch.setattr(
        "src.services.adaptors.jira_service.config.TASK_ISSUE_TYPE_ID", "10002"
    )
    monkeypatch.setattr(
        "src.services.adaptors.jira_service.config.JIRA_PARENT_WP_CUSTOM_FIELD_ID",
        "customfield_10207",
    )
    safe_api_stub = SafeJiraApiStub()
    service = JiraService(safe_api_stub)
    yield service, safe_api_stub


@pytest.fixture
def mock_context():
    """Provides a default SyncContext object for tests."""
    return SyncContext(request_user="default_user", days_to_due_date=7)


@pytest.mark.asyncio
async def test_get_issue_delegates(jira_service):
    service, api_stub = jira_service
    api_stub.add_issue("TEST-1", {"key": "TEST-1"})
    issue = await service.get_issue("TEST-1", fields="summary")
    assert issue["key"] == "TEST-1"
    api_stub.mock.get_issue.assert_called_once_with("TEST-1", "summary")


@pytest.mark.asyncio
async def test_create_issue_delegates(jira_service, mock_task, mocker):
    service, api_stub = jira_service
    mocker.patch.object(
        service, "prepare_jira_task_fields", return_value={"fields": {}}
    )
    jira_key = await service.create_issue(mock_task, "PARENT-1", mock_context)
    assert jira_key == "JIRA-STUB-1"
    api_stub.mock.create_issue.assert_called_once_with({"fields": {}})


@pytest.mark.asyncio
async def test_create_issue_api_failure(jira_service, mock_task, mocker):
    service, _ = jira_service
    mock_task.task_summary = "Failing Task"
    mocker.patch.object(
        service,
        "prepare_jira_task_fields",
        return_value={"fields": {"summary": "Failing Task"}},
    )
    result_key = await service.create_issue(mock_task, "FAIL-1", mock_context)
    assert result_key is None


@pytest.mark.asyncio
async def test_search_issues_by_jql_delegation(jira_service):
    service, api_stub = jira_service
    api_stub._jql_results["project = ABC"] = {"issues": [{"key": "JQL-1"}]}
    result = await service.search_issues_by_jql("project = ABC", fields="key")
    assert result == {"issues": [{"key": "JQL-1"}]}
    api_stub.mock.search_issues.assert_called_once_with("project = ABC", fields="key")


@pytest.mark.asyncio
async def test_get_issue_type_name_by_id_success(jira_service):
    service, api_stub = jira_service
    api_stub.add_issue_type("10000", {"id": "10000", "name": "Epic"})
    type_name = await service.get_issue_type_name_by_id("10000")
    assert type_name == "Epic"
    api_stub.mock.get_issue_type_details_by_id.assert_called_once_with("10000")


@pytest.mark.asyncio
async def test_get_issue_type_name_by_id_failure(jira_service):
    service, api_stub = jira_service
    api_stub.add_issue_type("99999", None)
    type_name = await service.get_issue_type_name_by_id("99999")
    assert type_name is None


@pytest.mark.asyncio
async def test_get_current_user_display_name_success(jira_service):
    service, _ = jira_service
    display_name = await service.get_current_user_display_name()
    assert display_name == "AutomationBot"


@pytest.mark.asyncio
async def test_get_current_user_display_name_caching(jira_service):
    service, api_stub = jira_service
    await service.get_current_user_display_name()
    await service.get_current_user_display_name()
    api_stub.mock.get_current_user.assert_called_once()


@pytest.mark.asyncio
async def test_get_current_user_display_name_fallback(jira_service):
    service, api_stub = jira_service
    api_stub._myself_response = None
    display_name = await service.get_current_user_display_name()
    assert display_name == "Unknown User"


@pytest.mark.asyncio
async def test_prepare_jira_task_fields(jira_service, mock_task, mock_context):
    service, _ = jira_service
    result = await service.prepare_jira_task_fields(mock_task, "PROJ-123", mock_context)
    expected_description = (
        f"Context from Confluence:\n{mock_task.context}\n\n"
        f"Created by AutomationBot on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"requested by {mock_context.request_user}"
    )
    assert result["summary"] == "My Summary"
    assert result["description"] == expected_description
    assert result["duedate"] == "2025-01-15"
    assert result["assignee"]["name"] == "assignee_user_name"


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_with_defaults_context(
    jira_service, mock_task, mock_context
):
    service, _ = jira_service
    mock_task.due_date = None
    mock_task.assignee_name = (
        None  # Set assignee to None to properly test default assignment logic.
    )
    expected_due_date = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    result = await service.prepare_jira_task_fields(
        mock_task, "ANOTHER-456", mock_context
    )
    assert result["summary"] == "My Summary"
    assert result["duedate"] == expected_due_date


@pytest.mark.asyncio
async def test_prepare_fields_with_jira_key_context(
    jira_service, mock_task, mock_context
):
    service, api_stub = jira_service
    mock_task.context = "JIRA_KEY_CONTEXT::PARENT-1"
    api_stub.add_issue("PARENT-1", {"fields": {"description": "Parent description."}})
    result = await service.prepare_jira_task_fields(mock_task, "WP-123", mock_context)
    assert "Context from parent issue PARENT-1" in result["description"]
    assert "Parent description." in result["description"]


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_trims_long_summary(jira_service, mock_task):
    """Verify that a summary exceeding the character limit is truncated."""
    service, _ = jira_service
    mock_task.task_summary = "A" * (config.JIRA_SUMMARY_MAX_CHARS + 100)
    mock_context = SyncContext(request_user="test_user", days_to_due_date=7)
    result = await service.prepare_jira_task_fields(mock_task, "PROJ-123", mock_context)

    assert result is not None
    assert len(result["summary"]) == config.JIRA_SUMMARY_MAX_CHARS
    assert result["summary"].endswith("...")


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_trims_long_description(jira_service, mock_task):
    """Verify that a description exceeding the character limit is truncated."""
    service, _ = jira_service
    mock_task.context = "B" * (config.JIRA_DESCRIPTION_MAX_CHARS + 100)
    mock_context = SyncContext(request_user="test_user", days_to_due_date=7)
    result = await service.prepare_jira_task_fields(mock_task, "PROJ-123", mock_context)

    assert result is not None
    assert len(result["description"]) == config.JIRA_DESCRIPTION_MAX_CHARS
    assert result["description"].endswith("...")


@pytest.mark.asyncio
async def test_transition_issue_success(jira_service):
    service, api_stub = jira_service
    result = await service.transition_issue("TEST-1", "Done")
    assert result is True
    api_stub.mock.transition_issue.assert_called_once_with("TEST-1", "Done")


@pytest.mark.asyncio
async def test_transition_issue_failure(jira_service, mocker):
    service, api_stub = jira_service
    mocker.patch.object(api_stub, "transition_issue", side_effect=Exception("fail"))
    result = await service.transition_issue("TEST-1", "Done")
    assert result is False


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_context_issue_summary_fallback(
    jira_service, mock_task, mock_context
):
    service, api_stub = jira_service
    mock_task.context = "JIRA_KEY_CONTEXT::PARENT-2"
    api_stub.add_issue("PARENT-2", {"fields": {"summary": "Parent summary only"}})
    result = await service.prepare_jira_task_fields(mock_task, "WP-123", mock_context)
    assert "Parent summary only" in result["description"]


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_context_issue_not_found(
    jira_service, mock_task, mock_context
):
    service, api_stub = jira_service
    mock_task.context = "JIRA_KEY_CONTEXT::NOTFOUND"
    result = await service.prepare_jira_task_fields(mock_task, "WP-123", mock_context)
    assert "Could not retrieve details" in result["description"]


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_no_context(
    jira_service, mock_task, mock_context
):
    service, _ = jira_service
    mock_task.context = None
    result = await service.prepare_jira_task_fields(mock_task, "WP-123", mock_context)
    assert "Created by AutomationBot" in result["description"]


@pytest.mark.asyncio
async def test_get_issue_status_success(jira_service, mocker):
    service, api_stub = jira_service
    mock_issue_data = {
        "fields": {
            "status": {"name": "In Progress", "statusCategory": {"key": "in-progress"}}
        }
    }
    api_stub.add_issue("ISSUE-1", mock_issue_data)
    mocker.patch.object(api_stub, "get_issue", return_value=mock_issue_data)
    status = await service.get_issue_status("ISSUE-1")
    assert status is not None
    assert status.name == "In Progress"
    assert status.category == "in-progress"


@pytest.mark.asyncio
async def test_get_issue_status_failure(jira_service, mocker):
    service, api_stub = jira_service
    mocker.patch.object(api_stub, "get_issue", side_effect=Exception("fail"))
    status = await service.get_issue_status("ISSUE-1")
    assert status is None


@pytest.mark.asyncio
async def test_get_jira_issue_success(jira_service, mocker):
    service, api_stub = jira_service
    mock_issue_data = {
        "key": "ISSUE-2",
        "fields": {
            "summary": "Test Summary",
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Task"},
        },
    }
    mocker.patch.object(api_stub, "get_issue", return_value=mock_issue_data)
    issue = await service.get_jira_issue("ISSUE-2")
    assert issue is not None
    assert issue.key == "ISSUE-2"
    assert issue.summary == "Test Summary"
    assert issue.status.name == "Done"
    assert issue.status.category == "done"
    assert issue.issue_type == "Task"


@pytest.mark.asyncio
async def test_get_jira_issue_failure(jira_service, mocker):
    service, api_stub = jira_service
    mocker.patch.object(api_stub, "get_issue", side_effect=Exception("fail"))
    issue = await service.get_jira_issue("ISSUE-2")
    assert issue is None


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_no_summary(
    jira_service, mock_task, mock_context
):
    service, _ = jira_service
    mock_task.task_summary = None
    result = await service.prepare_jira_task_fields(mock_task, "PROJ-123", mock_context)
    assert result["summary"] == "No Summary Provided"


@pytest.mark.asyncio
async def test_prepare_jira_task_fields_no_description(
    jira_service, mock_task, mock_context
):
    service, _ = jira_service
    mock_task.context = None
    result = await service.prepare_jira_task_fields(mock_task, "PROJ-123", mock_context)
    assert result["description"] is not None


@pytest.mark.asyncio
async def test_assign_issue_delegates_success(jira_service):
    """Tests successful assignment of a Jira issue through JiraService."""
    service, api_stub = jira_service
    issue_key = "PROJ-ASSIGN-1"
    assignee_name = "test_user_assign"
    result = await service.assign_issue(issue_key, assignee_name)
    assert result is True
    api_stub.mock.assign_issue.assert_awaited_once_with(issue_key, assignee_name)


@pytest.mark.asyncio
async def test_assign_issue_unassign_delegates_success(jira_service):
    """Tests successful unassignment of a Jira issue through JiraService."""
    service, api_stub = jira_service
    issue_key = "PROJ-UNASSIGN-1"
    result = await service.assign_issue(issue_key, None)
    assert result is True
    api_stub.mock.assign_issue.assert_awaited_once_with(issue_key, None)


@pytest.mark.asyncio
async def test_assign_issue_delegates_failure(jira_service):
    """Tests error handling when assigning/unassigning an issue through JiraService."""
    service, api_stub = jira_service
    issue_key = "PROJ-FAIL-ASSIGN"
    assignee_name = "error_user"
    api_stub.mock.assign_issue.side_effect = Exception("API assignment failed")

    result = await service.assign_issue(issue_key, assignee_name)
    assert result is False
    api_stub.mock.assign_issue.assert_awaited_once_with(issue_key, assignee_name)
