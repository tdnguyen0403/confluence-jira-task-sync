"""
Tests for the IssueFinderService using stubs for API dependencies.
"""

import pytest
from typing import Any, Dict, List, Optional

from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.config import config
from src.models.data_models import ConfluenceTask


# --- Stubs for API Services ---


class ConfluenceApiServiceStub(ConfluenceApiServiceInterface):
    """A stub for the Confluence API that returns predefined page content."""

    _page_content_html = ""

    def get_page_by_id(
        self, page_id: str, expand: str = ""
    ) -> Optional[Dict[str, Any]]:
        if self._page_content_html is None:
            return None
        return {"body": {"storage": {"value": self._page_content_html}}}

    # --- Implemented all abstract methods from the interface ---
    def get_all_descendants(self, page_id: str) -> List[Dict[str, Any]]:
        pass

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        pass

    def get_tasks_from_page(self, page_details: Dict[str, Any]) -> List[Dict[str, Any]]:
        pass

    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        pass

    def update_page_content(self, page_id: str, title: str, body: str) -> bool:
        pass

    def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> bool:
        pass

    def set_page_content(self, html: Optional[str]):
        self._page_content_html = html


class JiraApiServiceStub(JiraApiServiceInterface):
    """A stub for the Jira API that returns predefined issue details."""

    _issues = {}

    def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        return self._issues.get(issue_key)

    # --- Implemented all abstract methods from the interface ---
    def create_issue(
        self,
        task: ConfluenceTask,
        parent_key: str,
        request_user: Optional[str] = "jira-user",
    ) -> Optional[str]:
        pass

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        pass

    def search_issues_by_jql(
        self, jql_query: str, fields: str = "*all"
    ) -> List[Dict[str, Any]]:
        pass

    def get_issue_type_name_by_id(self, type_id: str) -> Optional[str]:
        pass

    def get_current_user_display_name(self) -> str:
        pass

    def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, request_user: str
    ) -> Dict[str, Any]:
        pass

    def add_issue(self, key: str, issue_data: dict):
        """Helper to preload the stub with issue data for a test."""
        self._issues[key] = issue_data


# --- Pytest Fixtures ---


@pytest.fixture
def confluence_api_stub() -> ConfluenceApiServiceStub:
    return ConfluenceApiServiceStub()


@pytest.fixture
def jira_api_stub() -> JiraApiServiceStub:
    return JiraApiServiceStub()


@pytest.fixture
def issue_finder_service(confluence_api_stub, jira_api_stub):
    return IssueFinderService(
        confluence_api=confluence_api_stub, jira_api=jira_api_stub
    )


# --- Pytest Test Functions ---


def test_find_issue_on_page_success(
    issue_finder_service, confluence_api_stub, jira_api_stub
):
    # Arrange
    confluence_api_stub.set_page_content(
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">JIRA-WP-1</ac:parameter></ac:structured-macro>'
    )
    # The service does a second call to get full details, so we stub that return value.
    full_issue_details = {
        "key": "JIRA-WP-1",
        "fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"]}},
    }
    jira_api_stub.add_issue("JIRA-WP-1", full_issue_details)

    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )

    # Assert
    assert result is not None
    assert result["key"] == "JIRA-WP-1"


def test_find_issue_on_page_no_content(issue_finder_service, confluence_api_stub):
    # Arrange
    confluence_api_stub.set_page_content(None)
    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )
    # Assert
    assert result is None


def test_find_issue_on_page_no_matching_issue_type(
    issue_finder_service, confluence_api_stub, jira_api_stub
):
    # Arrange
    confluence_api_stub.set_page_content(
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">JIRA-TASK-1</ac:parameter></ac:structured-macro>'
    )
    jira_api_stub.add_issue(
        "JIRA-TASK-1", {"key": "JIRA-TASK-1", "fields": {"issuetype": {"id": "10002"}}}
    )
    # Act
    result = issue_finder_service.find_issue_on_page(
        "page1", config.PARENT_ISSUES_TYPE_ID
    )
    # Assert
    assert result is None


def test_find_issue_on_page_nested_macro_ignored(
    issue_finder_service, confluence_api_stub, jira_api_stub, monkeypatch
):
    # Arrange
    monkeypatch.setattr(config, "AGGREGATION_CONFLUENCE_MACRO", {"jira-issues"})
    confluence_api_stub.set_page_content(
        '<ac:structured-macro ac:name="jira-issues">'
        '  <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">JIRA-NESTED</ac:parameter></ac:structured-macro>'
        "</ac:structured-macro>"
        '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">JIRA-VALID-WP</ac:parameter></ac:structured-macro>'
    )
    jira_api_stub.add_issue(
        "JIRA-VALID-WP",
        {
            "key": "JIRA-VALID-WP",
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
    assert result["key"] == "JIRA-VALID-WP"
