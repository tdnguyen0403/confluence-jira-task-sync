# File: tests/services/orchestration/test_undo_sync_task_orchestrator.py

"""
Tests for the UndoSyncTaskOrchestrator using stubs for service dependencies.
"""

import logging
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import SyncTaskContext, UndoSyncTaskRequest
from src.models.data_models import (
    ConfluenceTask,
    JiraIssueStatus,
)
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)

# Configure logging for the test file itself
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Test Data Fixtures (Raw Dictionary format matching expected snake_case JSON for simplified UndoSyncTaskRequest) ---
@pytest.fixture
def sample_synced_task_raw_json_simplified():
    """A raw dictionary representing a synced task, matching the simplified UndoSyncTaskRequest."""
    return {
        "confluence_page_id": "435680347",
        "original_page_version": 213,
        "new_jira_task_key": "SFSEA-1850",
        "request_user": "tdnguyen",
    }


@pytest.fixture
def sample_completed_synced_task_raw_json_simplified():
    """A raw dictionary representing a completed synced task, matching the simplified UndoSyncTaskRequest."""
    return {
        "confluence_page_id": "435680347", # Same page as sample_synced_task for shared rollback test
        "original_page_version": 213,
        "new_jira_task_key": "SFSEA-1851",
        "request_user": "tdnguyen",
    }


# Pydantic model instances derived from the raw JSON dictionaries for type-safe access in tests
@pytest.fixture
def sample_synced_item(sample_synced_task_raw_json_simplified):
    """A Pydantic UndoSyncTaskRequest instance for a synced task."""
    item = UndoSyncTaskRequest(**sample_synced_task_raw_json_simplified)
    logger.info(
        f"Fixture sample_synced_item created. new_jira_task_key: {item.new_jira_task_key}"
    )
    return item


@pytest.fixture
def sample_completed_item(sample_completed_synced_task_raw_json_simplified):
    """A Pydantic UndoSyncTaskRequest instance for a completed synced task."""
    item = UndoSyncTaskRequest(**sample_completed_synced_task_raw_json_simplified)
    logger.info(
        f"Fixture sample_completed_item created. new_jira_task_key: {item.new_jira_task_key}"
    )
    return item


