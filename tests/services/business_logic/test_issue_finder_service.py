import pytest
from unittest.mock import Mock

from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.services.orchestration.confluence_issue_updater_service import (
    ConfluenceIssueUpdaterService,
)
from src.exceptions import InvalidInputError
from src.config import config
from src.models.data_models import ConfluenceTask

# --- Stubs ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self):
        self._pages = {}
        self._descendants = {}
        self.mock = Mock()
        self._api = Mock()
        self._api._generate_jira_macro_html.side_effect = (
            lambda key: f"<p>New Macro for {key}</p>"
        )

    def get_page_id_from_url(self, url: str) -> str:
        self.mock.get_page_id_from_url(url)
        return "root_page_id" if url != "invalid_url" else None

    def get_all_descendants(self, page_id: str) -> list:
        self.mock.get_all_descendants(page_id)
        return self._descendants.get(page_id, [])

    def get_page_by_id(self, page_id: str, **kwargs) -> dict:
        self.mock.get_page_by_id(page_id, **kwargs)
        return self._pages.get(page_id)

    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool:
        self.mock.update_page_content(page_id, new_title, new_body)
        return True

    def get_tasks_from_page(self, page_details: dict) -> list:
        pass

    def update_page_with_jira_links(self, page_id: str, mappings: list) -> None:
        pass

    def create_page(self, **kwargs) -> dict:
        pass

    def get_user_details_by_username(self, username: str) -> dict:
        pass

    def add_page(self, page_id, page_data):
        self._pages[page_id] = page_data

    def add_descendants(self, parent_id, descendant_ids):
        self._descendants[parent_id] = descendant_ids


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self.mock = Mock()
        self._issues = {}
        self._issue_type_names = {}
        self._jql_results = {}

    def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        self.mock.get_issue(issue_key, fields)
        return self._issues.get(issue_key)

    def get_issue_type_name_by_id(self, type_id: str) -> str:
        self.mock.get_issue_type_name_by_id(type_id)
        return self._issue_type_names.get(type_id)

    def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> list:
        self.mock.search_issues_by_jql(jql_query, fields=fields)
        return self._jql_results.get(jql_query, [])

    def create_issue(
        self, task: ConfluenceTask, parent_key: str, request_user: str = "jira-user"
    ) -> str:
        pass

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        pass

    def get_current_user_display_name(self) -> str:
        pass

    def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, request_user: str
    ) -> dict:
        pass

    def add_issue(self, key, issue_data):
        self._issues[key] = issue_data

    def add_issue_type_name(self, type_id, name):
        self._issue_type_names[type_id] = name

    def add_jql_result(self, jql, result):
        self._jql_results[jql] = result


# --- Fixtures ---


@pytest.fixture
def confluence_stub():
    return ConfluenceServiceStub()


@pytest.fixture
def jira_stub():
    return JiraServiceStub()


@pytest.fixture
def updater_service(confluence_stub, jira_stub, monkeypatch):
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10200")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "11001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10100")
    return ConfluenceIssueUpdaterService(confluence_stub, jira_stub)


# --- Tests ---


def test_get_relevant_jira_issues_success(updater_service, jira_stub):
    """Tests that the JQL query is correctly formed and issues are filtered."""
    # Arrange
    jira_stub.add_issue_type_name("10100", "Work Package")
    jql = (
        "issuetype in (\"Work Package\") AND issue in relation('PROJ-ROOT', '', 'all')"
    )
    jira_stub.add_jql_result(
        jql,
        [
            {"fields": {"issuetype": {"id": "10100"}}},
            {"fields": {"issuetype": {"id": "99999"}}},  # Should be filtered out
        ],
    )

    # Act
    issues = updater_service._get_relevant_jira_issues_under_root(
        "PROJ-ROOT", {"10100"}
    )

    # Assert
    assert len(issues) == 1
    assert issues[0]["fields"]["issuetype"]["id"] == "10100"
    jira_stub.mock.search_issues_by_jql.assert_called_once_with(
        jql, fields="key,issuetype,summary"
    )


