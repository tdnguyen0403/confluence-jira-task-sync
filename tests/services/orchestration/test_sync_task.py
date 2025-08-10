# File: tests/services/orchestration/test_sync_task_orchestrator.py

import logging
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import SyncTaskContext
from src.models.data_models import ConfluenceTask, JiraIssueStatus
from src.services.orchestration.sync_task import SyncTaskService

logger = logging.getLogger(__name__)


# --- Test Data ---


@pytest.fixture
def sample_task() -> ConfluenceTask:
    """A sample ConfluenceTask for use in tests."""
    return ConfluenceTask(
        confluence_task_id="task1",
        confluence_page_id="page123",
        task_summary="Test Task 1",
        status="incomplete",
        original_page_version=1,
        confluence_page_title="Mock Page Title",
        confluence_page_url="http://mock.confluence.com/mock-page-url",
        assignee_name="test_user",
        due_date="2025-01-01",
        original_page_version_by="Mock Author",
        original_page_version_when="2025-01-01T12:00:00.000Z",
        context="Mock context.",
    )


# --- Stubs for Service Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self, task_to_return: ConfluenceTask, simulate_update_failure: bool = False):
        self._task = task_to_return
        self.updated_with_links = False
        self.simulate_update_failure = simulate_update_failure

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        return "page123" if "nonexistent" not in url else None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        return []

    async def get_page_by_id(self, page_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return {
            "id": page_id, "title": "Mock Page Title",
            "body": {"storage": {"value": "content"}}, "version": {"number": 1},
        }

    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        return [self._task] if self._task else []

    async def add_jira_links_to_page(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> bool:
        if self.simulate_update_failure: return False
        self.updated_with_links = True
        return True

    async def update_page_content(self, page_id: str, title: str, body: str) -> bool:
        return True

    async def health_check(self) -> None:
        pass

    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        return f"mock macro for {jira_key}"


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self) -> None:
        self.created_issue_key: Optional[str] = None
        self.transitioned_issue_key: Optional[str] = None
        self.transitioned_to_status: Optional[str] = None
        self.mock = AsyncMock()

    async def create_issue(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Optional[str]:
        return self.created_issue_key

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        self.transitioned_issue_key = issue_key
        self.transitioned_to_status = target_status
        return True

    async def assign_issue(self, issue_key: str, assignee_name: Optional[str]) -> bool:
        await self.mock.assign_issue(issue_key, assignee_name)
        return True

    async def get_issue(self, issue_key: str, fields: str = "*all") -> Dict[str, Any]:
        return {}

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        return None

    async def get_jira_issue(self, issue_key: str) -> None:
        pass

    async def build_jira_task_payload(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> Dict[str, Any]:
        return {}

    async def get_user_display_name(self) -> str:
        return "Stubbed User"

    async def search_by_jql(self, jql_query: str, fields: str = "*all") -> List[Dict[str, Any]]:
        return []

    async def get_issue_type_name(self, type_id: str) -> str:
        return ""


class IssueFinderServiceStub(IssueFinderServiceInterface):
    def __init__(self) -> None:
        self.found_issue_key: Optional[str] = "WP-001"
        self.wp_assignee: Optional[str] = "wp_assignee"

    async def find_issue_on_page(
        self,
        page_id: str,
        issue_type_map: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        assignee_data = {"name": self.wp_assignee} if self.wp_assignee else None
        return (
            {"key": self.found_issue_key, "fields": {"assignee": assignee_data}}
            if self.found_issue_key
            else None
        )

    async def find_issues_and_macros_on_page(self, page_html: str) -> Dict[str, Any]:
        return {"jira_macros": [], "fetched_issues_map": {}}


# --- Pytest Fixtures ---
@pytest.fixture
def sync_context() -> SyncTaskContext:
    return SyncTaskContext(request_user="test_orchestrator", days_to_due_date=5)


@pytest_asyncio.fixture
async def confluence_stub(sample_task: ConfluenceTask) -> ConfluenceServiceStub:
    return ConfluenceServiceStub(sample_task, simulate_update_failure=False)


@pytest_asyncio.fixture
async def confluence_stub_failing_update(sample_task: ConfluenceTask) -> ConfluenceServiceStub:
    return ConfluenceServiceStub(sample_task, simulate_update_failure=True)


@pytest_asyncio.fixture
async def jira_stub() -> JiraServiceStub:
    return JiraServiceStub()


@pytest_asyncio.fixture
async def issue_finder_stub() -> IssueFinderServiceStub:
    return IssueFinderServiceStub()


@pytest_asyncio.fixture
async def sync_orchestrator(
    confluence_stub: ConfluenceServiceStub, jira_stub: JiraServiceStub, issue_finder_stub: IssueFinderServiceStub
) -> SyncTaskService:
    """Provides a SyncTaskService instance with stubbed services."""
    return SyncTaskService(
        confluence_service=confluence_stub,
        jira_service=jira_stub,
        issue_finder_service=issue_finder_stub,
    )


# --- Pytest Test Functions ---


@pytest.mark.asyncio
async def test_run_success(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    sync_context: SyncTaskContext,
) -> None:
    """Test the main success path where a task is found and synced."""
    jira_stub.created_issue_key = "JIRA-100"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-1"
    )

    assert len(results.jira_task_creation_results) == 1
    assert results.overall_jira_task_creation_status == "Success"

    jira_result = results.jira_task_creation_results[0]
    assert jira_result.creation_status_text == "Success"
    assert jira_result.new_jira_task_key == "JIRA-100"
    assert jira_result.success is True

    assert len(results.confluence_page_update_results) == 1
    confluence_result = results.confluence_page_update_results[0]
    assert confluence_result.updated is True
    assert results.overall_confluence_page_update_status == "Success"
    assert confluence_stub.updated_with_links is True


@pytest.mark.asyncio
async def test_run_confluence_page_update_failure(
    confluence_stub_failing_update: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    issue_finder_stub: IssueFinderServiceStub,
    sync_context: SyncTaskContext,
) -> None:
    """Test the path where Jira tasks are created but page update fails."""
    sync_orchestrator = SyncTaskService(
        confluence_service=confluence_stub_failing_update,
        jira_service=jira_stub,
        issue_finder_service=issue_finder_stub,
    )
    jira_stub.created_issue_key = "JIRA-101"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-2"
    )

    assert len(results.jira_task_creation_results) == 1
    assert results.overall_jira_task_creation_status == "Success"

    assert len(results.confluence_page_update_results) == 1
    confluence_result = results.confluence_page_update_results[0]
    assert confluence_result.updated is False
    assert "Update failed for page" in confluence_result.error_message
    assert results.overall_confluence_page_update_status == "Failed"


@pytest.mark.asyncio
async def test_run_no_input(sync_orchestrator: SyncTaskService, sync_context: SyncTaskContext) -> None:
    """Test that an error is raised for empty input."""
    with pytest.raises(InvalidInputError, match="No 'confluence_page_urls' provided"):
        await sync_orchestrator.run({}, sync_context, request_id="test-3")


@pytest.mark.asyncio
async def test_run_no_urls(sync_orchestrator: SyncTaskService, sync_context: SyncTaskContext) -> None:
    """Test that an error is raised if no URLs are provided."""
    with pytest.raises(InvalidInputError, match="No 'confluence_page_urls' provided"):
        await sync_orchestrator.run(
            {"confluence_page_urls": []}, sync_context, request_id="test-4"
        )


@pytest.mark.asyncio
async def test_process_page_hierarchy_no_page_id(sync_orchestrator: SyncTaskService, sync_context: SyncTaskContext) -> None:
    """Test that an empty list is returned if a Confluence URL cannot be resolved."""
    results = await sync_orchestrator.process_page_hierarchy(
        "http://example.com/nonexistent", sync_context
    )
    assert results == ([], [])


@pytest.mark.asyncio
async def test_no_work_package_found(
    sync_orchestrator: SyncTaskService, issue_finder_stub: IssueFinderServiceStub, sync_context: SyncTaskContext
) -> None:
    """Test that a task is skipped if no parent Work Package is found."""
    issue_finder_stub.found_issue_key = None
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-5"
    )

    assert len(results.jira_task_creation_results) == 1
    jira_result = results.jira_task_creation_results[0]
    assert jira_result.creation_status_text == "Failed - No Work Package found"
    assert jira_result.success is False
    assert len(results.confluence_page_update_results) == 0
    assert "Skipped" in results.overall_confluence_page_update_status


@pytest.mark.asyncio
async def test_jira_creation_failure(sync_orchestrator: SyncTaskService, jira_stub: JiraServiceStub, sync_context: SyncTaskContext) -> None:
    """Test that Jira issue creation failure is reflected in the result."""
    jira_stub.created_issue_key = None
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-6"
    )

    assert len(results.jira_task_creation_results) == 1
    jira_result = results.jira_task_creation_results[0]
    assert jira_result.creation_status_text == "Failed - Jira API (No Key)"
    assert jira_result.success is False
    assert len(results.confluence_page_update_results) == 0


