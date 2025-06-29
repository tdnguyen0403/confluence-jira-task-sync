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

import requests
from atlassian import Jira

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.safe_jira_api import SafeJiraApi

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestSafeJiraApi(unittest.TestCase):
    """Tests the low-level SafeJiraApi for primary and fallback logic."""

    def setUp(self):
        """Set up a mock Jira client before each test."""
        self.mock_jira_client = MagicMock(spec=Jira)
        self.safe_jira_api = SafeJiraApi(self.mock_jira_client)

    def test_get_issue_primary_success(self):
        """Test get_issue successful call using the library."""
        self.mock_jira_client.get_issue.return_value = {"key": "TEST-1"}
        result = self.safe_jira_api.get_issue("TEST-1")
        self.assertEqual(result["key"], "TEST-1")
        self.mock_jira_client.get_issue.assert_called_once_with("TEST-1", fields="*all")

    @patch("src.api.safe_jira_api.requests.get")
    def test_get_issue_fallback_success(self, mock_get):
        """Test get_issue fallback after library raises an exception."""
        self.mock_jira_client.get_issue.side_effect = Exception("API Error")
        mock_response = Mock()
        mock_response.json.return_value = {"key": "FALLBACK-1"}
        mock_get.return_value = mock_response

        result = self.safe_jira_api.get_issue("FALLBACK-1")

        self.assertEqual(result["key"], "FALLBACK-1")
        self.mock_jira_client.get_issue.assert_called_once()
        mock_get.assert_called_once()

    @patch("src.api.safe_jira_api.requests.get")
    def test_get_issue_fallback_failure(self, mock_get):
        """Test get_issue when both primary and fallback attempts fail."""
        self.mock_jira_client.get_issue.side_effect = Exception("API Error")
        mock_get.side_effect = requests.exceptions.RequestException("Network Error")
        result = self.safe_jira_api.get_issue("FAIL-1")
        self.assertIsNone(result)

    def test_create_issue_primary_success(self):
        """Test create_issue successful call using the library."""
        self.mock_jira_client.issue_create.return_value = {"key": "NEW-1"}
        result = self.safe_jira_api.create_issue({"fields": {}})
        self.assertEqual(result["key"], "NEW-1")
        self.mock_jira_client.issue_create.assert_called_once_with(fields={})

    @patch("src.api.safe_jira_api.requests.post")
    def test_create_issue_fallback_success(self, mock_post):
        """Test create_issue fallback after library raises an exception."""
        self.mock_jira_client.issue_create.side_effect = Exception("API Error")
        mock_response = Mock()
        mock_response.json.return_value = {"key": "FALLBACK-NEW-1"}
        mock_post.return_value = mock_response

        result = self.safe_jira_api.create_issue({"fields": {}})

        self.assertEqual(result["key"], "FALLBACK-NEW-1")
        self.mock_jira_client.issue_create.assert_called_once()
        mock_post.assert_called_once()

    def test_transition_issue_primary_success(self):
        """Test transition_issue successful call using the library."""
        self.safe_jira_api.find_transition_id_by_name = Mock(return_value="31")
        self.mock_jira_client.issue_transition.return_value = True

        result = self.safe_jira_api.transition_issue("TEST-1", "Done")

        self.mock_jira_client.issue_transition.assert_called_once_with("TEST-1", "Done")
        self.assertTrue(result)

    @patch("src.api.safe_jira_api.requests.post")
    def test_transition_issue_fallback_success(self, mock_post):
        """Test transition_issue fallback after library raises an exception."""
        self.mock_jira_client.issue_transition.side_effect = Exception("API Error")
        self.safe_jira_api.find_transition_id_by_name = Mock(return_value="31")
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.safe_jira_api.transition_issue("TEST-1", "Done")
        self.assertTrue(result)

    @patch("src.api.safe_jira_api.requests.get")
    def test_get_myself_success(self, mock_requests_get):
        """Test successful retrieval of the current user's details."""
        mock_response = Mock()
        expected_user_data = {"name": "test_user", "displayName": "Test User"}
        mock_response.json.return_value = expected_user_data
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        user_data = self.safe_jira_api.get_myself()

        self.assertEqual(user_data, expected_user_data)
        expected_url = f"{self.safe_jira_api.base_url}/rest/api/2/myself"
        mock_requests_get.assert_called_once_with(
            expected_url, headers=self.safe_jira_api.headers, verify=False, timeout=15
        )

    @patch("src.api.safe_jira_api.requests.get")
    def test_get_myself_failure(self, mock_requests_get):
        """Test the graceful failure of get_myself when the API call fails."""
        mock_requests_get.side_effect = requests.exceptions.RequestException(
            "API Down"
        )
        user_data = self.safe_jira_api.get_myself()
        self.assertIsNone(user_data)


if __name__ == "__main__":
    unittest.main()
