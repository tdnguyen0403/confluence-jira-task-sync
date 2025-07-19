"""
Tests for the SyncTaskOrchestrator using stubs for service dependencies.
"""

import pytest
import pytest_asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock
import logging

from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)
from src.models.data_models import (
    ConfluenceTask,
    UndoRequestItem,
    SyncContext,
    JiraIssueStatus,
)
from src.exceptions import InvalidInputError
from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface

# Configure logging for the test file itself
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Test Data Fixtures (Raw Dictionary format matching expected snake_case JSON) ---
@pytest.fixture
def sample_synced_task_raw_json():
    """A raw dictionary representing a synced task, exactly as it would appear in snake_case JSON input."""
    return {
        "status_text": "Success",
        "new_jira_task_key": "SFSEA-1850",
        "linked_work_package": "SFSEA-1825",
        "request_user": "tdnguyen",
        "confluence_page_id": "435680347",
        "confluence_page_title": "Simple Page Test",
        "confluence_page_url": "/spaces/EUDEMHTM0589/pages/435680347/Simple+Page+Test",
        "confluence_task_id": "10",
        "task_summary": "Test long description",
        "status": "incomplete",
        "assignee_name": "j2t-automator",
        "due_date": None,
        "original_page_version": 213,
        "original_page_version_by": "Jira-to-Teamspace Automator",
        "original_page_version_when": "2025-07-19T13:07:22.000+02:00",
        "context": "JIRA_KEY_CONTEXT::SFSEA-1825",
    }


@pytest.fixture
def sample_completed_synced_task_raw_json():
    """A raw dictionary representing a completed synced task, for a second entry in snake_case JSON input."""
    return {
        "status_text": "Success",
        "new_jira_task_key": "SFSEA-1851",
        "linked_work_package": "SFSEA-1825",
        "request_user": "tdnguyen",
        "confluence_page_id": "435680347",
        "confluence_page_title": "Simple Page Test",
        "confluence_page_url": "/spaces/EUDEMHTM0589/pages/435680347/Simple+Page+Test",
        "confluence_task_id": "11",
        "task_summary": "Another completed task",
        "status": "complete",
        "assignee_name": "j2t-automator",
        "due_date": None,
        "original_page_version": 213,
        "original_page_version_by": "Jira-to-Teamspace Automator",
        "original_page_version_when": "2025-07-19T13:08:00.000+02:00",
        "context": "JIRA_KEY_CONTEXT::SFSEA-1825",
    }


# Pydantic model instances derived from the raw JSON dictionaries for type-safe access in tests
@pytest.fixture
def sample_synced_item(sample_synced_task_raw_json):
    """A Pydantic UndoRequestItem instance for a synced task."""
    item = UndoRequestItem(**sample_synced_task_raw_json)
    logger.info(
        f"Fixture sample_synced_item created. new_jira_task_key: {item.new_jira_task_key}"
    )
    return item


@pytest.fixture
def sample_completed_item(sample_completed_synced_task_raw_json):
    """A Pydantic UndoRequestItem instance for a completed synced task."""
    item = UndoRequestItem(**sample_completed_synced_task_raw_json)
    logger.info(
        f"Fixture sample_completed_item created. new_jira_task_key: {item.new_jira_task_key}"
    )
    return item


@pytest.fixture
def sync_context():
    return SyncContext(request_user="test_undo_orchestrator", days_to_due_date=0)


