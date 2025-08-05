import re  # Import regex module for parsing
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from src.api.safe_jira_api import SafeJiraApi
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.models.data_models import JiraIssue

# Import the service to be tested and its dependencies
from src.services.business_logic.issue_finder_service import IssueFinderService

# --- Stubs for Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self):
        self._page_content = {}

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        pass

    async def get_all_descendants(self, page_id: str) -> List[str]:
        pass

    async def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        content = self._page_content.get(page_id)
        if content:
            return {"id": page_id, "body": {"storage": {"value": content}}}
        return None

    async def get_tasks_from_page(self, page_details: Dict[str, Any]) -> List[Any]:
        pass

    async def update_page_with_jira_links(
        self, page_id: str, jira_task_mappings: List[Dict[str, str]]
    ) -> None:
        pass

    async def update_page_content(
        self, page_id: str, title: str, html_content: str
    ) -> bool:
        pass

    async def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        pass

    async def get_user_details_by_username(
        self, username: str
    ) -> Optional[Dict[str, Any]]:
        pass

    def set_page_content(self, page_id: str, content: str):
        self._page_content[page_id] = content

class SafeJiraApiStub(SafeJiraApi):
    def __init__(self):
        # We need AsyncMock for methods that are awaited in IssueFinderService
        self.get_issue = AsyncMock()
        self.search_issues = AsyncMock()
        self.get_current_user = AsyncMock()
        self.create_issue = AsyncMock()
        self.transition_issue = AsyncMock()
        self.get_issue_type_details_by_id = AsyncMock()
        self.update_issue_description = AsyncMock()

    # IssueFinderService uses get_issue and search_issues directly from SafeJiraApi
    # So we'll set return values on these AsyncMocks.


# --- Pytest Fixtures ---


@pytest_asyncio.fixture
async def mock_confluence_service():
    """Provides a stubbed ConfluenceService."""
    return ConfluenceServiceStub()


@pytest_asyncio.fixture
async def mock_jira_api():
    """Provides a stubbed SafeJiraApi with AsyncMocks."""
    return SafeJiraApiStub()


@pytest_asyncio.fixture
async def issue_finder_service(mock_jira_api):
    """Provides an IssueFinderService instance with mocked dependencies."""
    return IssueFinderService(jira_api=mock_jira_api)


# --- Helper for parsing JQL ---
def parse_jql_in_clause(jql_query: str) -> Optional[List[str]]:
    """Parses a JQL query string to extract issue keys from an 'issue in (...)' clause."""
    match = re.search(r"issue in \(([^)]+)\)", jql_query)
    if match:
        keys_str = match.group(1)
        # Split by comma and strip whitespace, then filter out any empty strings
        keys = [key.strip() for key in keys_str.split(",") if key.strip()]
        return sorted(keys)  # Return sorted keys for consistent comparison
    return None


# --- Tests for find_issues_and_macros_on_page ---


