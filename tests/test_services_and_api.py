import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import requests
import logging

# Disable logging during tests
logging.disable(logging.CRITICAL)


# Add the project root to the path for testing
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from atlassian import Jira, Confluence
from src.api.safe_jira_api import SafeJiraApi
from src.api.safe_confluence_api import SafeConfluenceApi
from src.services.jira_service import JiraService
from src.services.confluence_service import ConfluenceService
from src.services.issue_finder_service import IssueFinderService
from src.models.data_models import ConfluenceTask
from src.config import config

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

    @patch('src.api.safe_jira_api.requests.get')
    def test_get_myself_success(self, mock_requests_get):
        """
        Test the successful retrieval of the current user's details via fallback.
        """
        mock_response = Mock()
        expected_user_data = {"name": "test_user", "displayName": "Test User"}
        mock_response.json.return_value = expected_user_data
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        user_data = self.safe_jira_api.get_myself()

        self.assertEqual(user_data, expected_user_data)
        expected_url = f"{self.safe_jira_api.base_url}/rest/api/2/myself"
        mock_requests_get.assert_called_once_with(expected_url, headers=self.safe_jira_api.headers, verify=False, timeout=15)


    @patch('src.api.safe_jira_api.requests.get')
    def test_get_myself_failure(self, mock_requests_get):
        """
        Test the graceful failure of get_myself when the API call fails.
        """
        mock_requests_get.side_effect = requests.exceptions.RequestException("API Down")
        
        user_data = self.safe_jira_api.get_myself()

        self.assertIsNone(user_data)

    @patch('src.api.safe_jira_api.requests.get')
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
        self.mock_jira_client.issue_create.assert_called_once_with(fields={})

    @patch('src.api.safe_jira_api.requests.post')
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
        self.mock_jira_client.issue_transition.assert_called_once_with("TEST-1", "Done")
        self.assertTrue(result)

    @patch('src.api.safe_jira_api.requests.post')
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

    @patch('src.api.safe_jira_api.requests.get')
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

    @patch('src.api.safe_confluence_api.requests.get')
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

    @patch('src.api.safe_jira_api.SafeJiraApi')
    def setUp(self, MockSafeJiraApi):
        self.mock_safe_api = Mock(spec=SafeJiraApi)
        self.jira_service = JiraService(self.mock_safe_api)

    def test_get_issue_delegates_to_safe_api(self):
        """Verify get_issue calls the underlying safe_api method."""
        self.jira_service.get_issue("TEST-123")
        self.mock_safe_api.get_issue.assert_called_once_with("TEST-123", "*all")
    
    def test_get_current_user_display_name_success_and_cache(self):
        """Test that the user's display name is fetched and then cached."""
        self.mock_safe_api.get_myself.return_value = {"displayName": "Test User"}

        # First call should call the API
        name1 = self.jira_service.get_current_user_display_name()
        self.assertEqual(name1, "Test User")
        self.mock_safe_api.get_myself.assert_called_once()

        # Second call should use the cached value
        name2 = self.jira_service.get_current_user_display_name()
        self.assertEqual(name2, "Test User")
        self.mock_safe_api.get_myself.assert_called_once() # Should still be 1

    def test_get_current_user_display_name_failure(self):
        """Test the fallback to 'Unknown User' when the API fails."""
        self.mock_safe_api.get_myself.return_value = None
        name = self.jira_service.get_current_user_display_name()
        self.assertEqual(name, "Unknown User")

    @patch('src.services.jira_service.datetime')
    def test_prepare_jira_task_fields_with_all_info(self, mock_datetime):
        """Test preparing fields with context and a logged-in user."""
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        self.jira_service.get_current_user_display_name = Mock(return_value="Test User")
        mock_task = ConfluenceTask(
            confluence_page_id="1", confluence_page_title="My Page",
            confluence_page_url="http://page.url", confluence_task_id="t1",
            task_summary="My Summary", status="incomplete", assignee_name="assignee",
            due_date="2025-01-15", original_page_version=1,
            original_page_version_by="author", original_page_version_when="now",
            context="This is the context."
        )
        result = self.jira_service.prepare_jira_task_fields(mock_task, "WP-1")
        expected_description = (
            "Context from Confluence:\nThis is the context.\n\n"
            "Created by Test User on 2025-01-01 12:00:00" # Modified to remove the Source line
        )
        self.assertEqual(result['fields']['description'], expected_description)
        
    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

class TestConfluenceService(unittest.TestCase):
    """
    Tests the ConfluenceService to ensure it correctly delegates calls
    to the underlying SafeConfluenceApi.
    """
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
        self.mock_safe_api.get_page_by_id.assert_called_once_with(page_id, expand="version")

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
        self.mock_safe_api.update_page_with_jira_links.assert_called_once_with(page_id, mappings)

    def test_create_page_delegates(self):
        """Verify create_page calls the underlying api method."""
        page_args = {"space": "TEST", "title": "My Page", "parent_id": "123"}
        self.confluence_service.create_page(**page_args)
        self.mock_safe_api.create_page.assert_called_once_with(**page_args)

    def test_get_user_details_by_username_delegates(self):
        """Verify get_user_details_by_username calls the underlying api method."""
        username = "testuser"
        self.confluence_service.get_user_details_by_username(username)
        self.mock_safe_api.get_user_details_by_username.assert_called_once_with(username)