# --- Stubs for Service Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self, tasks_on_page: List[ConfluenceTask], initial_html: str = ""):
        self._tasks_on_page = tasks_on_page
        self._page_content = initial_html
        self.page_updated_count = 0
        self._page_details = {
            "435680347": {  # Use the actual page ID from your JSON
                "id": "435680347",
                "title": "Simple Page Test",
                "body": {"storage": {"value": initial_html}},
                "version": {
                    "number": 214
                },  # Assuming current version is 214 if original was 213
            }
        }

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        return "435680347" if "Simple+Page+Test" in url else None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        return []

    async def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        if page_id in self._page_details:
            if "version" in kwargs:
                # If requesting the original version
                if (
                    kwargs["version"] == 213
                ):  # Use the original_page_version from your JSON
                    return {
                        "id": page_id,
                        "title": self._page_details[page_id]["title"],
                        "body": {
                            "storage": {
                                "value": self._page_details[page_id]["body"]["storage"][
                                    "value"
                                ]
                            }
                        },
                        "version": {"number": kwargs["version"]},
                    }
            return self._page_details[page_id]
        return None

    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        return self._tasks_on_page

    async def update_page_content(
        self, page_id: str, new_title: str, new_body: str
    ) -> bool:
        self._page_content = new_body
        if page_id in self._page_details:
            self._page_details[page_id]["body"]["storage"]["value"] = new_body
            self._page_details[page_id]["version"]["number"] += 1
        self.page_updated_count += 1
        return True

    async def update_page_with_jira_links(self, page_id: str, mappings: list) -> None:
        pass

    async def create_page(self, **kwargs) -> dict:
        return {}

    async def get_user_details_by_username(self, username: str) -> dict:
        return {}

    @property
    def jira_macro_server_name(self) -> str:
        return "Mock Jira Server"

    @property
    def jira_macro_server_id(self) -> str:
        return "mock-server-id"

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        return f'<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">{jira_key}</ac:parameter></ac:structured-macro>'


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self.transitioned_issues = {}
        self._issue_statuses = {}
        self._issue_types = {}
        self._search_issues_results = {}

    async def create_issue(
        self, task: ConfluenceTask, parent_key: str, context: SyncContext
    ) -> Optional[str]:
        pass

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        logger.info(
            f"JiraServiceStub: Transitioning issue {issue_key} to {target_status}"
        )
        self.transitioned_issues[issue_key] = target_status
        return True

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        status_data = self._issue_statuses.get(issue_key)
        if status_data:
            return JiraIssueStatus(
                name=status_data["name"], category=status_data["category"]
            )
        return None

    def set_issue_status(self, issue_key: str, name: str, category: str):
        self._issue_statuses[issue_key] = {"name": name, "category": category}

    async def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        return {"key": issue_key, "fields": {"summary": "Issue Summary"}}

    async def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, context: SyncContext
    ) -> dict:
        pass

    async def get_current_user_display_name(self) -> str:
        return "Stubbed User"

    async def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> list:
        return self._search_issues_results.get(jql_query, [])

    async def get_issue_type_name_by_id(self, type_id: str) -> str:
        return self._issue_types.get(type_id, {}).get("name", f"Type-{type_id}")

    async def get_jira_issue(self, issue_key: str):
        pass

    async def get_issue_type_details_by_id(
        self, type_id: str
    ) -> Optional[Dict[str, Any]]:
        return self._issue_types.get(type_id)

    def add_issue_type(self, type_id: str, name: str):
        self._issue_types[type_id] = {"id": type_id, "name": name}

    async def search_issues(
        self, jql_query: str, fields: str = "*all", **kwargs
    ) -> Dict[str, Any]:
        return {"issues": self._search_issues_results.get(jql_query, [])}

    def add_search_result(self, jql_query: str, issues: List[Dict[str, Any]]):
        self._search_issues_results[jql_query] = issues


class IssueFinderServiceStub(IssueFinderServiceInterface):
    def __init__(self):
        self.mock = AsyncMock()

    async def find_issue_on_page(
        self, page_id: str, issue_type_map: Dict[str, str], confluence_api_service: Any
    ) -> Optional[Dict[str, Any]]:
        await self.mock.find_issue_on_page(
            page_id, issue_type_map, confluence_api_service
        )
        return None

    async def find_issues_and_macros_on_page(self, page_html: str) -> Dict[str, Any]:
        await self.mock.find_issues_and_macros_on_page(page_html)
        return {"jira_macros": [], "fetched_issues_map": {}}


# --- Pytest Fixtures ---


@pytest_asyncio.fixture
async def confluence_undo_stub(sample_synced_item, sample_completed_item):
    # Initial page content with Jira macros
    initial_html = (
        f"<p>Task 1: {sample_synced_item.task_summary} "
        f'<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="abcd">'
        f'<ac:parameter ac:name="key">{sample_synced_item.new_jira_task_key}</ac:parameter>'
        f'<ac:parameter ac:name="server">ConfluenceJiraServer</ac:parameter>'
        f'<ac:parameter ac:name="serverId">confluence-jira-id</ac:parameter>'
        f"</ac:structured-macro></p>"
        f"<p>Task 2: {sample_completed_item.task_summary} "
        f'<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="efgh">'
        f'<ac:parameter ac:name="key">{sample_completed_item.new_jira_task_key}</ac:parameter>'
        f'<ac:parameter ac:name="server">ConfluenceJiraServer</ac:parameter>'
        f'<ac:parameter ac:name="serverId">confluence-jira-id</ac:parameter>'
        f"</ac:structured-macro></p>"
        f"<p>Some other content.</p>"
    )

    # These ConfluenceTask objects are for the stub's internal `_tasks_on_page` list.
    dummy_confluence_task_1 = ConfluenceTask(
        confluence_page_id=sample_synced_item.confluence_page_id,
        confluence_page_title=sample_synced_item.confluence_page_title,
        confluence_page_url=sample_synced_item.confluence_page_url,
        confluence_task_id=sample_synced_item.confluence_task_id,
        task_summary=sample_synced_item.task_summary,
        status=sample_synced_item.status,
        assignee_name=sample_synced_item.assignee_name,
        due_date=sample_synced_item.due_date,
        original_page_version=sample_synced_item.original_page_version,
        original_page_version_by=sample_synced_item.original_page_version_by,
        original_page_version_when=sample_synced_item.original_page_version_when,
        context=sample_synced_item.context,
    )
    dummy_confluence_task_2 = ConfluenceTask(
        confluence_page_id=sample_completed_item.confluence_page_id,
        confluence_page_title=sample_completed_item.confluence_page_title,
        confluence_page_url=sample_completed_item.confluence_page_url,
        confluence_task_id=sample_completed_item.confluence_task_id,
        task_summary=sample_completed_item.task_summary,
        status=sample_completed_item.status,
        assignee_name=sample_completed_item.assignee_name,
        due_date=sample_completed_item.due_date,
        original_page_version=sample_completed_item.original_page_version,
        original_page_version_by=sample_completed_item.original_page_version_by,
        original_page_version_when=sample_completed_item.original_page_version_when,
        context=sample_completed_item.context,
    )
    return ConfluenceServiceStub(
        tasks_on_page=[dummy_confluence_task_1, dummy_confluence_task_2],
        initial_html=initial_html,
    )


