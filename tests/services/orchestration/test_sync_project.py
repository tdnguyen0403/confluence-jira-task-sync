# Mute logging during tests to keep test output clean
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
from src.models.data_models import JiraIssue, JiraIssueStatus

# Now import the service and models using the correct, updated path
from src.services.orchestration.sync_project import (
    SyncProjectService,
)

logging.disable(logging.CRITICAL)
# --- Stub Implementations for Dependencies ---


class ConfluenceServiceStub(ConfluenceApiServiceInterface):
    def __init__(self):
        self._pages_content = {}
        self._updated_pages = {}  # To track updates
        self._update_success = True  # Controllable success for update_page

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        return "page1" if "page1" in url else None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        return []

    async def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        content = self._pages_content.get(page_id)
        if content is None:
            return None
        return {
            "id": page_id,
            "title": f"Page {page_id}",
            "body": {"storage": {"value": content}},
            "version": {"number": 1},
        }

    # This method is actually called by the SyncProjectService
    async def update_page(self, page_id: str, new_title: str, new_body: str) -> bool:
        self._updated_pages[page_id] = {"title": new_title, "body": new_body}
        return self._update_success

    # If ConfluenceApiServiceInterface defines update_page_content as abstract,
    # we must implement it. Delegating to update_page as a practical stub.
    async def update_page_content(
        self, page_id: str, new_title: str, new_body: str
    ) -> bool:
        return await self.update_page(page_id, new_title, new_body)

    def set_page_content(self, page_id: str, content: str):
        self._pages_content[page_id] = content

    def set_update_success(self, success: bool):
        self._update_success = success

    async def health_check(self) -> None:
        pass

    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        macro_id = "mock-macro-id"  # Use a fixed ID for testing
        summary_param = '<ac:parameter ac:name="showSummary">true</ac:parameter>' if with_summary else '<ac:parameter ac:name="showSummary">false</ac:parameter>'
        return (
            f'<ac:structured-macro ac:name="jira" ac:schema-version="1" '
            f'ac:macro-id="{macro_id}>'
            f'{summary_param}'
            f'<ac:parameter ac:name="server">ConfluenceJiraServer</ac:parameter>'
            f'<ac:parameter ac:name="serverId">confluence-jira-id</ac:parameter>'
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f'</ac:structured-macro>'
        )


    @property
    def jira_macro_server_name(self) -> str:
        return "ConfluenceJiraServer"

    @property
    def jira_macro_server_id(self) -> str:
        return "confluence-jira-id"

    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        # This simple mock is enough for the test to function
        return f'<p>New Macro for {jira_key}</p>'

    # Implementations for other abstract methods (minimal for test purposes)
    async def get_tasks_from_page(self, page_details: dict) -> list:
        return []

    async def add_jira_links_to_page(self, page_id: str, mappings: list) -> None:
        pass

    async def create_page(self, **kwargs) -> dict:
        return {}

    async def get_user_by_username(self, username: str) -> dict:
        return {}