@pytest.mark.asyncio
async def test_completed_task_transition(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
) -> None:
    """Test that a completed Confluence task is transitioned to 'Done' in Jira."""
    sample_task.status = "complete"
    confluence_stub._task = sample_task
    jira_stub.created_issue_key = "JIRA-200"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-7"
    )

    assert len(results.jira_task_creation_results) == 1
    jira_result = results.jira_task_creation_results[0]
    assert jira_result.creation_status_text == "Success - Completed Task Created"
    assert jira_result.success is True
    assert (
        jira_stub.transitioned_to_status
        == config.JIRA_TARGET_STATUSES["completed_task"]
    )


@pytest.mark.asyncio
async def test_dev_mode_new_task_transition(
    sync_orchestrator: SyncTaskService, jira_stub: JiraServiceStub, monkeypatch: Any, sync_context: SyncTaskContext
) -> None:
    """Test that in dev mode, a new task is transitioned to 'Backlog'."""
    monkeypatch.setattr(config, "DEV_ENVIRONMENT", True)
    jira_stub.created_issue_key = "JIRA-300"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-8"
    )

    assert len(results.jira_task_creation_results) == 1
    jira_result = results.jira_task_creation_results[0]
    assert jira_result.creation_status_text == "Success"
    assert jira_result.success is True
    assert (
        jira_stub.transitioned_to_status == config.JIRA_TARGET_STATUSES["new_task_dev"]
    )


