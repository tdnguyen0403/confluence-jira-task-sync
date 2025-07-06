# jira_confluence_automator_/tests/service/test_jira_service.py

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
from src.config import config
from src.exceptions import AutomationError


# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestJiraService(unittest.TestCase):
    """Tests the high-level JiraService."""

    def setUp(self):
        """Set up a mock SafeJiraApi and the service for each test."""
        # Use Mock(spec=SafeJiraApi) to ensure mocks adhere to SafeJiraApi methods
        self.mock_safe_api = Mock(spec=SafeJiraApi) 
        
        self.mock_config_patcher = patch('src.services.jira_service.config')
        self.mock_config = self.mock_config_patcher.start()
        self.mock_config.JIRA_PROJECT_KEY = "TEST"
        self.mock_config.TASK_ISSUE_TYPE_ID = "10000"
        self.mock_config.JIRA_DEFAULT_ASSIGNEE_ID = "some_default_id" 
        self.mock_config.JIRA_CUSTOM_FIELDS = {
            "Confluence URL": "customfield_10001",
            "Request User": "customfield_10002"
        }
        self.mock_config.JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10003"


        self.jira_service = JiraService(self.mock_safe_api)
        # Mock get_myself for get_current_user_display_name dependency (for most tests)
        self.mock_safe_api.get_myself.return_value = {"displayName": "AutomationBot"}


    def tearDown(self):
        """Clean up mocks after each test."""
        self.mock_config_patcher.stop()
        self.mock_safe_api.get_myself.reset_mock()
        # Ensure the service's internal cache is reset for each test
        self.jira_service._current_user_name = None 


    def test_get_issue_delegates_to_safe_api(self):
        """Verify get_issue calls the underlying safe_api method."""
        self.jira_service.get_issue("TEST-123")
        self.mock_safe_api.get_issue.assert_called_once_with("TEST-123", "*all")

    def test_get_current_user_display_name_success_and_cache(self):
        """Test that the user's display name is fetched and then cached."""
        self.mock_safe_api.get_myself.reset_mock() # Reset to ensure no prior calls interfere
        self.mock_safe_api.get_myself.return_value = {"displayName": "Test User"}
        
        # First call should hit the API.
        name1 = self.jira_service.get_current_user_display_name()
        self.assertEqual(name1, "Test User")
        self.mock_safe_api.get_myself.assert_called_once() # get_myself called once

        # Second call should use the cached value, not call the API again.
        name2 = self.jira_service.get_current_user_display_name()
        self.assertEqual(name2, "Test User")
        self.mock_safe_api.get_myself.assert_called_once() # get_myself still called only once

    def test_get_current_user_display_name_failure(self):
        """Test the fallback to 'Unknown User' when the API fails."""
        self.mock_safe_api.get_myself.reset_mock()
        self.mock_safe_api.get_myself.return_value = None # Simulate API failure
        
        name = self.jira_service.get_current_user_display_name()
        self.assertEqual(name, "Unknown User")
        self.mock_safe_api.get_myself.assert_called_once()


    @patch("src.services.jira_service.datetime")
    def test_prepare_jira_task_fields_dynamically_extracts_project_key(
        self, mock_datetime
    ):
        """
        Test that `prepare_jira_task_fields` dynamically extracts the project
        key from the parent issue key and includes explicit request_user in description.
        """
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        
        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="My Summary",
            status="incomplete",
            assignee_name="assignee_user_name", # Provided assignee name
            due_date="2025-01-15", # Corrected: provide a valid string
            original_page_version=1,
            original_page_version_by="ConfluenceUser",
            original_page_version_when="now",
            context="This is the context.",
        )
        parent_key = "PROJ-123"
        test_request_user = "APIRequester" 

        # Act
        result = self.jira_service.prepare_jira_task_fields(
            mock_task, parent_key, test_request_user 
        )

        # Assert
        self.assertEqual(result["fields"]["project"]["key"], "PROJ")
        self.assertEqual(result["fields"]["summary"], "My Summary")
        self.assertEqual(result["fields"]["issuetype"]["id"], self.mock_config.TASK_ISSUE_TYPE_ID)
        self.assertEqual(result["fields"]["duedate"], "2025-01-15")
        self.assertEqual(result["fields"]["assignee"]["name"], "assignee_user_name") 
        
        self.assertEqual(result["fields"][self.mock_config.JIRA_PARENT_WP_CUSTOM_FIELD_ID], parent_key)
        self.assertNotIn("customfield_10001", result["fields"])
        self.assertNotIn("customfield_10002", result["fields"])


        expected_description = (
            "Context from Confluence:\nThis is the context.\n\n"
            f"Created by AutomationBot on 2025-01-01 12:00:00 requested by {test_request_user}" 
        )
        self.assertEqual(result["fields"]["description"], expected_description)

    @patch("src.services.jira_service.datetime")
    def test_prepare_jira_task_fields_with_default_request_user(
        self, mock_datetime
    ):
        """
        Test that `prepare_jira_task_fields` correctly handles the default
        'jira-user' value when passed from create_issue's default.
        """
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        
        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="My Summary",
            status="incomplete",
            assignee_name=None, 
            due_date=config.DEFAULT_DUE_DATE, # Corrected: provide a valid string
            original_page_version=1,
            original_page_version_by="AnotherConfluenceUser",
            original_page_version_when="now",
            context=None,
        )
        parent_key = "ANOTHER-456"
        test_default_user = "jira-user"

        # Act
        result = self.jira_service.prepare_jira_task_fields(mock_task, parent_key, test_default_user) 

        # Assert
        self.assertEqual(result["fields"]["project"]["key"], "ANOTHER")
        self.assertEqual(result["fields"]["summary"], "My Summary")
        self.assertEqual(result["fields"]["issuetype"]["id"], self.mock_config.TASK_ISSUE_TYPE_ID)
        self.assertEqual(result["fields"]["duedate"], config.DEFAULT_DUE_DATE)
        self.assertNotIn("assignee", result["fields"])
        
        self.assertEqual(result["fields"][self.mock_config.JIRA_PARENT_WP_CUSTOM_FIELD_ID], parent_key)
        self.assertNotIn("customfield_10001", result["fields"])
        self.assertNotIn("customfield_10002", result["fields"])


        expected_description = (
            f"Created by AutomationBot on 2025-01-01 12:00:00 requested by {test_default_user}" 
        )
        self.assertEqual(result["fields"]["description"], expected_description)


    @patch("src.services.jira_service.JiraService.prepare_jira_task_fields")
    def test_create_issue_delegates_and_prepares_fields(self, mock_prepare_fields):
        """
        Test that create_issue correctly prepares fields and calls the API,
        handling both explicit and default request_user.
        """
        # Arrange
        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="Test Task",
            status="incomplete",
            assignee_name="test_assignee",
            due_date="2025-01-01", 
            original_page_version=1,
            original_page_version_by="original_author",
            original_page_version_when="now",
            context="test context"
        )
        parent_key = "PARENT-1"
        expected_jira_key_dict = {'key': "NEWISSUE-1"}
        
        prepared_fields_payload = {
            "fields": {
                "project": {"key": "PARENT"},
                "summary": "Test Task",
                "issuetype": {"id": self.mock_config.TASK_ISSUE_TYPE_ID},
                "description": "Prepared description",
                "parent": {"key": parent_key},
                "assignee": {"name": "test_assignee"}
            }
        }
        mock_prepare_fields.return_value = prepared_fields_payload
        self.mock_safe_api.create_issue.return_value = expected_jira_key_dict 

        # Test case 1: Explicit request_user
        explicit_request_user = "ExplicitUser"
        jira_key_explicit = self.jira_service.create_issue(mock_task, parent_key, explicit_request_user)

        self.assertEqual(jira_key_explicit, expected_jira_key_dict) 
        mock_prepare_fields.assert_called_once_with(mock_task, parent_key, explicit_request_user)
        self.mock_safe_api.create_issue.assert_called_once_with(prepared_fields_payload) 
        
        mock_prepare_fields.reset_mock()
        self.mock_safe_api.create_issue.reset_mock()
        
        # Test case 2: Default request_user (no request_user provided in call to create_issue)
        jira_key_default = self.jira_service.create_issue(mock_task, parent_key)

        self.assertEqual(jira_key_default, expected_jira_key_dict)
        mock_prepare_fields.assert_called_once_with(mock_task, parent_key, "jira-user")
        self.mock_safe_api.create_issue.assert_called_once_with(prepared_fields_payload) 


    def test_create_issue_api_failure(self):
        """Test that create_issue handles API failures gracefully."""
        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="Failing Task",
            status="incomplete",
            assignee_name=None,
            due_date=config.DEFAULT_DUE_DATE, # Corrected: provide a valid string
            original_page_version=1,
            original_page_version_by="author",
            original_page_version_when="now",
            context=None
        )
        parent_key = "FAIL-1"
        
        prepared_fields_payload = {
            "fields": {
                "project": {"key": "FAIL"},
                "summary": "Failing Task",
                "issuetype": {"id": self.mock_config.TASK_ISSUE_TYPE_ID},
                "description": "Failing description",
                "parent": {"key": parent_key}
            }
        }
        with patch("src.services.jira_service.JiraService.prepare_jira_task_fields", return_value=prepared_fields_payload):
            self.mock_safe_api.create_issue.side_effect = Exception("Jira API error")

            with self.assertRaises(Exception) as cm: 
                self.jira_service.create_issue(mock_task, parent_key, "TestUser")
            
            self.assertIn("Jira API error", str(cm.exception)) 
            self.mock_safe_api.create_issue.assert_called_once()
            self.assertEqual(self.mock_safe_api.create_issue.call_args[0][0]["fields"]["summary"], "Failing Task") 

if __name__ == "__main__":
    unittest.main()