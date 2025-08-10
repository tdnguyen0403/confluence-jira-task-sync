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
from src.models.data_models import ConfluenceTask, JiraIssueStatus
from src.services.orchestration.undo_sync_task import (
    UndoSyncService,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Test Data Fixtures ---
@pytest.fixture
def sample_synced_item() -> UndoSyncTaskRequest:
    return UndoSyncTaskRequest(
        confluence_page_id="435680347",
        original_page_version=213,
        new_jira_task_key="SFSEA-1850",
        request_user="tdnguyen",
    )


@pytest.fixture
def sample_completed_item() -> UndoSyncTaskRequest:
    return UndoSyncTaskRequest(
        confluence_page_id="435680347",
        original_page_version=213,
        new_jira_task_key="SFSEA-1851",
        request_user="tdnguyen",
    )


# --- Stubs for Service Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self, initial_html: str = ""):
        self._page_content = initial_html
        self.page_updated_count = 0
        self._page_details = {
            "435680347": {
                "id": "435680347", "title": "Simple Page Test",
                "body": {"storage": {"value": initial_html}},
                "version": {"number": 214},
            }
        }

    async def get_page_by_id(self, page_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if page_id in self._page_details:
            if "version" in kwargs and kwargs["version"] == 213:
                return {
                    "id": page_id, "title": self._page_details[page_id]["title"],
                    "body": {"storage": {"value": "ORIGINAL_HTML_CONTENT_BEFORE_SYNC"}},
                    "version": {"number": kwargs["version"]},
                }
            return self._page_details[page_id]
        return None

    async def update_page_content(
        self, page_id: str, new_title: str, new_body: str
    ) -> bool:
        self._page_content = new_body
        self.page_updated_count += 1
        return True

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        return None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        return []

    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        return []

    async def update_page_with_jira_links(self, page_id: str, mappings: List[Dict[str, str]]) -> bool:
        return True

    async def health_check(self) -> None:
        pass

    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        return f"mock macro for {jira_key}"


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self.transitioned_issues: Dict[str, str] = {}

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        self.transitioned_issues[issue_key] = target_status
        return True

    async def create_issue(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Optional[str]:
        return None

    async def get_issue(self, issue_key: str, fields: str = "*all") -> Dict[str, Any]:
        return {}

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        return None

    async def get_jira_issue(self, issue_key: str) -> None:
        pass

    async def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Dict[str, Any]:
        return {}

    async def get_current_user_display_name(self) -> str:
        return "Stubbed User"

    async def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> List[Dict[str, Any]]:
        return []

    async def get_issue_type_name_by_id(self, type_id: str) -> str:
        return ""

    async def assign_issue(self, issue_key: str, assignee_name: Optional[str]) -> bool:
        return True

class IssueFinderServiceStub(IssueFinderServiceInterface):
    async def find_issue_on_page(
        self,
        page_id: str,
        issue_type_map: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        return None

    async def find_issues_and_macros_on_page(self, page_html: str) -> Dict[str, Any]:
        return {"jira_macros": [], "fetched_issues_map": {}}

# --- Pytest Fixtures ---


@pytest_asyncio.fixture
async def confluence_undo_stub() -> ConfluenceServiceStub:
    return ConfluenceServiceStub(initial_html="<p>Current content.</p>")


@pytest_asyncio.fixture
async def jira_undo_stub() -> JiraServiceStub:
    return JiraServiceStub()


@pytest_asyncio.fixture
async def issue_finder_undo_stub() -> IssueFinderServiceStub:
    return IssueFinderServiceStub()


@pytest_asyncio.fixture
async def undo_orchestrator(
    confluence_undo_stub: ConfluenceServiceStub,
    jira_undo_stub: JiraServiceStub,
    issue_finder_undo_stub: IssueFinderServiceStub,
) -> UndoSyncService:
    return UndoSyncService(
        confluence_service=confluence_undo_stub,
        jira_service=jira_undo_stub,
        issue_finder_service=issue_finder_undo_stub,
    )


# --- Tests ---


@pytest.mark.asyncio
async def test_undo_run_success_with_tasks(
    undo_orchestrator: UndoSyncService,
    confluence_undo_stub: ConfluenceServiceStub,
    jira_undo_stub: JiraServiceStub,
    sample_synced_item: UndoSyncTaskRequest,
    sample_completed_item: UndoSyncTaskRequest,
) -> None:
    undo_requests = [sample_synced_item, sample_completed_item]

    undo_response = await undo_orchestrator.run(
        undo_requests, request_id="undo-test-1"
    )

    assert len(undo_response.results) == 3

    jira_results = [
        r for r in undo_response.results if r.action_type == "jira_transition"
    ]
    assert len(jira_results) == 2
    assert all(res.success for res in jira_results)
    assert (
        jira_undo_stub.transitioned_issues.get(sample_synced_item.new_jira_task_key)
        == config.JIRA_TARGET_STATUSES["undo"]
    )
    assert (
        jira_undo_stub.transitioned_issues.get(sample_completed_item.new_jira_task_key)
        == config.JIRA_TARGET_STATUSES["undo"]
    )

    confluence_result = next(
        (r for r in undo_response.results if r.action_type == "confluence_rollback"),
        None,
    )
    assert confluence_result is not None
    assert confluence_result.success is True
    assert confluence_undo_stub.page_updated_count == 1
    assert confluence_undo_stub._page_content == "ORIGINAL_HTML_CONTENT_BEFORE_SYNC"


@pytest.mark.asyncio
async def test_undo_run_no_input(undo_orchestrator: UndoSyncService) -> None:
    """Test that an error is raised for no input."""
    with pytest.raises(InvalidInputError, match="No data provided for undo operation"):
        await undo_orchestrator.run([], request_id="undo-test-2")


@pytest.mark.asyncio
async def test_undo_run_empty_processable_data(undo_orchestrator: UndoSyncService) -> None:
    """Test error is raised if requests contain no actionable data."""
    undo_requests = [
        UndoSyncTaskRequest(
            confluence_page_id=None,
            original_page_version=None,
            new_jira_task_key=None,
            request_user="test_user_1",
        )
    ]
    with pytest.raises(
        InvalidInputError, match="No valid undo actions could be parsed."
    ):
        await undo_orchestrator.run(undo_requests, request_id="undo-test-3")

@pytest.mark.asyncio
async def test_undo_no_actionable_tasks_in_results(
    undo_orchestrator: UndoSyncService,
    confluence_undo_stub: ConfluenceServiceStub,
    jira_undo_stub: JiraServiceStub,
) -> None:
    """
    Checks for the expected error when an empty list is provided.
    """
    with pytest.raises(
        InvalidInputError,
        match="No data provided for undo operation.",
    ):
        await undo_orchestrator.run([], request_id="undo-test-no-action")

    assert not jira_undo_stub.transitioned_issues
    assert confluence_undo_stub.page_updated_count == 0

@pytest.mark.asyncio
async def test_undo_jira_transition_failure(
    undo_orchestrator: UndoSyncService,
    jira_undo_stub: JiraServiceStub,
    sample_synced_item: UndoSyncTaskRequest,
    confluence_undo_stub: ConfluenceServiceStub,
) -> None:
    """Test failure capture when Jira transition fails."""
    jira_undo_stub.transition_issue = AsyncMock(
        side_effect=Exception("Simulated Jira API Error")
    )
    undo_requests = [sample_synced_item]

    undo_response = await undo_orchestrator.run(
        undo_requests, request_id="undo-test-4"
    )

    assert len(undo_response.results) == 2
    jira_result = next(
        (r for r in undo_response.results if r.action_type == "jira_transition"), None
    )
    assert jira_result is not None
    assert jira_result.success is False
    assert "Simulated Jira API Error" in jira_result.error_message
    confluence_result = next(
        (r for r in undo_response.results if r.action_type == "confluence_rollback"),
        None,
    )
    assert confluence_result is not None
    assert confluence_result.success is True


@pytest.mark.asyncio
async def test_undo_confluence_rollback_failure(
    undo_orchestrator: UndoSyncService,
    confluence_undo_stub: ConfluenceServiceStub,
    sample_synced_item: UndoSyncTaskRequest,
    jira_undo_stub: JiraServiceStub,
) -> None:
    """Test failure capture when Confluence rollback fails."""
    confluence_undo_stub.update_page_content = AsyncMock(
        side_effect=Exception("Simulated Confluence API Error")
    )
    undo_requests = [sample_synced_item]

    undo_response = await undo_orchestrator.run(
        undo_requests, request_id="undo-test-5"
    )

    assert len(undo_response.results) == 2
    jira_result = next(
        (r for r in undo_response.results if r.action_type == "jira_transition"), None
    )
    assert jira_result is not None
    assert jira_result.success is True
    confluence_result = next(
        (r for r in undo_response.results if r.action_type == "confluence_rollback"),
        None,
    )
    assert confluence_result is not None
    assert confluence_result.success is False
    assert "Simulated Confluence API Error" in confluence_result.error_message


@pytest.mark.asyncio
async def test_parse_undo_requests_with_partial_data(
    undo_orchestrator, caplog
):
    """
    Tests that _parse_undo_requests correctly handles a mix of valid and invalid items.
    It should parse the valid ones and log a warning for the invalid ones.
    This covers the `else` branch in `_parse_undo_requests`.
    """
    caplog.set_level(logging.WARNING)
    requests_data = [
        UndoSyncTaskRequest(  # Valid item
            confluence_page_id="page1",
            original_page_version=10,
            new_jira_task_key="JIRA-1",
            request_user="user"
        ),
        UndoSyncTaskRequest(  # Item missing page version
            confluence_page_id="page1",
            original_page_version=None,
            new_jira_task_key="JIRA-2",
            request_user="user"
        ),
        UndoSyncTaskRequest(  # Item with only a Jira key
            confluence_page_id=None,
            original_page_version=None,
            new_jira_task_key="JIRA-3",
            request_user="user"
        )
    ]

    jira_keys, pages = undo_orchestrator._parse_undo_requests(requests_data)

    assert jira_keys == {"JIRA-1", "JIRA-2", "JIRA-3"}
    assert pages == {"page1": 10}
    assert "Skipping undo item with missing data" in caplog.text


@pytest.mark.asyncio
async def test_rollback_confluence_page_fetch_fails(
    undo_orchestrator, confluence_undo_stub
):
    """
    Tests the failure path in _rollback_confluence_page when get_page_by_id returns None.
    This covers the `if not page...` branch.
    """
    # Make the stub return None for the specific page and version
    confluence_undo_stub.get_page_by_id = AsyncMock(return_value=None)
    page_id = "nonexistent_page"
    version = 5

    result = await undo_orchestrator._rollback_confluence_page(page_id, version)

    assert result.success is False
    assert result.action_type == "confluence_rollback"
    assert result.target_id == page_id
    assert f"Failed to get historical content for v{version}" in result.status_message


@pytest.mark.asyncio
async def test_rollback_confluence_page_malformed_content(
    undo_orchestrator, confluence_undo_stub
):
    """
    Tests the failure path in _rollback_confluence_page when the fetched page is malformed.
    This covers the `...or "body" not in page...` branch.
    """
    page_id = "435680347"
    version = 213
    # Return a page object that's missing the 'body' key
    malformed_page = {"id": page_id, "title": "Malformed Page"}
    confluence_undo_stub.get_page_by_id = AsyncMock(return_value=malformed_page)

    result = await undo_orchestrator._rollback_confluence_page(page_id, version)

    assert result.success is False
    assert result.action_type == "confluence_rollback"
    assert f"Failed to get historical content for v{version}" in result.status_message


@pytest.mark.asyncio
async def test_determine_overall_status_no_results(undo_orchestrator):
    """
    Tests the _determine_overall_status method with an empty list of results.
    This covers the `if not results:` branch.
    """
    status = undo_orchestrator._determine_overall_status([], lambda r: r.success)
    assert status == "Skipped - No actions processed"

@pytest.mark.asyncio
async def test_parse_undo_requests_handles_duplicate_pages(
    undo_orchestrator, caplog
):
    """
    Tests that _parse_undo_requests correctly identifies the *earliest* page
    version when multiple requests for the same page exist.
    This covers the `else` branch of `if page_id not in pages or version < pages[page_id]:`
    at line 86.
    """
    requests_data = [
        UndoSyncTaskRequest(
            confluence_page_id="page1", original_page_version=10,
            new_jira_task_key="JIRA-1", request_user="user"
        ),
        # This one is for the same page but an OLDER version, so it should become the target
        UndoSyncTaskRequest(
            confluence_page_id="page1", original_page_version=8,
            new_jira_task_key="JIRA-2", request_user="user"
        ),
        # This one is for the same page but a NEWER version, so it should be ignored
        UndoSyncTaskRequest(
            confluence_page_id="page1", original_page_version=12,
            new_jira_task_key="JIRA-3", request_user="user"
        ),
        UndoSyncTaskRequest(
            confluence_page_id="page2", original_page_version=5,
            new_jira_task_key="JIRA-4", request_user="user"
        ),
    ]

    jira_keys, pages = undo_orchestrator._parse_undo_requests(requests_data)

    # All Jira keys should be collected
    assert jira_keys == {"JIRA-1", "JIRA-2", "JIRA-3", "JIRA-4"}

    # For "page1", only the lowest version number (8) should be stored
    assert pages == {"page1": 8, "page2": 5}

@pytest.mark.asyncio
async def test_parse_undo_requests_handles_duplicates_and_missing_data(
    undo_orchestrator, caplog
):
    """
    Tests that _parse_undo_requests correctly identifies the *earliest* page
    version when multiple requests for the same page exist and handles items with
    missing page data.
    This covers the `else` branch of the version check at line 86 and the `else`
    branch for missing page data at line 210.
    """
    caplog.set_level(logging.WARNING)

    requests_data = [
        # Base item for page1
        UndoSyncTaskRequest(
            confluence_page_id="page1", original_page_version=10,
            new_jira_task_key="JIRA-1", request_user="user"
        ),
        # A newer version for page1, should be ignored
        UndoSyncTaskRequest(
            confluence_page_id="page1", original_page_version=12,
            new_jira_task_key="JIRA-2", request_user="user"
        ),
        # An older version for page1, should be selected
        UndoSyncTaskRequest(
            confluence_page_id="page1", original_page_version=8,
            new_jira_task_key="JIRA-3", request_user="user"
        ),
        # An item with a missing page ID, should be logged and partially processed
        UndoSyncTaskRequest(
            confluence_page_id=None, original_page_version=None,
            new_jira_task_key="JIRA-4", request_user="user"
        )
    ]

    jira_keys, pages = undo_orchestrator._parse_undo_requests(requests_data)

    # All Jira keys should still be collected
    assert jira_keys == {"JIRA-1", "JIRA-2", "JIRA-3", "JIRA-4"}

    # For "page1", only the lowest version number (8) should be stored
    assert pages == {"page1": 8}

    # A warning should be logged for the item with missing data
    assert "Skipping undo item with missing data" in caplog.text
