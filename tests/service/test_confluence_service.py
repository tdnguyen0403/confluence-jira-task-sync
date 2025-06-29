"""
Unit tests for the ConfluenceService class.

This module tests the high-level ConfluenceService, ensuring that it
correctly delegates all of its calls to the underlying SafeConfluenceApi
wrapper.
"""

import logging
import os
import sys
import unittest
from unittest.mock import Mock

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.safe_confluence_api import SafeConfluenceApi
from src.services.confluence_service import ConfluenceService

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestConfluenceService(unittest.TestCase):
    """Tests the ConfluenceService delegation logic."""

    def setUp(self):
        """Set up a mock SafeConfluenceApi and the service for each test."""
        self.mock_safe_api = Mock(spec=SafeConfluenceApi)
        self.confluence_service = ConfluenceService(self.mock_safe_api)

    def test_get_page_id_from_url_delegates(self):
        """Verify get_page_id_from_url calls the underlying api method."""
        test_url = "http://confluence.example.com/pages/12345"
        self.confluence_service.get_page_id_from_url(test_url)
        self.mock_safe_api.get_page_id_from_url.assert_called_once_with(test_url)

    def test_get_all_descendants_delegates(self):
        """Verify get_all_descendants calls the underlying api method."""
        page_id = "12345"
        self.confluence_service.get_all_descendants(page_id)
        self.mock_safe_api.get_all_descendants.assert_called_once_with(page_id)

    def test_get_page_by_id_delegates(self):
        """Verify get_page_by_id calls the underlying api method."""
        page_id = "12345"
        self.confluence_service.get_page_by_id(page_id, expand="version")
        self.mock_safe_api.get_page_by_id.assert_called_once_with(
            page_id, expand="version"
        )

    def test_update_page_content_delegates(self):
        """Verify update_page_content calls the underlying api method."""
        page_id = "12345"
        title = "New Title"
        body = "<p>New Body</p>"
        self.confluence_service.update_page_content(page_id, title, body)
        self.mock_safe_api.update_page.assert_called_once_with(page_id, title, body)

    def test_get_tasks_from_page_delegates(self):
        """Verify get_tasks_from_page calls the underlying api method."""
        page_details = {"id": "12345", "body": {"storage": {"value": ""}}}
        self.confluence_service.get_tasks_from_page(page_details)
        self.mock_safe_api.get_tasks_from_page.assert_called_once_with(page_details)

    def test_update_page_with_jira_links_delegates(self):
        """Verify update_page_with_jira_links calls the underlying api method."""
        page_id = "12345"
        mappings = [{"confluence_task_id": "t1", "jira_key": "PROJ-1"}]
        self.confluence_service.update_page_with_jira_links(page_id, mappings)
        self.mock_safe_api.update_page_with_jira_links.assert_called_once_with(
            page_id, mappings
        )

    def test_create_page_delegates(self):
        """Verify create_page calls the underlying api method."""
        page_args = {"space": "TEST", "title": "My Page", "parent_id": "123"}
        self.confluence_service.create_page(**page_args)
        self.mock_safe_api.create_page.assert_called_once_with(**page_args)

    def test_get_user_details_by_username_delegates(self):
        """Verify get_user_details_by_username calls the underlying api method."""
        username = "testuser"
        self.confluence_service.get_user_details_by_username(username)
        self.mock_safe_api.get_user_details_by_username.assert_called_once_with(
            username
        )


if __name__ == "__main__":
    unittest.main()
