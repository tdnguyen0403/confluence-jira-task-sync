import unittest
from unittest.mock import Mock, patch, MagicMock
import requests
import logging
# Add this to disable logging during tests
logging.disable(logging.CRITICAL)

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
        # Create a mock with the transition_issue method
        self.mock_jira_client = MagicMock(spec=Jira)
        self.mock_jira_client.transition_issue = Mock()
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

    def test_create_issue_primary_success(self):
        """Test create_issue successful call using the library."""
        self.mock_jira_client.issue_create.return_value = {"key": "NEW-1"}
        result = self.safe_jira_api.create_issue({"fields": {}})
        self.assertEqual(result["key"], "NEW-1")
        self.mock_jira_client.issue_create.assert_called_once_with(fields={"fields": {}})

    @patch('api.safe_jira_api.requests.post')
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
        # Mock the dynamic transition lookup
        self.safe_jira_api.find_transition_id_by_name = Mock(return_value="31")
        result = self.safe_jira_api.transition_issue("TEST-1", "Done")
        self.mock_jira_client.transition_issue.assert_called_once_with("TEST-1", "31")
        self.assertTrue(result)

    @patch('api.safe_jira_api.requests.post')
    def test_transition_issue_fallback_success(self, mock_post):
        """Test transition_issue fallback after library raises an exception."""
        self.mock_jira_client.transition_issue.side_effect = Exception("API Error")
        self.safe_jira_api.find_transition_id_by_name = Mock(return_value="31")
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Correct the method call
        result = self.safe_jira_api.transition_issue("TEST-1", "Done")
        self.assertTrue(result)

    @patch('api.safe_jira_api.requests.get')
    def test_get_issue_fallback_failure(self, mock_get):
        """Test get_issue when both primary and fallback attempts fail."""
        self.mock_jira_client.get_issue.side_effect = Exception("API Error")
        mock_get.side_effect = requests.exceptions.RequestException("Network Error")
        result = self.safe_jira_api.get_issue("FAIL-1")
        self.assertIsNone(result)

    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
            
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

    def test_get_all_descendants_recursive(self):
        """Test that get_all_descendants recursively finds all child pages."""
        # Mock the API to simulate a three-level page hierarchy
        self.safe_confluence_api.get_page_child_by_type = Mock(side_effect=[
            [{"id": "child1"}, {"id": "child2"}],  # Children of root
            [{"id": "grandchild1"}],              # Children of child1
            [],                                   # Children of grandchild1
            []                                    # Children of child2
        ])

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
            "id": "101", "title": "Test Page", "_links": {"webui": "/test-page"},
            "body": {"storage": {"value": html_content}},
            "version": {"number": 2, "by": {"displayName": "tester"}, "when": "now"}
        }

        # Mock the user lookup for the assigned task
        self.safe_confluence_api.get_user_details_by_userkey = Mock(return_value={"username": "testuser"})

        tasks = self.safe_confluence_api.get_tasks_from_page(page_details)

        self.assertEqual(len(tasks), 3) # Should now find all 3 tasks
        self.assertEqual(tasks[0].task_summary, "Task 1")
        self.assertEqual(tasks[1].task_summary, "Task 2")
        self.assertEqual(tasks[1].status, "complete")
        self.assertEqual(tasks[2].task_summary, "Task 3 with and")
        self.assertEqual(tasks[2].status, "incomplete")

    @patch('api.safe_confluence_api.requests.get')
    def test_get_page_by_id_fallback_failure(self, mock_get):
        """Test get_page_by_id when both primary and fallback attempts fail."""
        self.mock_confluence_client.get_page_by_id.side_effect = Exception("API Error")
        mock_get.side_effect = requests.exceptions.RequestException("Network Error")
        result = self.safe_confluence_api.get_page_by_id("FAIL-123")
        self.assertIsNone(result)

    def test_get_tasks_from_page_no_body(self):
        """Test task parsing from a page with no body content."""
        page_details = {"id": "101"} # Missing 'body' key
        tasks = self.safe_confluence_api.get_tasks_from_page(page_details)
        self.assertEqual(len(tasks), 0)
        
    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
            
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
                <ac:structured-macro ac:name="jira">
                    <ac:parameter ac:name="key">WP-1</ac:parameter>
                </ac:structured-macro>
            </div>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}
        
        # Mock the two calls to get_issue
        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.WORK_PACKAGE_ISSUE_TYPE_ID}}},
            {"key": "WP-1", "fields": {"summary": "Full WP Details"}}
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

    def test_find_issue_on_page_wrong_issue_type(self):
        """Test that a Jira macro with the wrong issue type is ignored."""
        page_html = f"""
            <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">TASK-123</ac:parameter></ac:structured-macro>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}
        self.mock_jira_api.get_issue.return_value = {"fields": {"issuetype": {"id": "some_other_id"}}}

        result = self.issue_finder.find_issue_on_page("123", config.WORK_PACKAGE_ISSUE_TYPE_ID)

        self.assertIsNone(result)
        self.mock_jira_api.get_issue.assert_called_once_with("TASK-123", fields="issuetype")

    def test_find_issue_on_page_in_ignored_macro(self):
        """Test that a Jira macro inside an aggregation macro is ignored."""
        for macro_name in config.AGGREGATION_CONFLUENCE_MACRO:
            if macro_name == 'jira': continue # Skip the jira macro itself
            with self.subTest(macro=macro_name):
                page_html = f"""
                    <ac:structured-macro ac:name="{macro_name}">
                        <ac:rich-text-body>
                            <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">WP-999</ac:parameter></ac:structured-macro>
                        </ac:rich-text-body>
                    </ac:structured-macro>
                """
                self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}

                result = self.issue_finder.find_issue_on_page("123", config.WORK_PACKAGE_ISSUE_TYPE_ID)

                self.assertIsNone(result)
                self.mock_jira_api.get_issue.assert_not_called()
                # Reset mock for the next sub-test
                self.mock_jira_api.get_issue.reset_mock()

    def test_find_issue_on_page_no_page_content(self):
        """Test the finder when the Confluence API returns no content for the page."""
        self.mock_confluence_api.get_page_by_id.return_value = None
        result = self.issue_finder.find_issue_on_page("123", config.WORK_PACKAGE_ISSUE_TYPE_ID)
        self.assertIsNone(result)
   
    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
            
if __name__ == '__main__':
    unittest.main()