import pytest
from bs4 import BeautifulSoup

# Import the class to be tested and its dependencies
from src.scripts.generate_confluence_tree import ConfluenceTreeGenerator
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface
from src.config import config
from src.models.data_models import ConfluenceTask

# --- Stubs for Service Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self):
        self.created_pages = []
        self._user_details = {}

    def get_user_details_by_username(self, username: str) -> dict:
        return self._user_details.get(username)

    def create_page(self, space: str, title: str, body: str, parent_id: str) -> dict:
        page_data = {
            "space": space,
            "title": title,
            "body": body,
            "parent_id": parent_id,
        }
        self.created_pages.append(page_data)
        return {
            "id": f"new_page_{len(self.created_pages)}",
            "_links": {"webui": f"/new/page/url/{len(self.created_pages)}"},
        }

    # --- Methods not used in these tests, but required by the interface ---
    def get_page_by_id(self, page_id: str, **kwargs) -> dict:
        pass

    def get_all_descendants(self, page_id: str) -> list:
        pass

    def get_page_id_from_url(self, url: str) -> str:
        pass

    def get_tasks_from_page(self, page_details: dict) -> list:
        pass

    def update_page_with_jira_links(self, page_id: str, mappings: list) -> None:
        pass

    def update_page_content(self, page_id: str, title: str, body: str) -> bool:
        pass

    # --- Helper methods for test setup ---
    def add_user(self, username, details):
        self._user_details[username] = details


class JiraServiceStub(JiraApiServiceInterface):
    # This service is not used by the generator, so we only need to implement the interface
    def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        pass

    def get_issue_type_name_by_id(self, type_id: str) -> str:
        pass

    def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> list:
        pass

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


class IssueFinderServiceStub(IssueFinderServiceInterface):
    # This service is not used by the generator, so we only need to implement the interface
    def find_issue_on_page(self, page_id: str, issue_type_map: dict) -> dict:
        pass


# --- Pytest Fixtures ---


@pytest.fixture
def confluence_stub():
    stub = ConfluenceServiceStub()
    # Pre-populate with data needed for initialization
    stub.add_user("testuser", {"accountId": "test_account_id"})
    return stub


@pytest.fixture
def jira_stub():
    return JiraServiceStub()


@pytest.fixture
def issue_finder_stub():
    return IssueFinderServiceStub()


@pytest.fixture
def tree_generator(confluence_stub, jira_stub, issue_finder_stub, monkeypatch):
    """Provides a fully configured ConfluenceTreeGenerator instance for tests."""
    # Use monkeypatch to set config values
    monkeypatch.setattr(config, "BASE_PARENT_CONFLUENCE_PAGE_ID", "base_parent_id")
    monkeypatch.setattr(config, "CONFLUENCE_SPACE_KEY", "TESTSPACE")
    monkeypatch.setattr(config, "ASSIGNEE_USERNAME_FOR_GENERATED_TASKS", "testuser")
    monkeypatch.setattr(
        config, "TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE", ["WP-1", "WP-2"]
    )
    monkeypatch.setattr(config, "DEFAULT_DUE_DATE", "2025-01-01")

    return ConfluenceTreeGenerator(
        confluence_service=confluence_stub,
        jira_service=jira_stub,
        issue_finder_service=issue_finder_stub,
        base_parent_page_id=config.BASE_PARENT_CONFLUENCE_PAGE_ID,
        confluence_space_key=config.CONFLUENCE_SPACE_KEY,
        assignee_username=config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS,
        test_work_package_keys=config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE,
        max_depth=1,
        tasks_per_page=1,
    )


# --- Pytest Test Functions ---


def test_init(tree_generator):
    """Verify that the generator initializes its attributes correctly."""
    assert tree_generator.base_parent_page_id == "base_parent_id"
    assert tree_generator.assignee_account_id == "test_account_id"


def test_generate_page_hierarchy_single_page(tree_generator, confluence_stub, mocker):
    """Test generating a single page with tasks and a WP link."""
    # Arrange
    # Mock datetime to control timestamps in page titles and task summaries
    mock_datetime = mocker.patch("src.scripts.generate_confluence_tree.datetime")
    mock_datetime.now.return_value.strftime.return_value = "20250705100000"
    # Mock uuid to control the macro IDs
    mocker.patch("src.scripts.generate_confluence_tree.uuid.uuid4").hex.side_effect = [
        "uuid1",
        "uuid2",
        "uuid3",
    ]

    # Act
    results = tree_generator.generate_page_hierarchy(parent_page_id="base_parent_id")

    # Assert page creation
    assert len(confluence_stub.created_pages) == 1
    created_page = confluence_stub.created_pages[0]
    assert created_page["space"] == "TESTSPACE"
    assert created_page["parent_id"] == "base_parent_id"
    assert created_page["title"] == "Test Page (Depth 0-0) 20250705100000"

    # Assert content of the created page
    soup = BeautifulSoup(created_page["body"], "html.parser")

    # Check Jira Macro
    jira_macro = soup.find("ac:structured-macro", {"ac:name": "jira"})
    assert jira_macro is not None
    assert jira_macro.find("ac:parameter", {"ac:name": "key"}).text == "WP-1"

    # Check Task
    task = soup.find("ac:task")
    assert task is not None
    assert "Generated Task 0 for WP-1" in task.find("ac:task-body").text
    assert task.find("ac:task-assignee")["ac:account-id"] == "test_account_id"
    assert task.find("time")["datetime"] == "2025-01-01"

    # Assert final results summary
    assert len(results) == 1
    assert results[0]["url"] == "/new/page/url/1"
    assert results[0]["linked_work_package"] == "WP-1"


def test_generate_page_hierarchy_max_depth_zero(tree_generator, confluence_stub):
    """Test that no pages are generated if max_depth is 0."""
    # Arrange
    tree_generator.max_depth = 0

    # Act
    results = tree_generator.generate_page_hierarchy(parent_page_id="base_parent_id")

    # Assert
    assert len(results) == 0
    assert len(confluence_stub.created_pages) == 0
