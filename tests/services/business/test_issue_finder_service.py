import re
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import ConfluenceTask, JiraIssue, JiraIssueStatus
from src.models.api_models import SyncTaskContext
from src.services.business.issue_finder_service import IssueFinderService


# --- Stubs for Dependencies ---


class ConfluenceApiStub(ConfluenceApiServiceInterface):
    """A complete stub that implements the Confluence interface for tests."""

    def __init__(self):
        self._page_content: Dict[str, Any] = {}

    def set_page_content(self, page_id: str, content: Optional[str]):
        if content is None:
            self._page_content.pop(page_id, None)
            return

        self._page_content[page_id] = {
            "id": page_id,
            "title": f"Page {page_id}",
            "body": {"storage": {"value": content}},
            "ancestors": [],
        }

    async def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        return self._page_content.get(page_id)

    # Implement all other abstract methods to satisfy the interface contract
    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        return "stub_id"

    async def get_all_descendants(self, page_id: str) -> List[str]:
        return []

    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        return []

    async def update_page_with_jira_links(
        self, page_id: str, jira_task_mappings: List[Dict[str, str]]
    ) -> bool:
        return True

    async def update_page_content(
        self, page_id: str, title: str, html_content: str
    ) -> bool:
        return True

    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        return f"mock macro for {jira_key}"

    async def health_check(self) -> None:
        pass


class JiraApiStub(JiraApiServiceInterface):
    """A complete stub that implements the JiraApiServiceInterface."""
    def __init__(self):
        self.mock = AsyncMock()

    async def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        return await self.mock.get_issue(issue_key, fields=fields)

    async def create_issue(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Optional[str]:
        return await self.mock.create_issue(task, parent_key, context)

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        return await self.mock.transition_issue(issue_key, target_status)

    async def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Dict[str, Any]:
        return await self.mock.prepare_jira_task_fields(task, parent_key, context)

    async def get_current_user_display_name(self) -> str:
        return await self.mock.get_current_user_display_name()

    async def search_issues_by_jql(
        self, jql_query: str, fields: str = "*all"
    ) -> List[Dict[str, Any]]:
        return await self.mock.search_issues_by_jql(jql_query, fields=fields)

    async def get_issue_type_name_by_id(self, type_id: str) -> Optional[str]:
        return await self.mock.get_issue_type_name_by_id(type_id)

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        return await self.mock.get_issue_status(issue_key)

    async def get_jira_issue(self, issue_key: str) -> Optional[JiraIssue]:
        return await self.mock.get_jira_issue(issue_key)

    async def assign_issue(self, issue_key: str, assignee_name: Optional[str]) -> bool:
        return await self.mock.assign_issue(issue_key, assignee_name)


# --- Pytest Fixtures ---


@pytest_asyncio.fixture
async def mock_confluence_api() -> ConfluenceApiStub:
    """Provides a stubbed ConfluenceService."""
    return ConfluenceApiStub()


@pytest_asyncio.fixture
async def mock_jira_api() -> JiraApiStub:
    """Provides a stubbed JiraApiService adhering to the interface."""
    return JiraApiStub()


@pytest_asyncio.fixture
async def issue_finder_service(
    mock_jira_api: JiraApiStub,
    mock_confluence_api: ConfluenceApiStub,
) -> IssueFinderService:
    """Provides an IssueFinderService instance with the correct mock dependency."""
    return IssueFinderService(jira_api=mock_jira_api, confluence_api=mock_confluence_api)


# --- Test Helper ---


def parse_jql_in_clause(jql_query: str) -> Optional[List[str]]:
    """Helper to parse issue keys from a JQL 'in' clause for assertions."""
    match = re.search(r"issue in \(([^)]+)\)", jql_query)
    if match:
        keys_str = match.group(1)
        keys = [key.strip() for key in keys_str.split(",") if key.strip()]
        return sorted(keys)
    return None


# --- Tests for find_issues_and_macros_on_page ---
@pytest.mark.asyncio
async def test_find_issues_and_macros_on_page_success(
    issue_finder_service, mock_jira_api
):
    html_content = (
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">PROJ-1</ac:parameter></ac:structured-macro>'
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">PROJ-2</ac:parameter></ac:structured-macro>'
    )
    # FIX: Set attributes on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.return_value = [
        {"key": "PROJ-1", "fields": {"summary": "Summary 1", "status": {"name": "Open", "statusCategory": {"key": "new"}}, "issuetype": {"name": "Task"}}},
        {"key": "PROJ-2", "fields": {"summary": "Summary 2", "status": {"name": "Done", "statusCategory": {"key": "done"}}, "issuetype": {"name": "Bug"}}},
    ]

    result = await issue_finder_service.find_issues_and_macros_on_page(html_content)

    assert len(result["fetched_issues_map"]) == 2
    # FIX: Call assertion on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.assert_awaited_once()
    called_args, called_kwargs = mock_jira_api.mock.search_issues_by_jql.await_args
    assert parse_jql_in_clause(called_args[0]) == sorted(["PROJ-1", "PROJ-2"])
    assert called_kwargs["fields"] == "summary,status,issuetype"