@pytest_asyncio.fixture
async def jira_undo_stub():
    return JiraServiceStub()


@pytest_asyncio.fixture
async def issue_finder_undo_stub():
    return IssueFinderServiceStub()


@pytest_asyncio.fixture
async def undo_orchestrator(
    confluence_undo_stub, jira_undo_stub, issue_finder_undo_stub
):
    return UndoSyncTaskOrchestrator(
        confluence_service=confluence_undo_stub,
        jira_service=jira_undo_stub,
        issue_finder_service=issue_finder_undo_stub,
    )


# --- Tests ---


@pytest.mark.asyncio
async def test_undo_run_success_with_tasks(
    undo_orchestrator,
    confluence_undo_stub,
    jira_undo_stub,
    sample_synced_item,
    sample_completed_item,
):
    # Arrange
    logger.info(
        f"Test: test_undo_run_success_with_tasks - sample_synced_item.new_jira_task_key: {sample_synced_item.new_jira_task_key}"
    )
    logger.info(
        f"Test: test_undo_run_success_with_tasks - sample_completed_item.new_jira_task_key: {sample_completed_item.new_jira_task_key}"
    )

    # Pass the raw snake_case dictionaries to the orchestrator
    results_json_data = [
        sample_synced_item.model_dump(
            mode="json"
        ),  # Use mode='json' to ensure output keys are snake_case if no aliases were used
        sample_completed_item.model_dump(
            mode="json"
        ),  # Pydantic v2's default for `model_dump` is already attribute names, but explicit is good.
    ]
    logger.info(f"Test: results_json_data sent to orchestrator: {results_json_data}")

    # Set initial Jira statuses for tasks for the stub's internal state
    jira_undo_stub.set_issue_status(
        sample_synced_item.new_jira_task_key, "To Do", "new"
    )
    jira_undo_stub.set_issue_status(
        sample_completed_item.new_jira_task_key, "Done", "done"
    )

    # Act
    await undo_orchestrator.run(results_json_data)

    # Assert
    # Check if sample_synced_item was transitioned
    assert sample_synced_item.new_jira_task_key in jira_undo_stub.transitioned_issues
    assert (
        jira_undo_stub.transitioned_issues.get(sample_synced_item.new_jira_task_key)
        == config.JIRA_TARGET_STATUSES["undo"]
    )

    # Check if sample_completed_item was transitioned
    assert sample_completed_item.new_jira_task_key in jira_undo_stub.transitioned_issues
    assert (
        jira_undo_stub.transitioned_issues.get(sample_completed_item.new_jira_task_key)
        == config.JIRA_TARGET_STATUSES["undo"]
    )

    # Check that Confluence page was updated
    assert confluence_undo_stub.page_updated_count == 1
    expected_reverted_html = (
        f"<p>Task 1: {sample_synced_item.task_summary} "
        f'<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="abcd">'
        f'<ac:parameter ac:name="key">{sample_synced_item.new_jira_task_key}</ac:parameter>'
        f'<ac:parameter ac:name="server">ConfluenceJiraServer</ac:parameter>'
        f'<ac:parameter ac:name="serverId">confluence-jira-id</ac:parameter>'
        f"</ac:structured-macro></p>"
        f"<p>Task 2: {sample_completed_item.task_summary} "
        f'<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="efgh">'
        f'<ac:parameter ac:name="key">{sample_completed_item.new_jira_task_key}</ac:parameter>'
        f'<ac:parameter ac:name="server">ConfluenceJiraServer</ac:parameter>'
        f'<ac:parameter ac:name="serverId">confluence-jira-id</ac:parameter>'
        f"</ac:structured-macro></p>"
        f"<p>Some other content.</p>"
    )
    assert confluence_undo_stub._page_content == expected_reverted_html