@pytest.mark.asyncio
async def test_prod_mode_new_task_no_transition(
    sync_orchestrator: SyncTaskService, jira_stub: JiraServiceStub, monkeypatch: Any, sync_context: SyncTaskContext
) -> None:
    """Test that in production mode, a new task is not transitioned."""
    monkeypatch.setattr(config, "DEV_ENVIRONMENT", False)
    jira_stub.created_issue_key = "JIRA-300"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-9"
    )

    assert jira_stub.transitioned_issue_key is None
    assert jira_stub.transitioned_to_status is None


@pytest.mark.asyncio
async def test_assign_jira_task_from_work_package_when_confluence_task_unassigned(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    issue_finder_stub: IssueFinderServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
) -> None:
    """
    Test that a Jira task is assigned from the Work Package
    if the Confluence task itself has no assignee.
    """
    sample_task.assignee_name = None
    confluence_stub._task = sample_task
    issue_finder_stub.wp_assignee = "wp_assignee_from_jira"
    jira_stub.created_issue_key = "JIRA-400"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    await sync_orchestrator.run(input_data, sync_context, request_id="test-10")

    jira_stub.mock.assign_issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_jira_task_retains_confluence_assignee_even_if_work_package_has_assignee(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    issue_finder_stub: IssueFinderServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
) -> None:
    """
    Test that a Jira task retains the assignee from the Confluence task
    even if the Work Package also has an assignee.
    """
    sample_task.assignee_name = "confluence_assignee"
    confluence_stub._task = sample_task
    issue_finder_stub.wp_assignee = "wp_assignee_from_jira"
    jira_stub.created_issue_key = "JIRA-500"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    await sync_orchestrator.run(input_data, sync_context, request_id="test-11")

    jira_stub.mock.assign_issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_jira_task_retains_confluence_assignee_when_work_package_unassigned(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    issue_finder_stub: IssueFinderServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
) -> None:
    """
    Test that a Jira task retains the assignee from the Confluence task
    even if the Work Package has no assignee.
    """
    sample_task.assignee_name = "confluence_assignee"
    confluence_stub._task = sample_task
    issue_finder_stub.wp_assignee = None
    jira_stub.created_issue_key = "JIRA-700"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    await sync_orchestrator.run(input_data, sync_context, request_id="test-12")

    jira_stub.mock.assign_issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_unassign_jira_task_when_both_confluence_task_and_work_package_unassigned(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    issue_finder_stub: IssueFinderServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
) -> None:
    """
    Test that a newly created Jira task is explicitly unassigned
    if neither the Confluence task nor the Work Package has an assignee.
    """
    sample_task.assignee_name = None
    confluence_stub._task = sample_task
    issue_finder_stub.wp_assignee = None
    jira_stub.created_issue_key = "JIRA-600"
    input_data = {"confluence_page_urls": ["http://example.com/page1"]}

    await sync_orchestrator.run(input_data, sync_context, request_id="test-13")

    jira_stub.mock.assign_issue.assert_awaited_once_with("JIRA-600", None)