class JiraServiceStub(JiraApiServiceInterface):
    def __init__(self):
        self._issues = {}
        self._issue_types = {}
        self._jql_search_results = {}
        self._search_issues_raise_exception_for_jql = None

    async def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        return self._issues.get(issue_key)

    async def get_issue_type_name(self, type_id: str) -> Optional[str]:
        return self._issue_types.get(type_id, {}).get("name")

    async def search_by_jql(self, jql: str, fields: str="*all") -> List[Dict[str, Any]]:
        if jql in self._jql_search_results:
            return self._jql_search_results[jql]
        if jql.startswith("issue in (") and jql.endswith(")"):
            keys_str = jql[len("issue in (") : -1]
            keys = [key.strip().strip("'") for key in keys_str.split(",")]
            return [self._issues[key] for key in keys if key in self._issues]
        return []

    def add_issue(self, key: str, data: Dict[str, Any]):
        self._issues[key] = data

    def add_issue_type(self, type_id: str, name: str):
        self._issue_types[type_id] = {"id": type_id, "name": name}

    def add_jql_result(self, jql_query: str, results: List[Dict[str, Any]]):
        self._jql_search_results[jql_query] = results

    def set_search_issues_exception(self, jql: str):
        self._search_issues_raise_exception_for_jql = jql

    async def create_issue(
        self, task: Any, parent_key: str, context: Any
    ) -> Optional[str]:
        pass

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        pass

    async def build_jira_task_payload(
        self, task: Any, parent_key: str, context: Any
    ) -> Dict:
        pass

    async def assign_issue(self, issue_key: str, assignee_name: Optional[str]) -> bool:
        return True

    async def get_user_display_name(
        self,
    ) -> str:
        return "Stubbed Jira User"

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        return None

    async def get_jira_issue(self, issue_key: str) -> Optional[JiraIssue]:
        issue_data = self._issues.get(issue_key)
        if issue_data:
            return JiraIssue(
                key=issue_data["key"],
                summary=issue_data["fields"]["summary"],
                issue_type=issue_data["fields"]["issuetype"]["name"],
                status=JiraIssueStatus(
                    name=issue_data["fields"]["status"]["name"],
                    category=issue_data["fields"]["status"]["statusCategory"]["key"],
                ),
            )
        return None

    async def get_issue_type_by_id(
        self, type_id: str
    ) -> Optional[Dict[str, Any]]:
        return self._issue_types.get(type_id)

    async def search_issues(
        self, jql_query: str, fields: str = "*all", **kwargs
    ) -> Dict[str, Any]:
        if self._search_issues_raise_exception_for_jql == jql_query:
            raise Exception(f"Simulated Jira API error for JQL: {jql_query}")

        if jql_query in self._jql_search_results:
            return self._jql_search_results[jql_query]

        if jql_query.startswith("issue in (") and jql_query.endswith(")"):
            keys_str = jql_query[len("issue in (") : -1]
            keys = [key.strip().strip("'") for key in keys_str.split(",")]
            found_issues = [self._issues[key] for key in keys if key in self._issues]
            return {"issues": found_issues}

        return {"issues": []}


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
async def confluence_updater_stub():
    return ConfluenceServiceStub()


@pytest_asyncio.fixture
async def jira_updater_stub():
    return JiraServiceStub()


@pytest_asyncio.fixture
async def issue_finder_updater_stub():
    return IssueFinderServiceStub()


@pytest_asyncio.fixture
async def confluence_issue_updater_service(
    confluence_updater_stub, jira_updater_stub, issue_finder_updater_stub
):
    return SyncProjectService(
        confluence_api=confluence_updater_stub,
        jira_api=jira_updater_stub,
        issue_finder_service=issue_finder_updater_stub,
    )