@pytest.mark.asyncio
async def test_undo_run_no_input(undo_orchestrator):
    """Test that an error is raised for no input."""
    with pytest.raises(InvalidInputError, match="No results JSON data provided"):
        await undo_orchestrator.run([])


@pytest.mark.asyncio
async def test_undo_run_empty_json_data(undo_orchestrator):
    """Test that an error is raised for empty or unprocessable JSON data."""
    # This test case should now pass a list with a dictionary that fails Pydantic validation
    # to trigger the "No successful undo items found" error.
    # For example, an empty dict will lead to Pydantic ValidationError for missing required fields.
    with pytest.raises(
        InvalidInputError,
        match="No successful undo items found after processing results data.",
    ):
        await undo_orchestrator.run(
            [{}]
        )  # An empty dict will fail UndoRequestItem validation


@pytest.mark.asyncio
async def test_undo_run_missing_required_columns(undo_orchestrator):
    """
    Test that an error is gracefully handled (logged) if items are missing required fields.
    The orchestrator's _parse_results_for_undo will now catch Pydantic ValidationErrors.
    It will log a warning and skip the item, but then the overall run method
    should raise an InvalidInputError if no successful items are parsed.
    """
    invalid_data = [
        {"missing_col1": "value1"},  # Completely invalid
        {
            "status": "Success",
            "confluence_page_id": "123",
        },  # Missing original_page_version
        {"status": "Success", "original_page_version": 1},  # Missing confluence_page_id
    ]
    with pytest.raises(
        InvalidInputError,
        match="No successful undo items found after processing results data.",
    ):
        await undo_orchestrator.run(invalid_data)


@pytest.mark.asyncio
async def test_undo_no_successful_tasks_in_results(
    undo_orchestrator, confluence_undo_stub, jira_undo_stub
):
    """Test that nothing happens if no successful tasks are found in the results data."""
    # Arrange
    results_json_data = [
        {
            "status": "Failed - Jira Creation",  # Status is "Failed", so it should be skipped
            "new_jira_task_key": "jira-failed-1",
            "confluence_page_id": "456",
            "original_page_version": 1,
        }
    ]

    # Act
    with pytest.raises(
        InvalidInputError,
        match="No successful undo items found after processing results data.",
    ):
        await undo_orchestrator.run(results_json_data)

    # Assert (These assertions will only be reached if the test passes without raising the exception.
    # If the orchestrator changes its behavior to *not* raise an error in this case,
    # these assertions would then confirm no actions were taken.)
    assert not jira_undo_stub.transitioned_issues
    assert confluence_undo_stub.page_updated_count == 0


@pytest.mark.asyncio
async def test_undo_jira_transition_failure(
    undo_orchestrator, jira_undo_stub, sample_synced_item, monkeypatch
):
    """Test that Jira transition failure is gracefully handled (logged, but not stopping)."""
    # Arrange
    logger.info(
        f"Test: test_undo_jira_transition_failure - sample_synced_item.new_jira_task_key: {sample_synced_item.new_jira_task_key}"
    )

    results_json_data = [
        sample_synced_item.model_dump(mode="json")  # Use mode='json'
    ]
    logger.info(f"Test: results_json_data sent to orchestrator: {results_json_data}")

    # Simulate a failure in transition_issue
    jira_undo_stub.transition_issue = AsyncMock(
        side_effect=Exception("Simulated Jira API Error")
    )

    # Act
    await undo_orchestrator.run(results_json_data)

    # Assert
    jira_undo_stub.transition_issue.assert_called_once_with(
        sample_synced_item.new_jira_task_key, config.JIRA_TARGET_STATUSES["undo"]
    )
    assert not jira_undo_stub.transitioned_issues


@pytest.mark.asyncio
async def test_undo_confluence_rollback_failure(
    undo_orchestrator, confluence_undo_stub, sample_synced_item, monkeypatch
):
    """Test that Confluence rollback failure is gracefully handled (logged, but not stopping)."""
    # Arrange
    results_json_data = [
        sample_synced_item.model_dump(mode="json")  # Use mode='json'
    ]

    # Simulate a failure in update_page_content
    confluence_undo_stub.update_page_content = AsyncMock(
        side_effect=Exception("Simulated Confluence API Error")
    )

    # Act
    await undo_orchestrator.run(results_json_data)

    # Assert
    confluence_undo_stub.update_page_content.assert_called_once()
    assert confluence_undo_stub.page_updated_count == 0