@pytest.mark.asyncio
async def test_process_single_task_empty_summary(
    sync_orchestrator, sample_task, sync_context
):
    """
    Tests that a task with an empty or whitespace summary is skipped.
    This covers the `if not task.task_summary...` branch in `_process_single_task`.
    """
    sample_task.task_summary = "   "  # Whitespace only

    result = await sync_orchestrator._process_single_task(sample_task, sync_context)

    assert result.status_text == "Skipped - Empty Task"
    assert result.new_jira_task_key is None


@pytest.mark.asyncio
async def test_process_tasks_no_successes(
    sync_orchestrator, issue_finder_stub, sync_context, sample_task
):
    """
    Tests the scenario where tasks are processed but none succeed, so no Confluence update is attempted.
    This covers the `else` branch of `if tasks_to_update:`.
    """
    # Make all tasks fail by having no parent work package
    issue_finder_stub.found_issue_key = None

    jira_results, confluence_results = await sync_orchestrator._process_tasks(
        [sample_task], sync_context
    )

    assert len(jira_results) == 1
    assert jira_results[0].success is False
    # Crucially, confluence_results should be empty as no update should be triggered
    assert len(confluence_results) == 0


@pytest.mark.asyncio
async def test_update_confluence_page_get_page_fails(
    sync_orchestrator, confluence_stub
):
    """
    Tests the failure path when get_page_by_id returns None inside _update_confluence_page.
    This covers the `if not page_details:` branch.
    """
    # Make get_page_by_id return None for the specific page
    confluence_stub.get_page_by_id = AsyncMock(return_value=None)
    page_id = "nonexistent_page"
    mappings = [{"confluence_task_id": "t1", "jira_key": "KEY-1"}]

    result = await sync_orchestrator._update_confluence_page(page_id, mappings)

    assert result.updated is False
    assert result.page_id == page_id
    assert f"Could not find page {page_id} for update" in result.error_message


@pytest.mark.asyncio
async def test_update_confluence_page_update_call_returns_false(
    sync_orchestrator, confluence_stub
):
    """
    Tests failure when the final add_jira_links_to_page call returns False.
    This covers the `else` branch for `if success:` in `_update_confluence_page`.
    """
    # Make the update call itself fail by returning False
    confluence_stub.add_jira_links_to_page = AsyncMock(return_value=False)
    page_id = "page123"
    mappings = [{"confluence_task_id": "t1", "jira_key": "KEY-1"}]

    result = await sync_orchestrator._update_confluence_page(page_id, mappings)

    assert result.updated is False
    assert result.page_id == page_id
    assert "Update failed for page" in result.error_message


@pytest.mark.asyncio
async def test_completed_task_transition_failure(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
):
    """Test that a failure to transition a completed task is handled gracefully."""
    sample_task.status = "complete"
    confluence_stub._task = sample_task
    jira_stub.created_issue_key = "JIRA-201"
    # Simulate the transition failing
    jira_stub.transition_issue = AsyncMock(return_value=False)

    input_data = {"confluence_page_urls": ["http://example.com/page1"]}
    results = await sync_orchestrator.run(
        input_data, sync_context, request_id="test-transition-fail"
    )

    jira_result = results.jira_task_creation_results[0]
    assert jira_result.success is True # Creation itself was a success
    assert jira_result.creation_status_text == "Success - Task Created (Transition Failed)"
    jira_stub.transition_issue.assert_awaited_once_with(
        "JIRA-201", config.JIRA_TARGET_STATUSES["completed_task"]
    )


@pytest.mark.asyncio
async def test_assign_issue_failure_is_logged(
    sync_orchestrator: SyncTaskService,
    confluence_stub: ConfluenceServiceStub,
    jira_stub: JiraServiceStub,
    issue_finder_stub: IssueFinderServiceStub,
    sample_task: ConfluenceTask,
    sync_context: SyncTaskContext,
    caplog
):
    """
    Test that a failure to unassign an issue is logged but does not fail the whole process.
    This covers the `if not await self.jira_service.assign_issue` branch.
    """
    caplog.set_level(logging.WARNING)
    # Task and WP are unassigned
    sample_task.assignee_name = None
    issue_finder_stub.wp_assignee = None
    confluence_stub._task = sample_task

    jira_stub.created_issue_key = "JIRA-800"
    # Simulate assign_issue failing
    jira_stub.assign_issue = AsyncMock(return_value=False)

    input_data = {"confluence_page_urls": ["http://example.com/page1"]}
    await sync_orchestrator.run(input_data, sync_context, request_id="test-assign-fail")

    # Check that the warning was logged
    assert "Failed to explicitly unassign issue JIRA-800." in caplog.text
    jira_stub.assign_issue.assert_awaited_once_with("JIRA-800", None)