# --- Tests ---


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_success(
    confluence_issue_updater_service, confluence_updater_stub, jira_updater_stub, monkeypatch
):
    root_url, root_page_id, root_project_key = "http://example.com/page1", "page1", "NEWPROJ-1"
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")
    monkeypatch.setattr(config, "JIRA_WORK_CONTAINER_ISSUE_TYPE_ID", "10003")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    confluence_updater_stub.set_page_content(root_page_id, '<p>Old macro: <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-PHASE-1</ac:parameter></ac:structured-macro></p>')
    # No need to add issue types to the stub for the refactored code
    jira_updater_stub.add_issue("OLD-PHASE-1", {"key": "OLD-PHASE-1", "fields": {"summary": "Matchable Summary", "issuetype": {"id": "10001", "name": "Phase"}}})
    candidate_issue = {"key": "NEWPROJ-PHASE-1", "fields": {"summary": "Matchable Summary", "issuetype": {"id": "10001", "name": "Phase"}}}

    # --- THIS IS THE FIX ---
    # Construct the JQL query using IDs, exactly as the refactored service does.
    raw_ids = [
        config.JIRA_PHASE_ISSUE_TYPE_ID,
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID,
        config.JIRA_WORK_CONTAINER_ISSUE_TYPE_ID,
    ]
    # Then, create a new list that filters out the None values before sorting.
    target_ids = sorted([issue_id for issue_id in raw_ids if issue_id is not None])

    type_ids_str = ", ".join(target_ids)
    jql = (
        f"issuetype in ({type_ids_str}) "
        f"AND issue in relation('{root_project_key}', 'Project Children', 'all')"
    )
    # -----------------------

    jira_updater_stub.add_jql_result(jql, [candidate_issue])

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )

    # After the refactor, the result will be a SinglePageResult object
    successful_results = [r for r in results if r.status == "Success"]
    assert len(successful_results) == 1
    assert successful_results[0].page_id == root_page_id
    assert "NEWPROJ-PHASE-1" in successful_results[0].new_jira_keys
    assert "NEWPROJ-PHASE-1" in confluence_updater_stub._updated_pages[root_page_id]["body"]


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_no_candidate_issues(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    root_url = "http://example.com/page1"
    root_page_id = "page1"
    root_project_key = "NONEXISTENT-PROJ"

    # Fixed: Use 'config' directly
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")

    confluence_updater_stub.set_page_content(
        root_page_id,
        '<p>Old Jira macro: <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLDPROJ-1</ac:parameter></ac:structured-macro></p>',
    )

    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )

    project_type_name = jira_updater_stub._issue_types[
        config.JIRA_PROJECT_ISSUE_TYPE_ID
    ]["name"]
    phase_type_name = jira_updater_stub._issue_types[config.JIRA_PHASE_ISSUE_TYPE_ID][
        "name"
    ]
    work_package_type_name = jira_updater_stub._issue_types[
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID
    ]["name"]
    issue_type_names_sorted = sorted(
        [
            f'"{phase_type_name}"',
            f'"{project_type_name}"',
            f'"{work_package_type_name}"',
        ]
    )
    jql_query_for_candidates = (
        f"issuetype in ({', '.join(issue_type_names_sorted)}) "
        f"AND issue in relation('{root_project_key}', '', 'all')"
    )
    jira_updater_stub.add_jql_result(jql_query_for_candidates, {"issues": []})

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )

    assert len(results) == 0
    assert not confluence_updater_stub._updated_pages


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_no_macros_on_page(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    root_url = "http://example.com/page1"
    root_page_id = "page1"
    root_project_key = "NEWPROJ-1"

    # Fixed: Use 'config' directly
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")

    confluence_updater_stub.set_page_content(
        root_page_id, "<p>Some text with no Jira macros.</p>"
    )

    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )

    project_type_name = jira_updater_stub._issue_types[
        config.JIRA_PROJECT_ISSUE_TYPE_ID
    ]["name"]
    phase_type_name = jira_updater_stub._issue_types[config.JIRA_PHASE_ISSUE_TYPE_ID][
        "name"
    ]
    work_package_type_name = jira_updater_stub._issue_types[
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID
    ]["name"]
    issue_type_names_sorted = sorted(
        [
            f'"{phase_type_name}"',
            f'"{project_type_name}"',
            f'"{work_package_type_name}"',
        ]
    )
    jql_query_for_candidates = (
        f"issuetype in ({', '.join(issue_type_names_sorted)}) "
        f"AND issue in relation('{root_project_key}', '', 'all')"
    )
    jira_updater_stub.add_jql_result(
        jql_query_for_candidates,
        {
            "issues": [
                {
                    "key": root_project_key,
                    "fields": {
                        "summary": "New Project Summary",
                        "issuetype": {
                            "id": config.JIRA_PROJECT_ISSUE_TYPE_ID,
                            "name": "Project",
                        },
                        "status": {
                            "name": "New Status",
                            "statusCategory": {"key": "new"},
                        },
                    },
                },
            ]
        },
    )

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )

    assert len(results) == 0
    assert not confluence_updater_stub._updated_pages


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_macro_no_match(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    root_url = "http://example.com/page1"
    root_page_id = "page1"
    root_project_key = "NEWPROJ-1"

    # Fixed: Use 'config' directly
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    confluence_updater_stub.set_page_content(
        root_page_id,
        '<p>Old Jira macro: <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLDPROJ-NOMATCH</ac:parameter></ac:structured-macro></p>',
    )

    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )

    old_nomatch_issue_data = {
        "key": "OLDPROJ-NOMATCH",
        "fields": {
            "summary": "Completely Different Summary That Will Not Match",
            "issuetype": {"id": config.JIRA_PROJECT_ISSUE_TYPE_ID, "name": "Project"},
            "status": {"name": "Old Status", "statusCategory": {"key": "new"}},
        },
    }
    jira_updater_stub.add_issue("OLDPROJ-NOMATCH", old_nomatch_issue_data)

    project_type_name = jira_updater_stub._issue_types[
        config.JIRA_PROJECT_ISSUE_TYPE_ID
    ]["name"]
    phase_type_name = jira_updater_stub._issue_types[config.JIRA_PHASE_ISSUE_TYPE_ID][
        "name"
    ]
    work_package_type_name = jira_updater_stub._issue_types[
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID
    ]["name"]
    issue_type_names_sorted = sorted(
        [
            f'"{phase_type_name}"',
            f'"{project_type_name}"',
            f'"{work_package_type_name}"',
        ]
    )
    jql_query_for_candidates = (
        f"issuetype in ({', '.join(issue_type_names_sorted)}) "
        f"AND issue in relation('{root_project_key}', '', 'all')"
    )
    jira_updater_stub.add_jql_result(
        jql_query_for_candidates,
        {
            "issues": [
                {
                    "key": root_project_key,
                    "fields": {
                        "summary": "A New Project Summary That Is Distinct",
                        "issuetype": {
                            "id": config.JIRA_PROJECT_ISSUE_TYPE_ID,
                            "name": "Project",
                        },
                        "status": {
                            "name": "New Status",
                            "statusCategory": {"key": "new"},
                        },
                    },
                },
            ]
        },
    )

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )

    assert len(results) == 0
    assert not confluence_updater_stub._updated_pages


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_update_page_fails(
    confluence_issue_updater_service, confluence_updater_stub, jira_updater_stub, monkeypatch
):
    """
    Tests that if confluence_api.update_page_content fails, the service returns
    a result object with a 'Failed' status.
    """
    root_url = "http://example.com/page1"
    root_page_id = "page1"
    root_project_key = "NEWPROJ-FAIL"

    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")
    monkeypatch.setattr(config, "JIRA_WORK_CONTAINER_ISSUE_TYPE_ID", "10003")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    confluence_updater_stub.set_page_content(root_page_id, '<p>Old macro: <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-PHASE-TO-FAIL</ac:parameter></ac:structured-macro></p>')
    # Configure the stub to simulate a failure on the update call
    confluence_updater_stub.set_update_success(False)

    jira_updater_stub.add_issue("OLD-PHASE-TO-FAIL", {"key": "OLD-PHASE-TO-FAIL", "fields": {"summary": "Phase For Failure Test", "issuetype": {"id": "10001", "name": "Phase"}}})
    candidate_issue = {"key": "NEWPROJ-FAIL-KEY", "fields": {"summary": "Phase For Failure Test", "issuetype": {"id": "10001", "name": "Phase"}}}

    raw_ids = [
        config.JIRA_PHASE_ISSUE_TYPE_ID,
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID,
        config.JIRA_WORK_CONTAINER_ISSUE_TYPE_ID,
    ]
    target_ids = sorted([issue_id for issue_id in raw_ids if issue_id is not None])
    type_ids_str = ", ".join(target_ids)
    jql = (
        f"issuetype in ({type_ids_str}) "
        f"AND issue in relation('{root_project_key}', 'Project Children', 'all')"
    )

    jira_updater_stub.add_jql_result(jql, [candidate_issue])

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )

    # The service should now return one result object indicating the failure.
    assert len(results) == 1

    failed_result = results[0]
    assert failed_result.page_id == root_page_id
    assert failed_result.status == "Failed - updating failed unexpectedly"

    # We can also still confirm that an update was *attempted*.
    assert root_page_id in confluence_updater_stub._updated_pages


