# File: test_dependencies.py

from unittest.mock import AsyncMock

import httpx  # Import httpx here
import pytest
import pytest_asyncio

from src.api.https_helper import HTTPSHelper
from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi

# Import the functions to be tested
from src.dependencies import (
    get_confluence_issue_updater_service,
    get_confluence_service,
    get_https_helper,
    get_issue_finder_service,
    get_jira_service,
    get_safe_confluence_api,
    get_safe_jira_api,
    get_sync_task_orchestrator,
    get_undo_sync_task_orchestrator,
)
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.services.orchestration.confluence_issue_updater_service import (
    ConfluenceIssueUpdaterService,
)
from src.services.orchestration.sync_task_orchestrator import SyncTaskOrchestrator
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)


# Clear lru_cache for all *existing* functions before each test to ensure fresh instances
@pytest.fixture(autouse=True)
def clear_caches():
    # Only clear caches for functions that actually exist and are lru_cached
    get_https_helper.cache_clear()
    get_safe_confluence_api.cache_clear()
    get_safe_jira_api.cache_clear()
    get_confluence_service.cache_clear()
    get_jira_service.cache_clear()
    get_issue_finder_service.cache_clear()
    get_confluence_issue_updater_service.cache_clear()
    get_sync_task_orchestrator.cache_clear()
    get_undo_sync_task_orchestrator.cache_clear()


# Mock the _http_helper_instance singleton in src.dependencies
@pytest_asyncio.fixture
async def mock_https_helper(monkeypatch):
    # Create a mock for HTTPSHelper. Its 'client' attribute should also be a mock.
    mock_helper = AsyncMock(spec=HTTPSHelper)
    mock_helper.client = AsyncMock(
        spec=httpx.AsyncClient
    )  # Mock the internal httpx.AsyncClient

    # Patch the singleton instance in src.dependencies
    monkeypatch.setattr("src.dependencies._http_helper_instance", mock_helper)

    yield mock_helper
    # No explicit aclose call needed here, as the mock_helper.client is an AsyncMock
    # and its aclose would be called if the real HTTPSHelper's client.aclose were called.


# --- Tests for HTTPSHelper and API Wrappers ---


@pytest.mark.asyncio
async def test_get_https_helper(mock_https_helper):
    # This test now verifies that get_https_helper returns our mocked instance
    helper = get_https_helper()
    assert helper is mock_https_helper
    assert isinstance(helper, AsyncMock)
    assert isinstance(
        helper.client, AsyncMock
    )  # Ensure its internal client is also mocked

    # Test caching
    helper2 = get_https_helper()
    assert helper is helper2


@pytest.mark.asyncio
async def test_get_safe_confluence_api(mock_https_helper):
    # Manually inject the resolved dependency
    safe_api = get_safe_confluence_api(https_helper=get_https_helper())
    assert isinstance(safe_api, SafeConfluenceApi)
    # Check if SafeConfluenceApi was instantiated with the mocked HTTPSHelper
    assert safe_api.https_helper is mock_https_helper
    # Test caching
    safe_api2 = get_safe_confluence_api(https_helper=get_https_helper())
    assert safe_api is safe_api2


@pytest.mark.asyncio
async def test_get_safe_jira_api(mock_https_helper):
    # Manually inject the resolved dependency
    safe_api = get_safe_jira_api(https_helper=get_https_helper())
    assert isinstance(safe_api, SafeJiraApi)
    # Check if SafeJiraApi was instantiated with the mocked HTTPSHelper
    assert safe_api.https_helper is mock_https_helper
    # Test caching
    safe_api2 = get_safe_jira_api(https_helper=get_https_helper())
    assert safe_api is safe_api2


# --- Tests for Services ---


@pytest.mark.asyncio
async def test_get_confluence_service(mock_https_helper):
    # Manually inject the resolved dependency
    service = get_confluence_service(
        safe_confluence_api=get_safe_confluence_api(https_helper=get_https_helper())
    )
    assert isinstance(service, ConfluenceService)
    # Ensure it's using the cached SafeConfluenceApi instance, which in turn uses mock_https_helper
    safe_confluence_api_instance = get_safe_confluence_api(
        https_helper=get_https_helper()
    )
    assert service._api is safe_confluence_api_instance
    assert (
        service._api.https_helper is mock_https_helper
    )  # Verify the deeper dependency
    # Test caching
    service2 = get_confluence_service(
        safe_confluence_api=get_safe_confluence_api(https_helper=get_https_helper())
    )
    assert service is service2