@pytest.mark.asyncio
async def test_run_handles_exception_in_hierarchy_processing(
    sync_orchestrator, sync_context, caplog
):
    """
    Tests that the main 'run' method gracefully handles an exception raised
    by `process_page_hierarchy` and continues processing other URLs.
    """
    caplog.set_level(logging.ERROR)

    with patch.object(
        sync_orchestrator, "process_page_hierarchy", new_callable=AsyncMock
    ) as mock_process:

        async def mock_side_effect(url, context):
            if "fail" in url:
                raise RuntimeError("Simulated processing error")
            else:
                # Successful call returns an empty result tuple
                return ([], [])

        mock_process.side_effect = mock_side_effect

        input_data = {
            "confluence_page_urls": ["http://fail.com", "http://succeed.com"]
        }

        response = await sync_orchestrator.run(input_data, sync_context, "req-123")

        # The error should be logged
        assert "Error processing page hierarchy: Simulated processing error" in caplog.text
        # The overall status should reflect that something was skipped/failed
        assert response.overall_status != "Success"
        # The successful result from the second URL should still be processed
        assert response.overall_jira_task_creation_status == "Skipped - No actions processed"


@pytest.mark.asyncio
async def test_collect_tasks_handles_none_page_details(
    sync_orchestrator, confluence_stub, caplog
):
    """
    Tests that `_collect_tasks` correctly skips a page if `get_page_by_id` returns None.
    This covers the `else` path of `if page_details:` at line 114.
    """
    page_ids = ["page123", "nonexistent_page"]

    # Mock `get_page_by_id` to return None for one of the pages
    original_get_page = confluence_stub.get_page_by_id
    async def side_effect(page_id, **kwargs):
        if page_id == "nonexistent_page":
            return None
        return await original_get_page(page_id, **kwargs)

    confluence_stub.get_page_by_id = side_effect

    tasks = await sync_orchestrator._collect_tasks(page_ids)

    # Only the task from the valid page should be collected
    assert len(tasks) == 1
    assert tasks[0].confluence_page_id == "page123"

@pytest.mark.asyncio
async def test_run_handles_unproccesable_url_and_returns_partial_status(
    sync_orchestrator: SyncTaskService,
    sync_context: SyncTaskContext,
    caplog,
):
    """
    Tests that if processing one URL hierarchy fails with an exception, the
    orchestrator catches it, continues processing other URLs, and sets the
    overall status to reflect a partial success.
    """
    # ARRANGE: Set up the test to log errors
    caplog.set_level(logging.ERROR)

    # Use patch to temporarily replace the `process_page_hierarchy` method
    with patch.object(
        sync_orchestrator, "process_page_hierarchy", new_callable=AsyncMock
    ) as mock_process:

        # Define an async helper to control the mock's behavior
        async def mock_side_effect(url, context):
            if "fail" in url:
                # Raise an exception for the "un-processable" URL
                raise ValueError("Simulated processing error for this URL")
            else:
                # Return a normal, empty result for the valid URL
                return ([], [])

        mock_process.side_effect = mock_side_effect

        input_data = {
            "confluence_page_urls": [
                "http://example.com/fail", # This URL will trigger the exception
                "http://example.com/succeed" # This one will be processed
            ]
        }

        # ACT: Run the orchestrator with the mixed input
        response = await sync_orchestrator.run(
            input_data, sync_context, request_id="test-partial-fail"
        )

        # ASSERT
        # 1. The overall status should be the special partial success message.
        #    (Note: There's a small typo "come" in your source code, the test reflects this)
        assert response.overall_status == "Partial Success - some URLs cannot be processed"

        # 2. An error for the failed URL should have been logged.
        assert "Error processing page hierarchy: Simulated processing error for this URL" in caplog.text

        # 3. The sub-statuses should reflect that the successful URL found no tasks to process.
        assert response.overall_jira_task_creation_status == "Skipped - No actions processed"
        assert response.overall_confluence_page_update_status == "Skipped - No actions processed"
