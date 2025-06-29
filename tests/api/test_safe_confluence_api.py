"""
Unit tests for the SafeConfluenceApi class.

This module tests the low-level SafeConfluenceApi, which is responsible for
direct communication with the Confluence API. The tests verify both the
primary (library-based) and fallback (direct REST call) mechanisms, as well
as the HTML parsing logic for task extraction.
"""

import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests
from atlassian import Confluence

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.safe_confluence_api import SafeConfluenceApi

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestSafeConfluenceApi(unittest.TestCase):
    """Tests the low-level SafeConfluenceApi."""

    def setUp(self):
        """Set up a mock Confluence client before each test."""
        self.mock_confluence_client = MagicMock(spec=Confluence)
        self.safe_confluence_api = SafeConfluenceApi(self.mock_confluence_client)

    def test_get_page_by_id_primary_success(self):
        """Test get_page_by_id successful call using the library."""
        self.mock_confluence_client.get_page_by_id.return_value = {"id": "123"}
        result = self.safe_confluence_api.get_page_by_id("123")
        self.assertEqual(result["id"], "123")
        self.mock_confluence_client.get_page_by_id.assert_called_once_with("123")

    @patch("src.api.safe_confluence_api.requests.get")
    def test_get_page_by_id_fallback_failure(self, mock_get):
        """Test get_page_by_id when both primary and fallback attempts fail."""
        self.mock_confluence_client.get_page_by_id.side_effect = Exception("API Error")
        mock_get.side_effect = requests.exceptions.RequestException("Network Error")
        result = self.safe_confluence_api.get_page_by_id("FAIL-123")
        self.assertIsNone(result)

    def test_get_all_descendants_recursive(self):
        """Test that get_all_descendants recursively finds all child pages."""
        # Mock the API to simulate a three-level page hierarchy.
        self.safe_confluence_api.get_page_child_by_type = Mock(
            side_effect=[
                [{"id": "child1"}, {"id": "child2"}],  # Children of root
                [{"id": "grandchild1"}],  # Children of child1
                [],  # Children of grandchild1
                [],  # Children of child2
            ]
        )
        descendants = self.safe_confluence_api.get_all_descendants("root")
        self.assertEqual(len(descendants), 3)
        self.assertIn("child1", descendants)
        self.assertIn("child2", descendants)
        self.assertIn("grandchild1", descendants)
        self.assertEqual(self.safe_confluence_api.get_page_child_by_type.call_count, 4)

    def test_get_tasks_from_page_various_scenarios(self):
        """Test task parsing from a complex HTML body."""
        html_content = """
            <ac:task-list>
                <ac:task>
                    <ac:task-id>1</ac:task-id>
                    <ac:task-status>incomplete</ac:task-status>
                    <ac:task-body>Task 1</ac:task-body>
                </ac:task>
                <ac:task>
                    <ac:task-id>2</ac:task-id>
                    <ac:task-status>complete</ac:task-status>
                    <ac:task-body>Task 2</ac:task-body>
                </ac:task>
                <ac:task>
                    <ac:task-id>3</ac:task-id>
                    <ac:task-status>incomplete</ac:task-status>
                    <ac:task-body><span>Task 3 with <time datetime="2025-12-31"></time> and <ri:user ri:userkey="123"></ri:user></span></ac:task-body>
                </ac:task>
            </ac:task-list>
        """
        page_details = {
            "id": "101",
            "title": "Test Page",
            "_links": {"webui": "/test-page"},
            "body": {"storage": {"value": html_content}},
            "version": {"number": 2, "by": {"displayName": "tester"}, "when": "now"},
        }

        # Mock the user lookup for the assigned task.
        self.safe_confluence_api.get_user_details_by_userkey = Mock(
            return_value={"username": "testuser"}
        )
        tasks = self.safe_confluence_api.get_tasks_from_page(page_details)

        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0].task_summary, "Task 1")
        self.assertEqual(tasks[1].status, "complete")
        self.assertEqual(tasks[2].task_summary, "Task 3 with and")
        self.assertEqual(tasks[2].assignee_name, "testuser")

    def test_get_tasks_from_page_no_body(self):
        """Test task parsing from a page with no body content."""
        page_details = {"id": "101"}  # Missing 'body' key
        tasks = self.safe_confluence_api.get_tasks_from_page(page_details)
        self.assertEqual(len(tasks), 0)


if __name__ == "__main__":
    unittest.main()
