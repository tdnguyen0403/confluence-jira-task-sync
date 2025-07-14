import pytest
from typing import Any, Dict, Optional

# Import the service and its interfaces
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.config import config
from src.models.data_models import ConfluenceTask

# --- Stubs for Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    """A controlled stub for the Confluence service."""

    def __init__(self):
        self._page_content: Optional[str] = ""

    def get_page_by_id(
        self, page_id: str, expand: str = ""
    ) -> Optional[Dict[str, Any]]:
        if self._page_content is None:
            return None
        return {"body": {"storage": {"value": self._page_content}}}

    def set_page_content(self, html: Optional[str]):
        """Helper to set the page content for a test."""
        self._page_content = html

    # --- Methods not used in these tests, but required by the interface ---
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

    def update_page_content(self, page_id: str, title: str, body: str) -> bool:
        pass

    def get_user_details_by_username(self, username: str) -> dict:
        pass


class JiraServiceStub(JiraApiServiceInterface):
    """A controlled stub for the Jira service."""

    def __init__(self):
        self._issues = {}

    def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        return self._issues.get(issue_key)

    def add_issue(self, key: str, data: dict):
        """Helper to preload the stub with issue data."""
        self._issues[key] = data

    # --- Methods not used in these tests, but required by the interface ---
    def create_issue(
        self, task: ConfluenceTask, parent_key: str, request_user: str = "jira-user"
    ) -> str:
        pass

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        pass

    def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> list:
        pass

    def get_issue_type_name_by_id(self, type_id: str) -> str:
        pass

    def get_current_user_display_name(self) -> str:
        pass

    def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, request_user: str
    ) -> dict:
        pass


# --- Pytest Fixtures ---


@pytest.fixture
def confluence_stub():
    return ConfluenceServiceStub()


@pytest.fixture
def jira_stub():
    return JiraServiceStub()


@pytest.fixture
def issue_finder_service(confluence_stub, jira_stub):
    """Provides an IssueFinderService instance with stubbed dependencies."""
    return IssueFinderService(confluence_api=confluence_stub, jira_api=jira_stub)


# --- Tests for IssueFinderService ---


def test_find_issue_success(issue_finder_service, confluence_stub, jira_stub):
    """Test the happy path where a matching Jira macro is found."""
    # Arrange
    html = '<p><ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">WP-1</ac:parameter></ac:structured-macro></p>'
    confluence_stub.set_page_content(html)
    jira_stub.add_issue(
        "WP-1",
        {
            "key": "WP-1",
            "fields": {
                "issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"]}
            },
        },
    )

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is not None
    assert result["key"] == "WP-1"


def test_find_issue_no_content(issue_finder_service, confluence_stub):
    """Test that the service returns None if the page content is missing."""
    # Arrange
    confluence_stub.set_page_content(None)

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is None


def test_find_issue_no_macros(issue_finder_service, confluence_stub):
    """Test that the service returns None if the page has no Jira macros."""
    # Arrange
    confluence_stub.set_page_content("<p>Some text, but no macros.</p>")

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is None


def test_find_issue_wrong_type(issue_finder_service, confluence_stub, jira_stub):
    """Test that a macro is ignored if it's not a matching issue type."""
    # Arrange
    html = '<p><ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">TASK-123</ac:parameter></ac:structured-macro></p>'
    confluence_stub.set_page_content(html)
    jira_stub.add_issue(
        "TASK-123",
        {"key": "TASK-123", "fields": {"issuetype": {"id": "not_a_work_package_id"}}},
    )

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is None


def test_find_issue_jira_api_fails(issue_finder_service, confluence_stub, jira_stub):
    """Test that the service handles it gracefully if the Jira API returns None for an issue."""
    # Arrange
    html = '<p><ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">GHOST-1</ac:parameter></ac:structured-macro></p>'
    confluence_stub.set_page_content(html)
    # Don't add "GHOST-1" to the jira_stub, so it will return None

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is None


def test_find_issue_nested_macro_ignored(
    issue_finder_service, confluence_stub, jira_stub, monkeypatch
):
    """Test that a Jira macro is ignored if it's nested inside an aggregation macro."""
    # Arrange
    monkeypatch.setattr(config, "AGGREGATION_CONFLUENCE_MACRO", ["jira-issues"])
    html = (
        '<ac:structured-macro ac:name="jira-issues">'
        '  <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">WP-NESTED</ac:parameter></ac:structured-macro>'
        "</ac:structured-macro>"
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">WP-VALID</ac:parameter></ac:structured-macro>'
    )
    confluence_stub.set_page_content(html)
    jira_stub.add_issue(
        "WP-NESTED",
        {
            "key": "WP-NESTED",
            "fields": {
                "issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"]}
            },
        },
    )
    jira_stub.add_issue(
        "WP-VALID",
        {
            "key": "WP-VALID",
            "fields": {
                "issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"]}
            },
        },
    )

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is not None
    # It should find the valid, non-nested macro
    assert result["key"] == "WP-VALID"