@pytest.mark.asyncio
async def test_find_issues_and_macros_on_page_success(
    issue_finder_service, mock_jira_api
):
    html_content = """
    <p>Some text.</p>
    <ac:structured-macro ac:name="jira" ac:schema-version="1">
        <ac:parameter ac:name="key">PROJ-1</ac:parameter>
    </ac:structured-macro>
    <p>More text.</p>
    <ac:structured-macro ac:name="jira" ac:schema-version="1">
        <ac:parameter ac:name="key">PROJ-2</ac:parameter>
    </ac:structured-macro>
    """
    # Mock search_issues to return data for PROJ-1 and PROJ-2
    mock_jira_api.search_issues.return_value = {
        "issues": [
            {
                "key": "PROJ-1",
                "fields": {
                    "summary": "Summary 1",
                    "status": {"name": "Open", "statusCategory": {"key": "new"}},
                    "issuetype": {"name": "Task"},
                },
            },
            {
                "key": "PROJ-2",
                "fields": {
                    "summary": "Summary 2",
                    "status": {"name": "Done", "statusCategory": {"key": "done"}},
                    "issuetype": {"name": "Bug"},
                },
            },
        ]
    }

    result = await issue_finder_service.find_issues_and_macros_on_page(html_content)

    assert "jira_macros" in result
    assert "fetched_issues_map" in result
    assert len(result["jira_macros"]) == 2
    assert len(result["fetched_issues_map"]) == 2
    assert "PROJ-1" in result["fetched_issues_map"]
    assert "PROJ-2" in result["fetched_issues_map"]
    assert isinstance(result["fetched_issues_map"]["PROJ-1"], JiraIssue)
    assert result["fetched_issues_map"]["PROJ-1"].summary == "Summary 1"
    assert result["fetched_issues_map"]["PROJ-1"].status.name == "Open"
    assert result["fetched_issues_map"]["PROJ-1"].issue_type == "Task"

    # Assert search_issues was called with the correct sorted issue keys
    mock_jira_api.search_issues.assert_awaited_once()
    called_args, called_kwargs = (
        mock_jira_api.search_issues.await_args.args,
        mock_jira_api.search_issues.await_args.kwargs,
    )

    expected_issue_keys = sorted(["PROJ-1", "PROJ-2"])
    actual_issue_keys = parse_jql_in_clause(called_args[0])

    assert actual_issue_keys == expected_issue_keys
    assert called_kwargs["fields"] == ["summary", "status", "issuetype"]


@pytest.mark.asyncio
async def test_find_issues_and_macros_on_page_no_macros(
    issue_finder_service, mock_jira_api
):
    html_content = "<p>No Jira macros here.</p>"
    mock_jira_api.search_issues.return_value = {"issues": []}

    result = await issue_finder_service.find_issues_and_macros_on_page(html_content)

    assert len(result["jira_macros"]) == 0
    assert len(result["fetched_issues_map"]) == 0
    mock_jira_api.search_issues.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_issues_and_macros_on_page_jira_api_error(
    issue_finder_service, mock_jira_api
):
    html_content = """
    <ac:structured-macro ac:name="jira" ac:schema-version="1">
        <ac:parameter ac:name="key">PROJ-ERR</ac:parameter>
    </ac:structured-macro>
    """
    mock_jira_api.search_issues.side_effect = Exception("Jira API Down")

    with pytest.raises(Exception, match="Jira API Down"):
        await issue_finder_service.find_issues_and_macros_on_page(html_content)

    mock_jira_api.search_issues.assert_awaited_once()


# --- Tests for find_issue_on_page ---


@pytest.mark.asyncio
async def test_find_issue_on_page_match_found(
    issue_finder_service, mock_confluence_service, mock_jira_api
):
    page_id = "page123"
    issue_type_map = {"Work Package": "10000"}
    html_content = """
    <ac:structured-macro ac:name="jira" ac:schema-version="1">
        <ac:parameter ac:name="key">WP-ABC</ac:parameter>
    </ac:structured-macro>
    <ac:structured-macro ac:name="jira" ac:schema-version="1">
        <ac:parameter ac:name="key">TASK-1</ac:parameter>
    </ac:structured-macro>
    """
    mock_confluence_service.set_page_content(page_id, html_content)

    # Mock search_issues for find_issues_and_macros_on_page (internal call)
    mock_jira_api.search_issues.return_value = {
        "issues": [
            {
                "key": "WP-ABC",
                "fields": {
                    "summary": "Work Package Summary",
                    "status": {"name": "Open", "statusCategory": {"key": "new"}},
                    "issuetype": {"name": "Work Package"},
                },
            },
            {
                "key": "TASK-1",
                "fields": {
                    "summary": "Task Summary",
                    "status": {
                        "name": "In Progress",
                        "statusCategory": {"key": "indeterminate"},
                    },
                    "issuetype": {"name": "Task"},
                },
            },
        ]
    }
    # Mock get_issue for the final fetch of the matching issue
    mock_jira_api.get_issue.return_value = {
        "key": "WP-ABC",
        "fields": {
            "issuetype": {"name": "Work Package"},
            "assignee": {"name": "jdoe"},
            "reporter": {"name": "jdoe"},
            "summary": "Work Package Summary",
        },
    }

    found_issue = await issue_finder_service.find_issue_on_page(
        page_id, issue_type_map, mock_confluence_service
    )

    assert found_issue is not None
    assert found_issue["key"] == "WP-ABC"
    assert found_issue["fields"]["issuetype"]["name"] == "Work Package"

    # Assert search_issues was called with the correct sorted issue keys
    mock_jira_api.search_issues.assert_awaited_once()
    called_args, called_kwargs = (
        mock_jira_api.search_issues.await_args.args,
        mock_jira_api.search_issues.await_args.kwargs,
    )

    expected_issue_keys = sorted(["WP-ABC", "TASK-1"])
    actual_issue_keys = parse_jql_in_clause(called_args[0])

    assert actual_issue_keys == expected_issue_keys
    assert called_kwargs["fields"] == ["summary", "status", "issuetype"]

    mock_jira_api.get_issue.assert_awaited_once_with(
        "WP-ABC", fields=["key", "issuetype", "assignee", "reporter"]
    )