@pytest.mark.asyncio
async def test_replace_page_macros_jira_bulk_fetch_fails(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    """
    Tests that if the bulk fetch for existing Jira macros' details fails, those macros are skipped
    and no modifications are reported for that page.
    """
    page_id = "page-with-failing-macro"
    html_content = (
        "<p>Macro with failing fetch: "
        '<ac:structured-macro ac:name="jira" ac:macro-id="fail-1">'
        '<ac:parameter ac:name="key">FAIL-KEY</ac:parameter>'
        "</ac:structured-macro>.</p>"
        "<p>Another macro: "
        '<ac:structured-macro ac:name="jira" ac:macro-id="pass-1">'
        '<ac:parameter ac:name="key">PASS-KEY</ac:parameter>'
        "</ac:structured-macro>.</p>"
    )
    page_title = "Page with Failing Fetch"

    candidate_new_issues = [
        {
            "key": "NEW-FAIL",
            "fields": {
                "issuetype": {"id": "10000", "name": "Project"},
                "summary": "New Fail Project",
                "status": {"name": "New Status", "category": "new"},
            },
        },
        {
            "key": "NEW-PASS",
            "fields": {
                "issuetype": {"id": "10000", "name": "Project"},
                "summary": "New Pass Project",
                "status": {"name": "New Status", "category": "new"},
            },
        },
    ]
    target_issue_type_ids = {"10000"}

    # Fixed: Use 'config' directly
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    failing_jql_exact = "issue in ('FAIL-KEY','PASS-KEY')"
    jira_updater_stub.set_search_issues_exception(failing_jql_exact)

    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )

    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=candidate_new_issues,
        target_issue_type_ids=target_issue_type_ids,
    )

    assert did_modify is False
    assert 'ac:parameter ac:name="key">FAIL-KEY</ac:parameter>' in modified_html
    assert 'ac:parameter ac:name="key">PASS-KEY</ac:parameter>' in modified_html
    assert 'ac:parameter ac:name="key">NEW-FAIL</ac:parameter>' not in modified_html
    assert 'ac:parameter ac:name="key">NEW-PASS</ac:parameter>' not in modified_html


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_page_details_none(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    root_url = "http://example.com/page1"
    root_project_key = "NEWPROJ-1"
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    # Simulate get_page_by_id returning None
    confluence_updater_stub._pages_content = {}
    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )
    project_type_name = jira_updater_stub._issue_types[
        config.JIRA_PROJECT_ISSUE_TYPE_ID
    ]["name"]
    phase_type_name = jira_updater_stub._issue_types[config.JIRA_PHASE_ISSUE_TYPE_ID][
        "name"
    ]
    work_package_type_name = jira_updater_stub._issue_types[
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID
    ]["name"]
    issue_type_names_sorted = sorted(
        [
            f'"{phase_type_name}"',
            f'"{project_type_name}"',
            f'"{work_package_type_name}"',
        ]
    )
    jql_query_for_candidates = (
        f"issuetype in ({', '.join(issue_type_names_sorted)}) "
        f"AND issue in relation('{root_project_key}', '', 'all')"
    )
    jira_updater_stub.add_jql_result(jql_query_for_candidates, {"issues": []})

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )
    assert results == []


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_page_content_empty(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    root_url = "http://example.com/page1"
    root_page_id = "page1"
    root_project_key = "NEWPROJ-1"
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    confluence_updater_stub.set_page_content(root_page_id, "")
    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )
    project_type_name = jira_updater_stub._issue_types[
        config.JIRA_PROJECT_ISSUE_TYPE_ID
    ]["name"]
    phase_type_name = jira_updater_stub._issue_types[config.JIRA_PHASE_ISSUE_TYPE_ID][
        "name"
    ]
    work_package_type_name = jira_updater_stub._issue_types[
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID
    ]["name"]
    issue_type_names_sorted = sorted(
        [
            f'"{phase_type_name}"',
            f'"{project_type_name}"',
            f'"{work_package_type_name}"',
        ]
    )
    jql_query_for_candidates = (
        f"issuetype in ({', '.join(issue_type_names_sorted)}) "
        f"AND issue in relation('{root_project_key}', '', 'all')"
    )
    jira_updater_stub.add_jql_result(jql_query_for_candidates, {"issues": []})

    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )
    assert results == []


