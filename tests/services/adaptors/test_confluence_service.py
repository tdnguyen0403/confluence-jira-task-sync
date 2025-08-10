"""
Unit tests for the ConfluenceService class.
This module tests the high-level ConfluenceService, ensuring that it
correctly delegates all of its calls to the underlying SafeConfluenceApi
wrapper and returns the expected data.
"""

from unittest.mock import AsyncMock  # <--- CHANGE THIS LINE: Import AsyncMock

import pytest
import pytest_asyncio

# Assuming your project structure allows this import path
from src.api.safe_confluence_api import SafeConfluenceApi
from src.services.adaptors.confluence_service import ConfluenceService


# --- Stub for the underlying API ---
# This stub replaces the real API, preventing actual network calls.
class SafeConfluenceApiStub(SafeConfluenceApi):
    def __init__(self):
        """
        Override the parent __init__ to prevent it from creating a real client.
        The 'mock' attribute is used to track calls for our assertions.
        """
        # CHANGE THIS LINE: Use AsyncMock instead of Mock
        self.mock = AsyncMock()
        self.base_url = "http://stub.example.com"
        self.jira_macro_server_name = "Mock Jira Server"
        self.jira_macro_server_id = "mock-server-id"

    async def get_page_id_from_url(self, url: str) -> str:
        # Now self.mock.get_page_id_from_url is an AsyncMock, so awaiting it is valid
        await self.mock.get_page_id_from_url(url)
        return "stubbed_page_id"

    async def get_all_descendants(self, page_id: str) -> list:
        await self.mock.get_all_descendants(page_id)
        return [{"id": "child1"}, {"id": "child2"}]

    async def get_page_by_id(self, page_id: str, expand: str = None) -> dict:
        await self.mock.get_page_by_id(page_id, expand=expand)
        return {"id": page_id, "title": "Stubbed Page", "version": {"number": 2}}

    async def update_page(self, page_id: str, title: str, body: str, **kwargs) -> bool:
        await self.mock.update_page(page_id, title, body, **kwargs)
        return True

    async def get_tasks_from_page(self, page_details: dict) -> list:
        await self.mock.get_tasks_from_page(page_details)
        return [{"id": "task1", "status": "incomplete"}]

    async def update_page_with_jira_links(self, page_id: str, mappings: list) -> dict:
        await self.mock.update_page_with_jira_links(page_id, mappings)
        return {"id": page_id, "body": {"storage": {"value": "updated_body"}}}

    async def create_page(self, **kwargs) -> dict:
        await self.mock.create_page(**kwargs)
        return {"id": "new_stubbed_page", "title": kwargs.get("title")}

    async def get_user_by_username(self, username: str) -> dict:
        await self.mock.get_user_by_username(username)
        return {"username": username, "displayName": "Stubbed User"}

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        return (
            f'<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="some-id">'
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f'<ac:parameter ac:name="server">{self.jira_macro_server_name}</ac:parameter>'
            f'<ac:parameter ac:name="serverId">{self.jira_macro_server_id}</ac:parameter>'
            f'<ac:parameter ac:name="columns">key,summary,status</ac:parameter>'
            f"</ac:structured-macro>"
        )


# --- Pytest Fixture ---
@pytest_asyncio.fixture
async def confluence_service_with_stub():
    """Provides a ConfluenceService instance with a stubbed API for testing."""
    safe_api_stub = SafeConfluenceApiStub()
    service = ConfluenceService(safe_api_stub)
    yield service, safe_api_stub.mock


# --- Pytest Test Functions ---


@pytest.mark.asyncio
async def test_get_page_id_from_url(confluence_service_with_stub):
    """Verify get_page_id_from_url calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    test_url = "http://confluence.example.com/pages/12345"
    result = await service.get_page_id_from_url(test_url)
    mock_api.get_page_id_from_url.assert_called_once_with(test_url)
    assert result == "stubbed_page_id"


@pytest.mark.asyncio
async def test_get_all_descendants(confluence_service_with_stub):
    """Verify get_all_descendants calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_id = "12345"
    result = await service.get_all_descendants(page_id)
    mock_api.get_all_descendants.assert_called_once_with(page_id)
    assert result == [{"id": "child1"}, {"id": "child2"}]


@pytest.mark.asyncio
async def test_get_page_by_id(confluence_service_with_stub):
    """Verify get_page_by_id calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_id = "12345"
    result = await service.get_page_by_id(page_id, expand="version")
    mock_api.get_page_by_id.assert_called_once_with(page_id, expand="version")
    assert result["id"] == page_id


@pytest.mark.asyncio
async def test_update_page_content(confluence_service_with_stub):
    """Verify update_page_content calls the underlying api's update_page method."""
    service, mock_api = confluence_service_with_stub
    page_id, title, body = "12345", "New Title", "<p>New Body</p>"
    result = await service.update_page_content(page_id, title, body)

    mock_api.update_page.assert_called_once_with(page_id, title, body)
    assert result is True


@pytest.mark.asyncio
async def test_get_tasks_from_page(confluence_service_with_stub):
    """Verify get_tasks_from_page calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_details = {"id": "12345"}
    result = await service.get_tasks_from_page(page_details)
    mock_api.get_tasks_from_page.assert_called_once_with(page_details)
    assert result[0]["id"] == "task1"


@pytest.mark.asyncio
async def test_update_page_with_jira_links(confluence_service_with_stub):
    """Verify update_page_with_jira_links calls the api."""
    service, mock_api = confluence_service_with_stub
    page_id = "12345"
    mappings = [{"confluence_task_id": "t1", "jira_key": "PROJ-1"}]
    await service.update_page_with_jira_links(page_id, mappings)
    mock_api.update_page_with_jira_links.assert_called_once_with(page_id, mappings)


@pytest.mark.asyncio
async def test_create_page(confluence_service_with_stub):
    """Verify create_page calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_args = {"space": "TEST", "title": "My Page", "parent_id": "123"}
    result = await service.create_page(**page_args)
    mock_api.create_page.assert_called_once_with(**page_args)
    assert result["title"] == "My Page"


@pytest.mark.asyncio
async def test_get_user_by_username(confluence_service_with_stub):
    """Verify get_user_by_username calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    username = "testuser"
    result = await service.get_user_by_username(username)
    mock_api.get_user_by_username.assert_called_once_with(username)
    assert result["displayName"] == "Stubbed User"
