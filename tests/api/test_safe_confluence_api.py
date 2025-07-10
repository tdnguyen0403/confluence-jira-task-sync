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
        patcher_config_url = patch(
            "src.api.safe_confluence_api.config.CONFLUENCE_URL",
            "https://mock.confluence.com",
        )
        patcher_config_token = patch(
            "src.api.safe_confluence_api.config.CONFLUENCE_API_TOKEN", "mock_token"
        )
        patcher_config_macro_name = patch(
            "src.api.safe_confluence_api.config.JIRA_MACRO_SERVER_NAME", "Mock Jira"
        )
        patcher_config_macro_id = patch(
            "src.api.safe_confluence_api.config.JIRA_MACRO_SERVER_ID", "mock_server_id"
        )

        self.mock_config_url = patcher_config_url.start()
        self.mock_config_token = patcher_config_token.start()
        self.mock_config_macro_name = patcher_config_macro_name.start()
        self.mock_config_macro_id = patcher_config_macro_id.start()

        self.addCleanup(patcher_config_url.stop)
        self.addCleanup(patcher_config_token.stop)
        self.addCleanup(patcher_config_macro_name.stop)
        self.addCleanup(patcher_config_macro_id.stop)

        self.safe_confluence_api = SafeConfluenceApi(self.mock_confluence_client)

    @patch("src.api.safe_confluence_api.make_request")  # Patch the new helper function
    def test_get_page_by_id_primary_success(self, mock_make_request):
        """Test get_page_by_id successful call using the library (no fallback needed)."""
        self.mock_confluence_client.get_page_by_id.return_value = {"id": "123"}
        result = self.safe_confluence_api.get_page_by_id("123")
        self.assertEqual(result["id"], "123")
        self.mock_confluence_client.get_page_by_id.assert_called_once_with("123")
        mock_make_request.assert_not_called()  # Ensure fallback was not called

    @patch("src.api.safe_confluence_api.make_request")  # Patch the new helper function
    def test_get_page_by_id_fallback_success(self, mock_make_request):
        """Test get_page_by_id successful fallback after library failure."""
        self.mock_confluence_client.get_page_by_id.side_effect = Exception("API Error")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "FALLBACK-123",
            "title": "Fallback Page",
        }
        mock_make_request.return_value = mock_response

        result = self.safe_confluence_api.get_page_by_id(
            "FALLBACK-123", expand="body.storage"
        )

        self.assertEqual(result["id"], "FALLBACK-123")
        self.mock_confluence_client.get_page_by_id.assert_called_once_with(
            "FALLBACK-123", expand="body.storage"
        )
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_confluence_api.base_url}/rest/api/content/FALLBACK-123",
            headers=self.safe_confluence_api.headers,
            params={"expand": "body.storage"},
            verify_ssl=False,  # Assert this
        )

    @patch("src.api.safe_confluence_api.make_request")  # Patch the new helper function
    def test_get_page_by_id_fallback_failure(self, mock_make_request):
        """Test get_page_by_id when both primary and fallback attempts fail."""
        self.mock_confluence_client.get_page_by_id.side_effect = Exception("API Error")
        mock_make_request.return_value = None  # Simulate helper failure

        result = self.safe_confluence_api.get_page_by_id("FAIL-123")
        self.assertIsNone(result)
        self.mock_confluence_client.get_page_by_id.assert_called_once_with("FAIL-123")
        mock_make_request.assert_called_once()  # Verify helper was attempted

    @patch("src.api.safe_confluence_api.make_request")
    def test_get_page_child_by_type_fallback_success(self, mock_make_request):
        """Test get_page_child_by_type successful fallback."""
        self.mock_confluence_client.get_page_child_by_type.side_effect = Exception(
            "Library Error"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{"id": "child1"}, {"id": "child2"}]
        }
        mock_make_request.return_value = mock_response

        children = self.safe_confluence_api.get_page_child_by_type("parent-id", "page")

        self.assertEqual(len(children), 2)
        self.assertEqual(children[0]["id"], "child1")
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_confluence_api.base_url}/rest/api/content/parent-id/child/page",
            headers=self.safe_confluence_api.headers,
            verify_ssl=False,
        )
        self.mock_confluence_client.get_page_child_by_type.assert_called_once()

    @patch("src.api.safe_confluence_api.make_request")
    def test_update_page_fallback_success(self, mock_make_request):
        """Test update_page successful fallback."""
        self.mock_confluence_client.update_page.side_effect = Exception("Library Error")
        # Ensure that the get_page_by_id call inside _fallback_update_page also triggers its fallback
        self.mock_confluence_client.get_page_by_id.side_effect = Exception(
            "Mock Get Page Error to force fallback"
        )

        # Mock get_page_by_id used by the fallback to get current version
        mock_get_page_response = MagicMock()
        mock_get_page_response.json.return_value = {
            "id": "page-to-update",
            "title": "Old Title",
            "version": {"number": 5},
        }

        # Mock the actual update request via make_request
        mock_update_response = MagicMock()
        mock_update_response.status_code = 200  # Indicate success
        mock_make_request.side_effect = [
            mock_get_page_response,  # First call is from get_page_by_id inside fallback
            mock_update_response,  # Second call is the actual PUT update
        ]

        page_id = "page-to-update"
        new_title = "Updated Title"
        new_body = "New Content"
        result = self.safe_confluence_api.update_page(page_id, new_title, new_body)

        self.assertTrue(result)
        self.mock_confluence_client.update_page.assert_called_once()
        # Verify calls to make_request for both get_page_by_id and the actual PUT
        self.assertEqual(mock_make_request.call_count, 2)
        mock_make_request.assert_any_call(
            "GET",
            f"{self.safe_confluence_api.base_url}/rest/api/content/{page_id}",
            headers=self.safe_confluence_api.headers,
            params={"expand": "version"},
            verify_ssl=False,
        )
        mock_make_request.assert_any_call(
            "PUT",
            f"{self.safe_confluence_api.base_url}/rest/api/content/{page_id}",
            headers=self.safe_confluence_api.headers,
            json_data={
                "version": {"number": 6},  # Old version + 1
                "type": "page",
                "title": new_title,
                "body": {"storage": {"value": new_body, "representation": "storage"}},
            },
            verify_ssl=False,
        )

    @patch("src.api.safe_confluence_api.make_request")
    def test_create_page_fallback_success(self, mock_make_request):
        """Test create_page successful fallback."""
        self.mock_confluence_client.create_page.side_effect = Exception("Library Error")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "new-page-id",
            "title": "New Fallback Page",
        }
        mock_make_request.return_value = mock_response

        page_args = {
            "space": "TEST",
            "title": "New Page",
            "body": "<p>Content</p>",
            "parent_id": "parent-1",
        }
        result = self.safe_confluence_api.create_page(**page_args)

        self.assertEqual(result["id"], "new-page-id")
        self.mock_confluence_client.create_page.assert_called_once()
        mock_make_request.assert_called_once_with(
            "POST",
            f"{self.safe_confluence_api.base_url}/rest/api/content",
            headers=self.safe_confluence_api.headers,
            json_data={
                "type": "page",
                "title": page_args["title"],
                "space": {"key": page_args["space"]},
                "body": {
                    "storage": {"value": page_args["body"], "representation": "storage"}
                },
                "ancestors": [{"id": page_args["parent_id"]}],
            },
            verify_ssl=False,
        )

    @patch("src.api.safe_confluence_api.make_request")
    def test_get_user_details_by_username_fallback_success(self, mock_make_request):
        """Test get_user_details_by_username successful fallback."""
        self.mock_confluence_client.get_user_details_by_username.side_effect = (
            Exception("Library Error")
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "username": "fallback_user",
            "displayName": "Fallback User",
        }
        mock_make_request.return_value = mock_response

        username = "fallback_user"
        result = self.safe_confluence_api.get_user_details_by_username(username)

        self.assertEqual(result["username"], "fallback_user")
        self.mock_confluence_client.get_user_details_by_username.assert_called_once()
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_confluence_api.base_url}/rest/api/user?username={username}",
            headers=self.safe_confluence_api.headers,
            verify_ssl=False,
        )

    @patch("src.api.safe_confluence_api.requests.head")
    def test_get_page_id_from_url_short_url_success(self, mock_head):
        """Test resolving page ID from a short URL."""
        mock_response = MagicMock()
        mock_response.url = "https://mock.confluence.com/pages/12345/Some+Page"
        mock_response.raise_for_status.return_value = None
        mock_head.return_value = mock_response

        url = "https://mock.confluence.com/x/abcde"
        page_id = self.safe_confluence_api.get_page_id_from_url(url)
        self.assertEqual(page_id, "12345")
        mock_head.assert_called_once_with(
            url,
            headers=self.safe_confluence_api.headers,
            allow_redirects=True,
            timeout=15,
            verify=False,
        )

    @patch("src.api.safe_confluence_api.requests.head")
    def test_get_page_id_from_url_short_url_failure(self, mock_head):
        """Test failure to resolve page ID from a short URL."""
        mock_head.side_effect = requests.exceptions.RequestException("Network Error")

        url = "https://mock.confluence.com/x/abcde"
        page_id = self.safe_confluence_api.get_page_id_from_url(url)
        self.assertIsNone(page_id)
        mock_head.assert_called_once()

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