@pytest.mark.asyncio
async def test_replace_page_macros_macro_no_key_param(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    page_id = "page1"
    html_content = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="notkey">VAL</ac:parameter></ac:structured-macro>'
    page_title = f"Page {page_id}"
    candidate_new_issues = []
    target_issue_type_ids = {"10000"}
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=candidate_new_issues,
        target_issue_type_ids=target_issue_type_ids,
    )
    assert did_modify is False
    assert '<ac:parameter ac:name="notkey">VAL</ac:parameter>' in modified_html


@pytest.mark.asyncio
async def test_replace_page_macros_macro_key_empty(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    page_id = "page1"
    html_content = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key"></ac:parameter></ac:structured-macro>'
    page_title = f"Page {page_id}"
    candidate_new_issues = []
    target_issue_type_ids = {"10000"}
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=candidate_new_issues,
        target_issue_type_ids=target_issue_type_ids,
    )
    assert did_modify is False
    assert '<ac:parameter ac:name="key"></ac:parameter>' in modified_html


@pytest.mark.asyncio
async def test_replace_page_macros_macro_issue_type_not_target(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    page_id = "page1"
    html_content = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">ISSUE-1</ac:parameter></ac:structured-macro>'
    page_title = f"Page {page_id}"
    candidate_new_issues = []
    target_issue_type_ids = {"10000"}
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    # Add issue with non-target type
    jira_updater_stub.add_issue(
        "ISSUE-1",
        {
            "key": "ISSUE-1",
            "fields": {
                "summary": "Summary",
                "issuetype": {"id": "99999", "name": "NonTarget"},
            },
        },
    )
    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=candidate_new_issues,
        target_issue_type_ids=target_issue_type_ids,
    )
    assert did_modify is False
    assert "ISSUE-1" in modified_html