@pytest.fixture
def sync_context():
    return SyncTaskContext(request_user="test_undo_orchestrator", days_to_due_date=0)


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
                # Return content that *would have been* at that historical version
                if kwargs["version"] == 213:
                    return {
                        "id": page_id,
                        "title": self._page_details[page_id]["title"],
                        "body": {
                            "storage": {
                                "value": "ORIGINAL_HTML_CONTENT_BEFORE_SYNC" # Distinct content for assertion
                            }
                        },
                        "version": {"number": kwargs["version"]},
                    }
            return self._page_details[page_id] # Return current page details if no specific version requested
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
            self._page_details[page_id]["version"]["number"] += 1 # Simulate version increment
        self.page_updated_count += 1
        return True # Simulate success

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
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Optional[str]:
        pass

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        logger.info(
            f"JiraServiceStub: Transitioning issue {issue_key} to {target_status}"
        )
        self.transitioned_issues[issue_key] = target_status
        return True # Simulate success

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
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
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

    async def assign_issue(self, issue_key: str, assignee_name: Optional[str]) -> bool:
        # Not used by orchestrator tests, but required by interface
        return True


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
async def confluence_undo_stub():
    # Pass dummy tasks and HTML, actual HTML content for rollback is fetched by get_page_by_id
    return ConfluenceServiceStub(
        tasks_on_page=[], # Not directly relevant for undo orchestrator
        initial_html="<p>Current content with Jira macros.</p>", # This HTML is for the "current page"
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

    # Pass the Pydantic instances directly, matching main.py's behavior
    undo_requests = [
        sample_synced_item,
        sample_completed_item,
    ]
    logger.info(f"Test: undo_requests sent to orchestrator: {[item.model_dump() for item in undo_requests]}")

    # Act
    undo_results = await undo_orchestrator.run(undo_requests)

    # Assert
    # Expect 3 results: 2 Jira transitions (for SFSEA-1850, SFSEA-1851) + 1 Confluence rollback (for page 435680347)
    assert len(undo_results) == 3

    # Assertions for Jira transitions
    jira_results = [res for res in undo_results if res.action_type == "jira_transition"]
    assert len(jira_results) == 2
    assert all(res.success for res in jira_results)
    assert any(res.target_id == sample_synced_item.new_jira_task_key for res in jira_results)
    assert any(res.target_id == sample_completed_item.new_jira_task_key for res in jira_results)
    assert jira_undo_stub.transitioned_issues.get(sample_synced_item.new_jira_task_key) == config.JIRA_TARGET_STATUSES["undo"]
    assert jira_undo_stub.transitioned_issues.get(sample_completed_item.new_jira_task_key) == config.JIRA_TARGET_STATUSES["undo"]

    # Assertions for Confluence rollback
    confluence_result = next((res for res in undo_results if res.action_type == "confluence_rollback"), None)
    assert confluence_result is not None
    assert confluence_result.success is True
    assert confluence_result.target_id == sample_synced_item.confluence_page_id
    assert confluence_undo_stub.page_updated_count == 1
    # Check against the exact placeholder content from get_page_by_id for the historical version
    assert confluence_undo_stub._page_content == "ORIGINAL_HTML_CONTENT_BEFORE_SYNC"


@pytest.mark.asyncio
async def test_undo_run_no_input(undo_orchestrator):
    """Test that an error is raised for no input."""
    with pytest.raises(InvalidInputError, match="No results data provided"):
        await undo_orchestrator.run([])


@pytest.mark.asyncio
async def test_undo_run_empty_processable_data(undo_orchestrator):
    """Test that an error is raised if valid UndoSyncTaskRequest items are provided but none lead to actionable undo operations."""
    # Arrange: Create a request that is valid according to the model but contains no actionable data.
    undo_requests = [
        UndoSyncTaskRequest(
            confluence_page_id=None,
            original_page_version=None,
            new_jira_task_key=None,
            request_user="test_user_1"
        ),
    ]
    with pytest.raises(InvalidInputError): # Expect Pydantic InvalidInputError
        await undo_orchestrator.run(undo_requests)


@pytest.mark.asyncio
async def test_undo_no_actionable_tasks_in_results( # Renamed for clarity
    undo_orchestrator, confluence_undo_stub, jira_undo_stub
):
    """Test that if valid UndoSyncTaskRequest items are provided, but none lead to actionable undo operations."""
    # Arrange: No requests provided
    with pytest.raises(
        InvalidInputError,
        match="No results data provided for undo operation.",
    ):
        await undo_orchestrator.run([])

    # Assert that no actions were attempted by stubs
    assert not jira_undo_stub.transitioned_issues
    assert confluence_undo_stub.page_updated_count == 0


@pytest.mark.asyncio
async def test_undo_jira_transition_failure(
    undo_orchestrator, jira_undo_stub, sample_synced_item, confluence_undo_stub
):
    """Test that Jira transition failure is captured in UndoActionResult, and page rollback still occurs."""
    # Arrange
    jira_undo_stub.transition_issue = AsyncMock(
        side_effect=Exception("Simulated Jira API Error")
    )

    undo_requests = [sample_synced_item]

    # Act
    undo_results = await undo_orchestrator.run(undo_requests)

    # Assert
    assert len(undo_results) == 2 # Expect one failed Jira, one successful Confluence

    jira_result = next((res for res in undo_results if res.action_type == "jira_transition"), None)
    assert jira_result is not None
    assert jira_result.success is False
    assert "Simulated Jira API Error" in jira_result.status_message
    assert "Simulated Jira API Error" in jira_result.error_message

    confluence_result = next((res for res in undo_results if res.action_type == "confluence_rollback"), None)
    assert confluence_result is not None
    assert confluence_result.success is True # Page rollback should still succeed
    assert confluence_undo_stub.page_updated_count == 1
    assert confluence_undo_stub._page_content == "ORIGINAL_HTML_CONTENT_BEFORE_SYNC"


@pytest.mark.asyncio
async def test_undo_confluence_rollback_failure(
    undo_orchestrator, confluence_undo_stub, sample_synced_item, jira_undo_stub
):
    """Test that Confluence rollback failure is captured in UndoActionResult, and Jira transition still occurs."""
    # Arrange
    confluence_undo_stub.update_page_content = AsyncMock(
        side_effect=Exception("Simulated Confluence API Error")
    )

    undo_requests = [sample_synced_item]

    # Act
    undo_results = await undo_orchestrator.run(undo_requests)

    # Assert
    assert len(undo_results) == 2 # Expect one successful Jira, one failed Confluence

    jira_result = next((res for res in undo_results if res.action_type == "jira_transition"), None)
    assert jira_result is not None
    assert jira_result.success is True # Jira transition should still succeed
    assert jira_undo_stub.transitioned_issues.get(sample_synced_item.new_jira_task_key) == config.JIRA_TARGET_STATUSES["undo"]

    confluence_result = next((res for res in undo_results if res.action_type == "confluence_rollback"), None)
    assert confluence_result is not None
    assert confluence_result.success is False
    assert "Simulated Confluence API Error" in confluence_result.status_message
    assert "Simulated Confluence API Error" in confluence_result.error_message
    assert confluence_undo_stub.page_updated_count == 0 # Should not have updated due to failure