@pytest.mark.asyncio
async def test_get_jira_service(mock_https_helper):
    # Manually inject the resolved dependency
    service = get_jira_service(
        safe_jira_api=get_safe_jira_api(https_helper=get_https_helper())
    )
    assert isinstance(service, JiraService)
    safe_jira_api_instance = get_safe_jira_api(https_helper=get_https_helper())
    assert service._api is safe_jira_api_instance
    assert (
        service._api.https_helper is mock_https_helper
    )  # Verify the deeper dependency
    # Test caching
    service2 = get_jira_service(
        safe_jira_api=get_safe_jira_api(https_helper=get_https_helper())
    )
    assert service is service2


@pytest.mark.asyncio
async def test_get_issue_finder_service(mock_https_helper):
    # Manually inject the resolved dependency
    jira_service_instance = get_jira_service(
        safe_jira_api=get_safe_jira_api(https_helper=get_https_helper())
    )
    service = get_issue_finder_service(jira_service=jira_service_instance)
    assert isinstance(service, IssueFinderService)
    assert service.jira_api is jira_service_instance


@pytest.mark.asyncio
async def test_get_confluence_issue_updater_service(mock_https_helper):
    # Manually inject all resolved dependencies
    confluence_service = get_confluence_service(
        safe_confluence_api=get_safe_confluence_api(https_helper=get_https_helper())
    )
    jira_service = get_jira_service(
        safe_jira_api=get_safe_jira_api(https_helper=get_https_helper())
    )
    # FIX: Pass the correct dependency to get_issue_finder_service
    issue_finder = get_issue_finder_service(jira_service=jira_service)

    service = get_confluence_issue_updater_service(
        confluence_service=confluence_service,
        jira_service=jira_service,
        issue_finder_service=issue_finder,
    )
    assert isinstance(service, ConfluenceIssueUpdaterService)
    assert service.confluence_api is confluence_service
    assert service.jira_api is jira_service
    assert service.issue_finder_service is issue_finder


@pytest.mark.asyncio
async def test_get_sync_task_orchestrator(mock_https_helper):
    # Arrange: Manually resolve all the necessary service-layer dependencies
    confluence_service = get_confluence_service(
        safe_confluence_api=get_safe_confluence_api(
            https_helper=get_https_helper()
        )
    )
    jira_service = get_jira_service(
        safe_jira_api=get_safe_jira_api(https_helper=get_https_helper())
    )
    issue_finder_service = get_issue_finder_service(jira_service=jira_service)

    # Act: Call the dependency provider with the correct arguments
    orchestrator = get_sync_task_orchestrator(
        confluence_service=confluence_service,
        jira_service=jira_service,
        issue_finder_service=issue_finder_service,
    )

    # Assert: Check the instance type and that dependencies were injected correctly
    assert isinstance(orchestrator, SyncTaskOrchestrator)
    assert orchestrator.confluence_service is confluence_service
    assert orchestrator.jira_service is jira_service
    assert orchestrator.issue_finder_service is issue_finder_service

    # Assert: Check that the lru_cache is working
    orchestrator2 = get_sync_task_orchestrator(
        confluence_service=confluence_service,
        jira_service=jira_service,
        issue_finder_service=issue_finder_service,
    )
    assert orchestrator is orchestrator2


@pytest.mark.asyncio
async def test_get_undo_sync_task_orchestrator(mock_https_helper):
    # Arrange: Manually resolve all the necessary service-layer dependencies
    confluence_service = get_confluence_service(
        safe_confluence_api=get_safe_confluence_api(
            https_helper=get_https_helper()
        )
    )
    jira_service = get_jira_service(
        safe_jira_api=get_safe_jira_api(https_helper=get_https_helper())
    )
    issue_finder_service = get_issue_finder_service(jira_service=jira_service)

    # Act: Call the dependency provider with the correct arguments
    orchestrator = get_undo_sync_task_orchestrator(
        confluence_service=confluence_service,
        jira_service=jira_service,
        issue_finder_service=issue_finder_service,
    )

    # Assert: Check the instance type and that dependencies were injected correctly
    assert isinstance(orchestrator, UndoSyncTaskOrchestrator)
    assert orchestrator.confluence_service is confluence_service
    assert orchestrator.jira_service is jira_service
    assert orchestrator.issue_finder_service is issue_finder_service

    # Assert: Check that the lru_cache is working
    orchestrator2 = get_undo_sync_task_orchestrator(
        confluence_service=confluence_service,
        jira_service=jira_service,
        issue_finder_service=issue_finder_service,
    )
    assert orchestrator is orchestrator2
