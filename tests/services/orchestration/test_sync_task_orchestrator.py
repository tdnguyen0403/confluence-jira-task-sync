# File: tests/services/orchestration/test_sync_task_orchestrator.py

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
from src.models.api_models import SyncTaskContext
from src.models.data_models import ConfluenceTask, JiraIssueStatus
from src.services.orchestration.sync_task_orchestrator import SyncTaskOrchestrator

logger = logging.getLogger(__name__)


# --- Test Data ---


@pytest.fixture
def sample_task():
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
    def __init__(self, task_to_return, simulate_update_failure: bool = False):
        self._task = task_to_return
        self.updated_with_links = False
        self.simulate_update_failure = simulate_update_failure

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        return "page123" if "nonexistent" not in url else None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        return []

    async def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        return {
            "id": page_id, "title": "Mock Page Title",
            "body": {"storage": {"value": "content"}}, "version": {"number": 1},
        }

    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        return [self._task] if self._task else []

    async def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> bool:
        if self.simulate_update_failure: return False
        self.updated_with_links = True
        return True

    async def update_page_content(self, page_id: str, title: str, body: str) -> bool:
        return True


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self.created_issue_key: Optional[str] = None
        self.transitioned_issue_key = None
        self.transitioned_to_status = None
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

    async def get_issue(self, issue_key: str, fields: str = "*all") -> dict:
        return {}

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        return None

    async def get_jira_issue(self, issue_key: str):
        pass

    async def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, context: SyncTaskContext
    ) -> dict:
        return {}

    async def get_current_user_display_name(self) -> str:
        return "Stubbed User"

    async def search_issues_by_jql(self, jql_query: str, fields: str = "*all") -> list:
        return []

    async def get_issue_type_name_by_id(self, type_id: str) -> str:
        return ""


class IssueFinderServiceStub(IssueFinderServiceInterface):
    def __init__(self):
        self.found_issue_key = "WP-001"
        self.wp_assignee: Optional[str] = "wp_assignee"

    async def find_issue_on_page(
        self,
        page_id: str,
        issue_type_map: Dict[str, str],
        confluence_api_service: ConfluenceApiServiceInterface,
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
def sync_context():
    return SyncTaskContext(request_user="test_orchestrator", days_to_due_date=5)


@pytest_asyncio.fixture
async def confluence_stub(sample_task):
    return ConfluenceServiceStub(sample_task, simulate_update_failure=False)


@pytest_asyncio.fixture
async def confluence_stub_failing_update(sample_task):
    return ConfluenceServiceStub(sample_task, simulate_update_failure=True)


@pytest_asyncio.fixture
async def jira_stub():
    return JiraServiceStub()


@pytest_asyncio.fixture
async def issue_finder_stub():
    return IssueFinderServiceStub()


@pytest_asyncio.fixture
async def sync_orchestrator(confluence_stub, jira_stub, issue_finder_stub):
    """Provides a SyncTaskOrchestrator instance with stubbed services."""
    return SyncTaskOrchestrator(
        confluence_service=confluence_stub,
        jira_service=jira_stub,
        issue_finder_service=issue_finder_stub,
    )


# --- Pytest Test Functions ---


@pytest.mark.asyncio
async def test_run_success(sync_orchestrator, confluence_stub, jira_stub, sync_context):
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
    confluence_stub_failing_update, jira_stub, issue_finder_stub, sync_context
):
    """Test the path where Jira tasks are created but page update fails."""
    sync_orchestrator = SyncTaskOrchestrator(
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
async def test_run_no_input(sync_orchestrator, sync_context):
    """Test that an error is raised for empty input."""
    with pytest.raises(InvalidInputError, match="No 'confluence_page_urls' provided"):
        await sync_orchestrator.run({}, sync_context, request_id="test-3")


@pytest.mark.asyncio
async def test_run_no_urls(sync_orchestrator, sync_context):
    """Test that an error is raised if no URLs are provided."""
    with pytest.raises(InvalidInputError, match="No 'confluence_page_urls' provided"):
        await sync_orchestrator.run(
            {"confluence_page_urls": []}, sync_context, request_id="test-4"
        )


@pytest.mark.asyncio
async def test_process_page_hierarchy_no_page_id(sync_orchestrator, sync_context):
    """Test that an empty list is returned if a Confluence URL cannot be resolved."""
    results = await sync_orchestrator.process_page_hierarchy(
        "http://example.com/nonexistent", sync_context
    )
    assert results == ([], [])


@pytest.mark.asyncio
async def test_no_work_package_found(
    sync_orchestrator, issue_finder_stub, sync_context
):
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
async def test_jira_creation_failure(sync_orchestrator, jira_stub, sync_context):
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
    sync_orchestrator, confluence_stub, jira_stub, sample_task, sync_context
):
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
    sync_orchestrator, jira_stub, monkeypatch, sync_context
):
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
    sync_orchestrator, jira_stub, monkeypatch, sync_context
):
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
    sync_orchestrator,
    confluence_stub,
    jira_stub,
    issue_finder_stub,
    sample_task,
    sync_context,
):
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
    sync_orchestrator,
    confluence_stub,
    jira_stub,
    issue_finder_stub,
    sample_task,
    sync_context,
):
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
    sync_orchestrator,
    confluence_stub,
    jira_stub,
    issue_finder_stub,
    sample_task,
    sync_context,
):
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
    sync_orchestrator,
    confluence_stub,
    jira_stub,
    issue_finder_stub,
    sample_task,
    sync_context,
):
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
