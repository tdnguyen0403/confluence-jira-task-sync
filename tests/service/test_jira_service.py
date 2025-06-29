"""
Unit tests for the JiraService class.

This module tests the high-level JiraService, ensuring that it correctly
handles business logic and delegates calls to its underlying API wrapper.
"""

import logging
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.safe_jira_api import SafeJiraApi
from src.models.data_models import ConfluenceTask
from src.services.jira_service import JiraService

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestJiraService(unittest.TestCase):
    """Tests the high-level JiraService."""

    def setUp(self):
        """Set up a mock SafeJiraApi and the service for each test."""
        self.mock_safe_api = Mock(spec=SafeJiraApi)
        self.jira_service = JiraService(self.mock_safe_api)

    def test_get_issue_delegates_to_safe_api(self):
        """Verify get_issue calls the underlying safe_api method."""
        self.jira_service.get_issue("TEST-123")
        self.mock_safe_api.get_issue.assert_called_once_with("TEST-123", "*all")

    def test_get_current_user_display_name_success_and_cache(self):
        """Test that the user's display name is fetched and then cached."""
        self.mock_safe_api.get_myself.return_value = {"displayName": "Test User"}

        # First call should hit the API.
        name1 = self.jira_service.get_current_user_display_name()
        self.assertEqual(name1, "Test User")
        self.mock_safe_api.get_myself.assert_called_once()

        # Second call should use the cached value, not call the API again.
        name2 = self.jira_service.get_current_user_display_name()
        self.assertEqual(name2, "Test User")
        self.mock_safe_api.get_myself.assert_called_once()  # Count remains 1.

    def test_get_current_user_display_name_failure(self):
        """Test the fallback to 'Unknown User' when the API fails."""
        self.mock_safe_api.get_myself.return_value = None
        name = self.jira_service.get_current_user_display_name()
        self.assertEqual(name, "Unknown User")

    @patch("src.services.jira_service.datetime")
    def test_prepare_jira_task_fields_dynamically_extracts_project_key(
        self, mock_datetime
    ):
        """
        Test that `prepare_jira_task_fields` dynamically extracts the project
        key from the parent issue key.
        """
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        self.jira_service.get_current_user_display_name = Mock(
            return_value="Test User"
        )
        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="My Summary",
            status="incomplete",
            assignee_name="assignee",
            due_date="2025-01-15",
            original_page_version=1,
            original_page_version_by="author",
            original_page_version_when="now",
            context="This is the context.",
        )
        # The parent key is "PROJ-123", so the project key should be "PROJ".
        parent_key = "PROJ-123"

        # Act
        result = self.jira_service.prepare_jira_task_fields(mock_task, parent_key)

        # Assert
        # Verify the project key is extracted correctly.
        self.assertEqual(result["fields"]["project"]["key"], "PROJ")

        # Verify other fields remain correct.
        self.assertEqual(result["fields"]["summary"], "My Summary")
        expected_description = (
            "Context from Confluence:\nThis is the context.\n\n"
            "Created by Test User on 2025-01-01 12:00:00"
        )
        self.assertEqual(result["fields"]["description"], expected_description)

if __name__ == "__main__":
    unittest.main()