@pytest.mark.asyncio
async def test_find_issues_and_macros_on_page_no_macros(
    issue_finder_service, mock_jira_api
):
    await issue_finder_service.find_issues_and_macros_on_page("<p>No content</p>")
    # FIX: Call assertion on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_issues_and_macros_on_page_jira_api_error(
    issue_finder_service, mock_jira_api
):
    html_content = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">PROJ-ERR</ac:parameter></ac:structured-macro>'
    # FIX: Set attributes on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.side_effect = Exception("Jira API Down")

    with pytest.raises(Exception, match="Jira API Down"):
        await issue_finder_service.find_issues_and_macros_on_page(html_content)
    mock_jira_api.mock.search_issues_by_jql.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_issue_on_page_match_found(
    issue_finder_service, mock_confluence_api, mock_jira_api
):
    page_id = "page123"
    issue_type_map = {"Work Package": "10000"}
    html = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">WP-ABC</ac:parameter></ac:structured-macro>'
    mock_confluence_api.set_page_content(page_id, html)
    # FIX: Set attributes on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.return_value = [{"key": "WP-ABC", "fields": {"issuetype": {"name": "Work Package"}, "summary": "s", "status": {"name":"d", "statusCategory": {"key":"d"}}}}]
    mock_jira_api.mock.get_issue.return_value = {"key": "WP-ABC"}

    found_issue = await issue_finder_service.find_issue_on_page(page_id, issue_type_map)

    assert found_issue["key"] == "WP-ABC"
    # FIX: Call assertion on the internal mock object
    mock_jira_api.mock.get_issue.assert_awaited_once_with("WP-ABC", fields="key,issuetype,assignee,reporter")


@pytest.mark.asyncio
async def test_find_issue_on_page_no_match_found(
    issue_finder_service, mock_confluence_api, mock_jira_api
):
    page_id = "page123"
    issue_type_map = {"Epic": "10001"}
    html = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">TASK-1</ac:parameter></ac:structured-macro>'
    mock_confluence_api.set_page_content(page_id, html)
    # FIX: Set attributes on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.return_value = [{"key": "TASK-1", "fields": {"issuetype": {"name": "Task"}, "summary":"s", "status": {"name":"d", "statusCategory": {"key":"d"}}}}]

    found_issue = await issue_finder_service.find_issue_on_page(page_id, issue_type_map)

    assert found_issue is None
    mock_jira_api.mock.search_issues_by_jql.assert_awaited_once()
    mock_jira_api.mock.get_issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_issue_on_page_no_page_content(
    issue_finder_service, mock_confluence_api, mock_jira_api
):
    page_id = "page123"
    mock_confluence_api.set_page_content(page_id, None)
    await issue_finder_service.find_issue_on_page(page_id, {})
    # FIX: Call assertion on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_issue_on_page_empty_html_content(
    issue_finder_service, mock_confluence_api, mock_jira_api
):
    page_id = "page123"
    mock_confluence_api.set_page_content(page_id, "")
    await issue_finder_service.find_issue_on_page(page_id, {})
    # FIX: Call assertion on the internal mock object
    mock_jira_api.mock.search_issues_by_jql.assert_not_awaited()
