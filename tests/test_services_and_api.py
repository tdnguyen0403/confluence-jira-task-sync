import unittest
from unittest.mock import Mock, patch, MagicMock

# Add the project root to the path for testing
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from atlassian import Jira, Confluence
from api.safe_jira_api import SafeJiraApi
from api.safe_confluence_api import SafeConfluenceApi
from services.jira_service import JiraService
from services.confluence_service import ConfluenceService
from services.issue_finder_service import IssueFinderService
from models.data_models import ConfluenceTask
import config

# --- API Layer Tests ---

class TestSafeJiraApi(unittest.TestCase):
    """Tests the low-level SafeJiraApi for primary and fallback logic."""

    def setUp(self):
        self.mock_jira_client = MagicMock(spec=Jira)
        self.safe_jira_api = SafeJiraApi(self.mock_jira_client)

    def test_get_issue_primary_success(self):
        """Test get_issue successful call using the library."""
        self.mock_jira_client.get_issue.return_value = {"key": "TEST-1"}
        result = self.safe_jira_api.get_issue("TEST-1")
        self.assertEqual(result["key"], "TEST-1")
        self.mock_jira_client.get_issue.assert_called_once_with("TEST-1", fields="*all")

    @patch('api.safe_jira_api.requests.get')
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

class TestSafeConfluenceApi(unittest.TestCase):
    """Tests the low-level SafeConfluenceApi."""

    def setUp(self):
        self.mock_confluence_client = MagicMock(spec=Confluence)
        self.safe_confluence_api = SafeConfluenceApi(self.mock_confluence_client)

    def test_get_page_by_id_primary_success(self):
        """Test get_page_by_id successful call using the library."""
        self.mock_confluence_client.get_page_by_id.return_value = {"id": "123"}
        result = self.safe_confluence_api.get_page_by_id("123")
        self.assertEqual(result["id"], "123")
        self.mock_confluence_client.get_page_by_id.assert_called_once_with("123")

# --- Service Layer Tests ---

class TestJiraService(unittest.TestCase):
    """Tests the high-level JiraService pass-through."""

    @patch('api.safe_jira_api.SafeJiraApi')
    def setUp(self, MockSafeJiraApi):
        self.mock_safe_api = MockSafeJiraApi.return_value
        self.jira_service = JiraService(self.mock_safe_api)

    def test_get_issue_delegates_to_safe_api(self):
        """Verify get_issue calls the underlying safe_api method."""
        self.jira_service.get_issue("TEST-123")
        self.mock_safe_api.get_issue.assert_called_once_with("TEST-123", "*all")

class TestIssueFinderService(unittest.TestCase):
    """Tests the specialized IssueFinderService."""

    def setUp(self):
        self.mock_confluence_api = Mock(spec=SafeConfluenceApi)
        self.mock_jira_api = Mock(spec=SafeJiraApi)
        self.issue_finder = IssueFinderService(self.mock_confluence_api, self.mock_jira_api)

    def test_find_issue_on_page_success(self):
        """Test finding a work package successfully."""
        page_html = f"""
            <div>
                <p>Some content</p>
                <ac:structured-macro ac:name="jira">
                    <ac:parameter ac:name="key">WP-1</ac:parameter>
                </ac:structured-macro>
            </div>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}
        
        # Mock the two calls to get_issue
        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.WORK_PACKAGE_ISSUE_TYPE_ID}}}, # First call for type check
            {"key": "WP-1", "fields": {"summary": "Full WP Details"}} # Second call for full details
        ]
        
        result = self.issue_finder.find_issue_on_page("123", config.WORK_PACKAGE_ISSUE_TYPE_ID)

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "WP-1")
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)
        
    def test_find_issue_on_page_not_found(self):
        """Test when no matching macro is on the page."""
        page_html = f"<p>No Jira macros here.</p>"
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}
        
        result = self.issue_finder.find_issue_on_page("123", config.WORK_PACKAGE_ISSUE_TYPE_ID)

        self.assertIsNone(result)
        self.mock_jira_api.get_issue.assert_not_called()

if __name__ == '__main__':
    unittest.main()
