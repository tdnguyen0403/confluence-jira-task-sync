"""
Unit tests for the ConfluenceService class.
This module tests the high-level ConfluenceService, ensuring that it
correctly delegates all of its calls to the underlying SafeConfluenceApi
wrapper and returns the expected data.
"""

import pytest
from unittest.mock import Mock

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
        self.mock = Mock()
        # The real API needs a base_url, but our stub doesn't. We only define
        # it here to prevent AttributeError if any unexpected real method gets called.
        self.base_url = "http://stub.example.com"

    def get_page_id_from_url(self, url: str) -> str:
        self.mock.get_page_id_from_url(url)
        return "stubbed_page_id"

    def get_all_descendants(self, page_id: str) -> list:
        self.mock.get_all_descendants(page_id)
        return [{"id": "child1"}, {"id": "child2"}]

    def get_page_by_id(self, page_id: str, expand: str = None) -> dict:
        self.mock.get_page_by_id(page_id, expand=expand)
        return {"id": page_id, "title": "Stubbed Page", "version": {"number": 2}}

    # --- FIX WAS HERE ---
    # The method called by the service is `update_page`, not `update_page_content`.
    # We must override `update_page` to prevent the real implementation from running.
    def update_page(self, page_id: str, title: str, body: str, **kwargs) -> bool:
        self.mock.update_page(page_id, title, body, **kwargs)
        return True  # The service expects a boolean return

    def get_tasks_from_page(self, page_details: dict) -> list:
        self.mock.get_tasks_from_page(page_details)
        return [{"id": "task1", "status": "incomplete"}]

    def update_page_with_jira_links(self, page_id: str, mappings: list) -> dict:
        self.mock.update_page_with_jira_links(page_id, mappings)
        return {"id": page_id, "body": {"storage": {"value": "updated_body"}}}

    def create_page(self, **kwargs) -> dict:
        self.mock.create_page(**kwargs)
        return {"id": "new_stubbed_page", "title": kwargs.get("title")}

    def get_user_details_by_username(self, username: str) -> dict:
        self.mock.get_user_details_by_username(username)
        return {"username": username, "displayName": "Stubbed User"}


# --- Pytest Fixture ---
@pytest.fixture
def confluence_service_with_stub():
    """Provides a ConfluenceService instance with a stubbed API for testing."""
    safe_api_stub = SafeConfluenceApiStub()
    service = ConfluenceService(safe_api_stub)
    yield service, safe_api_stub.mock


# --- Pytest Test Functions ---


def test_get_page_id_from_url(confluence_service_with_stub):
    """Verify get_page_id_from_url calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    test_url = "http://confluence.example.com/pages/12345"
    result = service.get_page_id_from_url(test_url)
    mock_api.get_page_id_from_url.assert_called_once_with(test_url)
    assert result == "stubbed_page_id"


def test_get_all_descendants(confluence_service_with_stub):
    """Verify get_all_descendants calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_id = "12345"
    result = service.get_all_descendants(page_id)
    mock_api.get_all_descendants.assert_called_once_with(page_id)
    assert result == [{"id": "child1"}, {"id": "child2"}]


def test_get_page_by_id(confluence_service_with_stub):
    """Verify get_page_by_id calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_id = "12345"
    result = service.get_page_by_id(page_id, expand="version")
    mock_api.get_page_by_id.assert_called_once_with(page_id, expand="version")
    assert result["id"] == page_id


def test_update_page_content(confluence_service_with_stub):
    """Verify update_page_content calls the underlying api's update_page method."""
    service, mock_api = confluence_service_with_stub
    page_id, title, body = "12345", "New Title", "<p>New Body</p>"
    result = service.update_page_content(page_id, title, body)

    # Assert that the correct method on the mock was called
    mock_api.update_page.assert_called_once_with(page_id, title, body)
    # Assert that the service returned the value from the stub
    assert result is True


def test_get_tasks_from_page(confluence_service_with_stub):
    """Verify get_tasks_from_page calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_details = {"id": "12345"}
    result = service.get_tasks_from_page(page_details)
    mock_api.get_tasks_from_page.assert_called_once_with(page_details)
    assert result[0]["id"] == "task1"


def test_update_page_with_jira_links(confluence_service_with_stub):
    """Verify update_page_with_jira_links calls the api."""
    service, mock_api = confluence_service_with_stub
    page_id = "12345"
    mappings = [{"confluence_task_id": "t1", "jira_key": "PROJ-1"}]
    service.update_page_with_jira_links(page_id, mappings)
    mock_api.update_page_with_jira_links.assert_called_once_with(page_id, mappings)


def test_create_page(confluence_service_with_stub):
    """Verify create_page calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    page_args = {"space": "TEST", "title": "My Page", "parent_id": "123"}
    result = service.create_page(**page_args)
    mock_api.create_page.assert_called_once_with(**page_args)
    assert result["title"] == "My Page"


def test_get_user_details_by_username(confluence_service_with_stub):
    """Verify get_user_details_by_username calls the api and returns its data."""
    service, mock_api = confluence_service_with_stub
    username = "testuser"
    result = service.get_user_details_by_username(username)
    mock_api.get_user_details_by_username.assert_called_once_with(username)
    assert result["displayName"] == "Stubbed User"