@pytest.mark.asyncio
async def test_find_best_match_candidate_type_mismatch(
    confluence_issue_updater_service, monkeypatch
):
    old_issue_details = {
        "fields": {
            "issuetype": {"id": "10000", "name": "Project"},
            "summary": "Summary",
        }
    }
    candidate_new_issues = [
        {
            "fields": {
                "issuetype": {"id": "99999", "name": "Other"},
                "summary": "Summary",
            }
        }
    ]
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    result = confluence_issue_updater_service._find_best_match(
        old_issue_details, candidate_new_issues
    )
    assert result is None


@pytest.mark.asyncio
async def test_find_best_match_both_summaries_empty(
    confluence_issue_updater_service, monkeypatch
):
    old_issue_details = {
        "fields": {
            "issuetype": {"id": "10000", "name": "Project"},
            "summary": "",
        }
    }
    candidate_new_issues = [
        {"fields": {"issuetype": {"id": "10000", "name": "Project"}, "summary": ""}}
    ]
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    result = confluence_issue_updater_service._find_best_match(
        old_issue_details, candidate_new_issues
    )
    assert result is not None


@pytest.mark.asyncio
async def test_replace_page_macros_best_match_no_key(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    page_id = "page1"
    html_content = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">ISSUE-1</ac:parameter></ac:structured-macro>'
    page_title = f"Page {page_id}"
    candidate_new_issues = [
        {
            "fields": {
                "issuetype": {"id": "10000", "name": "Project"},
                "summary": "Summary",
            }
        }
    ]
    target_issue_type_ids = {"10000"}
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    jira_updater_stub.add_issue(
        "ISSUE-1",
        {
            "key": "ISSUE-1",
            "fields": {
                "summary": "Summary",
                "issuetype": {"id": "10000", "name": "Project"},
            },
        },
    )
    # Patch _find_best_match to return candidate with no 'key'
    orig_find_best = confluence_issue_updater_service._find_best_match

    def fake_find_best(*args, **kwargs):
        return {
            "fields": {
                "issuetype": {"id": "10000", "name": "Project"},
                "summary": "Summary",
            }
        }

    confluence_issue_updater_service._find_best_match = fake_find_best
    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=candidate_new_issues,
        target_issue_type_ids=target_issue_type_ids,
    )
    confluence_issue_updater_service._find_best_match = orig_find_best
    assert did_modify is False
    assert "ISSUE-1" in modified_html


@pytest.mark.asyncio
async def test_replace_page_macros_no_macros(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    page_id = "page1"
    html_content = "<p>No macros here.</p>"
    page_title = f"Page {page_id}"
    candidate_new_issues = []
    target_issue_type_ids = {"10000"}
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=candidate_new_issues,
        target_issue_type_ids=target_issue_type_ids,
    )
    assert did_modify is False
    assert "No macros here." in modified_html


@pytest.mark.asyncio
async def test_replace_page_macros_candidates_none(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    """Test _replace_page_macros with candidate_new_issues=None."""
    page_id = "page1"
    html_content = '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">ISSUE-1</ac:parameter></ac:structured-macro>'
    page_title = f"Page {page_id}"
    target_issue_type_ids = {"10000"}
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)

    jira_updater_stub.add_issue(
        "ISSUE-1",
        {
            "key": "ISSUE-1",
            "fields": {
                "summary": "Summary",
                "issuetype": {"id": "10000", "name": "Project"},
            },
        },
    )

    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title=page_title,
        html_content=html_content,
        candidate_new_issues=[], # Set to empty list as per method signature
        target_issue_type_ids=target_issue_type_ids,
    )
    assert did_modify is False
    assert "ISSUE-1" in modified_html


@pytest.mark.asyncio
async def test_find_best_match_candidate_summary_none(
    confluence_issue_updater_service, monkeypatch
):
    old_issue_details = {
        "fields": {
            "issuetype": {"id": "10000", "name": "Project"},
            "summary": "Summary",
        }
    }
    candidate_new_issues = [
        {"fields": {"issuetype": {"id": "10000", "name": "Project"}, "summary": None}}
    ]
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.75)
    result = confluence_issue_updater_service._find_best_match(
        old_issue_details, candidate_new_issues
    )
    assert result is None