@pytest.mark.asyncio
async def test_find_issue_on_page_no_match_found(
    issue_finder_service, mock_confluence_service, mock_jira_api
):
    page_id = "page123"
    issue_type_map = {"Epic": "10001"}  # Looking for Epic, but only Task exists
    html_content = """
    <ac:structured-macro ac:name="jira" ac:schema-version="1">
        <ac:parameter ac:name="key">TASK-1</ac:parameter>
    </ac:structured-macro>
    """
    mock_confluence_service.set_page_content(page_id, html_content)
    mock_jira_api.search_issues.return_value = {
        "issues": [
            {
                "key": "TASK-1",
                "fields": {
                    "summary": "Task Summary",
                    "status": {
                        "name": "In Progress",
                        "statusCategory": {"key": "indeterminate"},
                    },
                    "issuetype": {"name": "Task"},
                },
            }
        ]
    }
    mock_jira_api.get_issue.return_value = (
        None  # No issue will be fetched as no match is found
    )

    found_issue = await issue_finder_service.find_issue_on_page(
        page_id, issue_type_map, mock_confluence_service
    )

    assert found_issue is None
    # Assert search_issues was called with the correct sorted issue keys
    mock_jira_api.search_issues.assert_awaited_once()
    called_args, called_kwargs = (
        mock_jira_api.search_issues.await_args.args,
        mock_jira_api.search_issues.await_args.kwargs,
    )

    expected_issue_keys = sorted(["TASK-1"])
    actual_issue_keys = parse_jql_in_clause(called_args[0])

    assert actual_issue_keys == expected_issue_keys
    assert called_kwargs["fields"] == ["summary", "status", "issuetype"]

    mock_jira_api.get_issue.assert_not_awaited()  # get_issue should not be called if no match


@pytest.mark.asyncio
async def test_find_issue_on_page_no_page_content(
    issue_finder_service, mock_confluence_service, mock_jira_api
):
    page_id = "non_existent_page"
    issue_type_map = {"Work Package": "10000"}
    mock_confluence_service.set_page_content(page_id, None)  # Simulate no content

    found_issue = await issue_finder_service.find_issue_on_page(
        page_id, issue_type_map, mock_confluence_service
    )

    assert found_issue is None
    mock_jira_api.search_issues.assert_not_awaited()  # No search if no page content
    mock_jira_api.get_issue.assert_not_awaited()  # No get if no page content


@pytest.mark.asyncio
async def test_find_issue_on_page_empty_html_content(
    issue_finder_service, mock_confluence_service, mock_jira_api
):
    page_id = "empty_content_page"
    issue_type_map = {"Work Package": "10000"}
    mock_confluence_service.set_page_content(page_id, "")  # Simulate empty content

    found_issue = await issue_finder_service.find_issue_on_page(
        page_id, issue_type_map, mock_confluence_service
    )

    assert found_issue is None
    mock_jira_api.search_issues.assert_not_awaited()
    mock_jira_api.get_issue.assert_not_awaited()