def test_find_best_match_exact(updater_service):
    """Tests finding a replacement issue with an exact summary match."""
    old = {"fields": {"issuetype": {"id": "10100"}, "summary": "Exact Summary"}}
    candidates = [
        {
            "key": "NEW-1",
            "fields": {"issuetype": {"id": "10100"}, "summary": "Exact Summary"},
        }
    ]
    match = updater_service._find_best_new_issue_match(old, candidates, 0.7)
    assert match["key"] == "NEW-1"


def test_find_best_match_fuzzy(updater_service, mocker):
    """Tests finding a replacement with a high fuzzy summary match score."""
    mocker.patch("difflib.SequenceMatcher.ratio", return_value=0.9)  # High similarity
    old = {"fields": {"issuetype": {"id": "10100"}, "summary": "Original"}}
    candidates = [
        {"key": "NEW-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Similar"}}
    ]
    match = updater_service._find_best_new_issue_match(old, candidates, 0.7)
    assert match["key"] == "NEW-1"


def test_find_best_match_no_type_match(updater_service):
    """Tests that no match is found if issue types differ."""
    old = {"fields": {"issuetype": {"id": "10100"}, "summary": "Summary"}}
    candidates = [
        {"key": "NEW-1", "fields": {"issuetype": {"id": "99999"}, "summary": "Summary"}}
    ]
    match = updater_service._find_best_new_issue_match(old, candidates, 0.7)
    assert match is None


def test_find_and_replace_macros_success(updater_service, confluence_stub, jira_stub):
    """Tests that a Jira macro on a page is successfully found and replaced."""
    # Arrange
    html = '<p><ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-1</ac:parameter></ac:structured-macro></p>'
    jira_stub.add_issue(
        "OLD-1",
        {
            "key": "OLD-1",
            "fields": {"issuetype": {"id": "10100"}, "summary": "Old Summary"},
        },
    )
    candidates = [
        {
            "key": "NEW-1",
            "fields": {"issuetype": {"id": "10100"}, "summary": "Old Summary"},
        }
    ]

    # Act
    modified_html, did_modify = updater_service._find_and_replace_jira_macros_on_page(
        {}, html, candidates, {"10100"}
    )

    # Assert
    assert did_modify is True
    assert "New Macro for NEW-1" in modified_html


def test_update_hierarchy_success(updater_service, confluence_stub, mocker):
    """Tests the main success path of the high-level update method."""
    # Arrange
    confluence_stub.add_page(
        "root_page_id",
        {
            "id": "root_page_id",
            "title": "Root",
            "body": {"storage": {"value": "content"}},
        },
    )
    mocker.patch.object(
        updater_service,
        "_get_relevant_jira_issues_under_root",
        return_value=[{"key": "NEW-1"}],
    )
    mocker.patch.object(
        updater_service,
        "_find_and_replace_jira_macros_on_page",
        return_value=("new html", True),
    )

    # Act
    results = updater_service.update_confluence_hierarchy_with_new_jira_project(
        "http://ok", "PROJ-ROOT"
    )

    # Assert
    confluence_stub.mock.update_page_content.assert_called_once_with(
        "root_page_id", "Root", "new html"
    )
    assert len(results) == 1
    assert results[0]["page_id"] == "root_page_id"


def test_update_hierarchy_invalid_url(updater_service):
    """Tests that an InvalidInputError is raised for a bad URL."""
    with pytest.raises(InvalidInputError):
        updater_service.update_confluence_hierarchy_with_new_jira_project(
            "invalid_url", "PROJ-ROOT"
        )


def test_update_hierarchy_no_candidates(updater_service, confluence_stub, mocker):
    """Tests that the process exits early if no candidate issues are found in Jira."""
    # Arrange
    mocker.patch.object(
        updater_service, "_get_relevant_jira_issues_under_root", return_value=[]
    )  # No candidates

    # Act
    results = updater_service.update_confluence_hierarchy_with_new_jira_project(
        "http://ok", "PROJ-ROOT"
    )

    # Assert
    assert results == []
    confluence_stub.mock.get_page_by_id.assert_not_called()  # Should not proceed to process pages