class TestIssueFinderService(unittest.TestCase):
    """Tests the specialized IssueFinderService."""

    def setUp(self):
        self.mock_confluence_api = Mock(spec=SafeConfluenceApi)
        self.mock_jira_api = Mock(spec=SafeJiraApi)
        self.issue_finder = IssueFinderService(self.mock_confluence_api, self.mock_jira_api)

        # Suppress logging during tests for cleaner output unless needed for debugging
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        logging.disable(logging.NOTSET) # Re-enable logging

    def test_find_issue_on_page_success_work_package(self):
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
            {"fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"]}}},
            {"key": "WP-1", "fields": {"summary": "Full WP Details", "issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"], "name": "Work Package"}}}
        ]

        # Pass the PARENT_ISSUES_TYPE_ID dictionary
        result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "WP-1")
        self.assertEqual(result["fields"]["issuetype"]["id"], config.PARENT_ISSUES_TYPE_ID["Work Package"])
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)
        # Corrected assertion: Assert on the 'get_issue' method of the mock
        self.mock_jira_api.get_issue.assert_any_call("WP-1", fields="issuetype")
        self.mock_jira_api.get_issue.assert_any_call("WP-1", fields="key,issuetype,assignee,reporter")
        self.mock_jira_api.reset_mock() # Reset for next test

    def test_find_issue_on_page_success_risk(self):
        """Test finding a Risk issue successfully."""
        page_html = f"""
            <div>
                <ac:structured-macro ac:name="jira">
                    <ac:parameter ac:name="key">RISK-1</ac:parameter>
                </ac:structured-macro>
            </div>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}

        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Risk"]}}},
            {"key": "RISK-1", "fields": {"summary": "Full Risk Details", "issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Risk"], "name": "Risk"}}}
        ]

        result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "RISK-1")
        self.assertEqual(result["fields"]["issuetype"]["id"], config.PARENT_ISSUES_TYPE_ID["Risk"])
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)
        # Corrected assertion: Assert on the 'get_issue' method of the mock
        self.mock_jira_api.get_issue.assert_any_call("RISK-1", fields="issuetype")
        self.mock_jira_api.get_issue.assert_any_call("RISK-1", fields="key,issuetype,assignee,reporter")
        self.mock_jira_api.reset_mock()

    def test_find_issue_on_page_success_deviation(self):
        """Test finding a Deviation issue successfully."""
        page_html = f"""
            <div>
                <ac:structured-macro ac:name="jira">
                    <ac:parameter ac:name="key">DEV-1</ac:parameter>
                </ac:structured-macro>
            </div>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}

        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Deviation"]}}},
            {"key": "DEV-1", "fields": {"summary": "Full Deviation Details", "issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Deviation"], "name": "Deviation"}}}
        ]

        result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "DEV-1")
        self.assertEqual(result["fields"]["issuetype"]["id"], config.PARENT_ISSUES_TYPE_ID["Deviation"])
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)
        # Corrected assertion: Assert on the 'get_issue' method of the mock
        self.mock_jira_api.get_issue.assert_any_call("DEV-1", fields="issuetype")
        self.mock_jira_api.get_issue.assert_any_call("DEV-1", fields="key,issuetype,assignee,reporter")
        self.mock_jira_api.reset_mock()

    def test_find_issue_on_page_not_found(self):
        """Test when no matching macro is on the page."""
        page_html = f"<p>No Jira macros here.</p>"
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}

        # Pass the PARENT_ISSUES_TYPE_ID dictionary
        result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)

        self.assertIsNone(result)
        # Corrected assertion: Assert on the 'get_issue' method of the mock
        self.mock_jira_api.get_issue.assert_not_called()
        self.mock_jira_api.reset_mock()

    def test_find_issue_on_page_wrong_issue_type(self):
        """Test that a Jira macro with an unsearched issue type is ignored."""
        page_html = f"""
            <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">TASK-123</ac:parameter></ac:structured-macro>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {"body": {"storage": {"value": page_html}}}
        # Return an issue type ID that is NOT in PARENT_ISSUES_TYPE_ID values
        self.mock_jira_api.get_issue.return_value = {"fields": {"issuetype": {"id": config.TASK_ISSUE_TYPE_ID}}}

        # Pass the PARENT_ISSUES_TYPE_ID dictionary
        result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)

        self.assertIsNone(result)
        # Corrected assertion: Assert on the 'get_issue' method of the mock
        self.mock_jira_api.get_issue.assert_called_once_with("TASK-123", fields="issuetype")
        self.mock_jira_api.reset_mock()

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

                # Pass the PARENT_ISSUES_TYPE_ID dictionary
                result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)

                self.assertIsNone(result)
                # Corrected assertion: Assert on the 'get_issue' method of the mock
                self.mock_jira_api.get_issue.assert_not_called()
                # Reset mock for the next sub-test
                self.mock_jira_api.reset_mock()

    def test_find_issue_on_page_no_page_content(self):
        """Test the finder when the Confluence API returns no content for the page."""
        self.mock_confluence_api.get_page_by_id.return_value = None
        # Pass the PARENT_ISSUES_TYPE_ID dictionary
        result = self.issue_finder.find_issue_on_page("123", config.PARENT_ISSUES_TYPE_ID)
        self.assertIsNone(result)
        # Corrected assertion: Assert on the 'get_issue' method of the mock
        self.mock_jira_api.get_issue.assert_not_called()
        self.mock_jira_api.reset_mock()
            
if __name__ == '__main__':
    unittest.main()