@pytest.mark.asyncio
async def test_update_confluence_hierarchy_with_empty_candidates(
    confluence_issue_updater_service,
    confluence_updater_stub,
    jira_updater_stub,
    monkeypatch,
):
    root_url = "http://example.com/page1"
    root_project_key = "EMPTY-CANDIDATES"
    monkeypatch.setattr(config, "JIRA_PROJECT_ISSUE_TYPE_ID", "10000")
    monkeypatch.setattr(config, "JIRA_PHASE_ISSUE_TYPE_ID", "10001")
    monkeypatch.setattr(config, "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10002")
    jira_updater_stub.add_issue_type(config.JIRA_PROJECT_ISSUE_TYPE_ID, "Project")
    jira_updater_stub.add_issue_type(config.JIRA_PHASE_ISSUE_TYPE_ID, "Phase")
    jira_updater_stub.add_issue_type(
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID, "Work Package"
    )
    project_type_name = jira_updater_stub._issue_types[
        config.JIRA_PROJECT_ISSUE_TYPE_ID
    ]["name"]
    phase_type_name = jira_updater_stub._issue_types[config.JIRA_PHASE_ISSUE_TYPE_ID][
        "name"
    ]
    work_package_type_name = jira_updater_stub._issue_types[
        config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID
    ]["name"]
    issue_type_names_sorted = sorted(
        [
            f'"{phase_type_name}"',
            f'"{project_type_name}"',
            f'"{work_package_type_name}"',
        ]
    )
    jql_query_for_candidates = (
        f"issuetype in ({', '.join(issue_type_names_sorted)}) "
        f"AND issue in relation('{root_project_key}', '', 'all')"
    )
    jira_updater_stub.add_jql_result(jql_query_for_candidates, {"issues": []})
    results = await confluence_issue_updater_service.sync_project(
        project_page_url=root_url, project_key=root_project_key
    )
    assert results == []

@pytest.mark.asyncio
async def test_replace_macros_skips_macro_with_no_key(
    confluence_issue_updater_service,
):
    """
    Tests that a Jira macro without a 'key' parameter is skipped during processing.
    This covers the branch where `macro_key_param` is None at line 180.
    """
    html_with_malformed_macro = (
        '<p>A malformed macro: '
        '<ac:structured-macro ac:name="jira">'
        # This parameter is not 'key'
        '<ac:parameter ac:name="summary">Some Summary</ac:parameter>'
        '</ac:structured-macro></p>'
    )

    (
        modified_html,
        did_modify,
    ) = await confluence_issue_updater_service._replace_page_macros(
        page_title="Test Page",
        html_content=html_with_malformed_macro,
        candidate_new_issues=[{"key": "NEW-123", "fields": {}}],
        target_issue_type_ids={"10001"},
    )

    # The service should not modify the HTML and should report no changes
    assert did_modify is False
    assert modified_html == html_with_malformed_macro

@pytest.mark.asyncio
async def test_update_hierarchy_raises_error_for_invalid_root_url(
    confluence_issue_updater_service, confluence_updater_stub
):
    """
    Tests that an InvalidInputError is raised if the root URL cannot be resolved.
    This covers the `if not root_page_id:` branch.
    """
    # The stub returns None for any URL without "page1" in it
    invalid_url = "http://example.com/invalid-page"

    with pytest.raises(InvalidInputError, match="Could not find page ID for URL"):
        await confluence_issue_updater_service.sync_project(
            project_page_url=invalid_url, project_key="ANY-PROJ"
        )

@pytest.mark.asyncio
async def test_get_relevant_issues_with_no_valid_type_ids(
    confluence_issue_updater_service, jira_updater_stub, caplog
):
    """
    Tests that the JQL query is not run if the target issue type IDs are invalid.
    This covers the `if not target_issue_type_ids:` branch in the refactored method.
    """
    # Clear any previously added issue types in the stub
    jira_updater_stub._issue_types = {}

    with caplog.at_level(logging.WARNING):
        # Pass an empty set for the target IDs
        candidates = await confluence_issue_updater_service._get_project_issues(
            root_key="ANY-PROJ", target_issue_type_ids=set()
        )

    # No candidates should be returned, and a warning should be logged.
    assert candidates == []
    assert "No target issue type IDs provided for JQL search" in caplog.text
