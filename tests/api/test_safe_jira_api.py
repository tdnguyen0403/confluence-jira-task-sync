"""
Unit tests for the SafeJiraApi class.

This module tests the low-level SafeJiraApi, which is responsible for direct
communication with the Jira API. The tests verify both the primary calls
(using the atlassian-python-api library) and the custom fallback mechanisms
that use direct REST API calls.
"""

import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

from atlassian import Jira

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.safe_jira_api import SafeJiraApi

# No need to import config here as it's not directly used in the test class, only in the module under test.

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestSafeJiraApi(unittest.TestCase):
    """Tests the low-level SafeJiraApi for primary and fallback logic."""

    def setUp(self):
        """Set up a mock Jira client before each test."""
        self.mock_jira_client = MagicMock(spec=Jira)
        # Patch config values that SafeJiraApi directly accesses
        patcher_config_url = patch(
            "src.api.safe_jira_api.config.JIRA_URL", "https://mock.jira.com"
        )
        patcher_config_token = patch(
            "src.api.safe_jira_api.config.JIRA_API_TOKEN", "mock_token"
        )

        self.mock_config_url = patcher_config_url.start()
        self.mock_config_token = patcher_config_token.start()

        self.addCleanup(patcher_config_url.stop)
        self.addCleanup(patcher_config_token.stop)

        self.safe_jira_api = SafeJiraApi(self.mock_jira_client)

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_get_issue_primary_success(self, mock_make_request):
        """Test get_issue successful call using the library (no fallback needed)."""
        self.mock_jira_client.get_issue.return_value = {"key": "TEST-1"}
        result = self.safe_jira_api.get_issue("TEST-1")
        self.assertEqual(result["key"], "TEST-1")
        self.mock_jira_client.get_issue.assert_called_once_with("TEST-1", fields="*all")
        mock_make_request.assert_not_called()  # Ensure fallback was not called

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_get_issue_fallback_success(self, mock_make_request):
        """Test get_issue successful fallback after library failure."""
        self.mock_jira_client.get_issue.side_effect = Exception("API Error")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "key": "FALLBACK-1",
            "fields": {"summary": "Fallback Issue"},
        }
        mock_make_request.return_value = mock_response

        result = self.safe_jira_api.get_issue("FALLBACK-1")

        self.assertEqual(result["key"], "FALLBACK-1")
        self.mock_jira_client.get_issue.assert_called_once()
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_jira_api.base_url}/rest/api/2/issue/FALLBACK-1?fields=*all",
            headers=self.safe_jira_api.headers,
            verify_ssl=False,
        )

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_get_issue_fallback_failure(self, mock_make_request):
        """Test get_issue when both primary and fallback attempts fail."""
        self.mock_jira_client.get_issue.side_effect = Exception("API Error")
        mock_make_request.return_value = None  # Simulate helper failure

        result = self.safe_jira_api.get_issue("FAIL-1")
        self.assertIsNone(result)
        self.mock_jira_client.get_issue.assert_called_once()
        mock_make_request.assert_called_once()  # Verify helper was attempted

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_create_issue_primary_success(self, mock_make_request):
        """Test create_issue successful call using the library."""
        self.mock_jira_client.issue_create.return_value = {"key": "NEW-1"}
        issue_fields_payload = {"fields": {"summary": "New Issue"}}
        result = self.safe_jira_api.create_issue(issue_fields_payload)
        self.assertEqual(result["key"], "NEW-1")
        self.mock_jira_client.issue_create.assert_called_once_with(
            fields=issue_fields_payload["fields"]
        )
        mock_make_request.assert_not_called()

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_create_issue_fallback_success(self, mock_make_request):
        """Test create_issue fallback after library raises an exception."""
        self.mock_jira_client.issue_create.side_effect = Exception("API Error")

        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "FALLBACK-NEW-1"}
        mock_make_request.return_value = mock_response

        issue_fields_payload = {"fields": {"summary": "Fallback New Issue"}}
        result = self.safe_jira_api.create_issue(issue_fields_payload)

        self.assertEqual(result["key"], "FALLBACK-NEW-1")
        self.mock_jira_client.issue_create.assert_called_once()
        mock_make_request.assert_called_once_with(
            "POST",
            f"{self.safe_jira_api.base_url}/rest/api/2/issue",
            headers=self.safe_jira_api.headers,
            json_data=issue_fields_payload,
            verify_ssl=False,
        )

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_get_available_transitions_success(self, mock_make_request):
        """Test get_available_transitions directly using make_request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "transitions": [{"id": "1", "name": "To Do"}]
        }
        mock_make_request.return_value = mock_response

        transitions = self.safe_jira_api.get_available_transitions("TEST-123")
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["id"], "1")
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_jira_api.base_url}/rest/api/2/issue/TEST-123/transitions",
            headers=self.safe_jira_api.headers,
            verify_ssl=False,
        )
        # Ensure the Jira client's methods are not called for direct HTTP methods
        self.mock_jira_client.assert_not_called()

    def test_transition_issue_primary_success(self):
        """Test transition_issue successful call using the library."""
        # Mocking find_transition_id_by_name directly for this test
        self.safe_jira_api.find_transition_id_by_name = Mock(return_value="31")
        self.mock_jira_client.issue_transition.return_value = True

        result = self.safe_jira_api.transition_issue("TEST-1", "Done")

        self.mock_jira_client.issue_transition.assert_called_once_with("TEST-1", "Done")
        self.assertTrue(result)

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_transition_issue_fallback_success(self, mock_make_request):
        """Test transition_issue fallback after library raises an exception."""
        self.mock_jira_client.issue_transition.side_effect = Exception("API Error")

        # Mocking find_transition_id_by_name for the fallback logic
        self.safe_jira_api.find_transition_id_by_name = Mock(return_value="31")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None  # Simulate 204 No Content
        mock_make_request.return_value = mock_response

        result = self.safe_jira_api.transition_issue("TEST-1", "Done")
        self.assertTrue(result)
        self.mock_jira_client.issue_transition.assert_called_once()
        mock_make_request.assert_called_once_with(
            "POST",
            f"{self.safe_jira_api.base_url}/rest/api/2/issue/TEST-1/transitions",
            headers=self.safe_jira_api.headers,
            json_data={"transition": {"id": "31"}},
            verify_ssl=False,
        )

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_get_myself_success(self, mock_make_request):
        """Test successful retrieval of the current user's details directly using make_request."""
        mock_response = MagicMock()
        expected_user_data = {"name": "test_user", "displayName": "Test User"}
        mock_response.json.return_value = expected_user_data
        mock_make_request.return_value = mock_response

        user_data = self.safe_jira_api.get_myself()

        self.assertEqual(user_data, expected_user_data)
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_jira_api.base_url}/rest/api/2/myself",
            headers=self.safe_jira_api.headers,
            verify_ssl=False,
        )
        self.mock_jira_client.assert_not_called()

    @patch("src.api.safe_jira_api.make_request")  # Patch the new helper function
    def test_get_myself_failure(self, mock_make_request):
        """Test the graceful failure of get_myself when the API call fails."""
        mock_make_request.return_value = None  # Simulate helper failure
        user_data = self.safe_jira_api.get_myself()
        self.assertIsNone(user_data)
        mock_make_request.assert_called_once()

    @patch("src.api.safe_jira_api.make_request")
    def test_search_issues_primary_success(self, mock_make_request):
        """Test search_issues successful call using the library (no fallback needed)."""
        mock_issue_raw = {
            "key": "SEARCH-1",
            "fields": {"summary": "Found issue", "issuetype": {"id": "10000"}},
        }
        # Mocking the Jira client's jql method to return a list of objects with a .raw attribute
        mock_jira_issue_obj = MagicMock()
        mock_jira_issue_obj.raw = mock_issue_raw
        self.mock_jira_client.jql.return_value = [mock_jira_issue_obj]

        jql_query = "project = TEST"
        result = self.safe_jira_api.search_issues(jql_query, fields="summary,issuetype")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "SEARCH-1")
        self.mock_jira_client.jql.assert_called_once_with(
            jql_query, fields="summary,issuetype"
        )
        mock_make_request.assert_not_called()

    @patch("src.api.safe_jira_api.make_request")
    def test_search_issues_fallback_success(self, mock_make_request):
        """Test search_issues successful fallback after library failure."""
        self.mock_jira_client.jql.side_effect = Exception("JQL Library Error")

        mock_response = MagicMock()
        mock_response.json.return_value = {"issues": [{"key": "FALLBACK-SEARCH-1"}]}
        mock_make_request.return_value = mock_response

        jql_query = "project = FALLBACK"
        result = self.safe_jira_api.search_issues(jql_query, fields="key")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "FALLBACK-SEARCH-1")
        self.mock_jira_client.jql.assert_called_once()
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_jira_api.base_url}/rest/api/2/search?jql=project%20%3D%20FALLBACK&fields=key",
            headers=self.safe_jira_api.headers,
            verify_ssl=False,
        )

    @patch("src.api.safe_jira_api.make_request")
    def test_search_issues_fallback_failure(self, mock_make_request):
        """Test search_issues when both primary and fallback attempts fail."""
        self.mock_jira_client.jql.side_effect = Exception("JQL Library Error")
        mock_make_request.return_value = None  # Simulate helper failure

        result = self.safe_jira_api.search_issues("project = FAIL", fields="key")
        self.assertEqual(result, [])
        self.mock_jira_client.jql.assert_called_once()
        mock_make_request.assert_called_once()

    @patch("src.api.safe_jira_api.make_request")
    def test_get_issue_type_details_by_id_success(self, mock_make_request):
        """Test get_issue_type_details_by_id successful call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "1", "name": "Task"}
        mock_make_request.return_value = mock_response

        issue_type_id = "1"
        result = self.safe_jira_api.get_issue_type_details_by_id(issue_type_id)

        self.assertEqual(result["name"], "Task")
        mock_make_request.assert_called_once_with(
            "GET",
            f"{self.safe_jira_api.base_url}/rest/api/2/issuetype/{issue_type_id}",
            headers=self.safe_jira_api.headers,
            verify_ssl=False,
        )
        self.mock_jira_client.assert_not_called()  # No client method called for this

    @patch("src.api.safe_jira_api.make_request")
    def test_get_issue_type_details_by_id_failure(self, mock_make_request):
        """Test get_issue_type_details_by_id when API call fails."""
        mock_make_request.return_value = None  # Simulate helper failure

        issue_type_id = "999"
        result = self.safe_jira_api.get_issue_type_details_by_id(issue_type_id)

        self.assertIsNone(result)
        mock_make_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
