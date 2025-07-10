import logging
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock  # Fix: Import MagicMock


# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.api.safe_jira_api import SafeJiraApi
from src.models.data_models import ConfluenceTask
from src.services.jira_service import JiraService


# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestJiraService(unittest.TestCase):
    """Tests the high-level JiraService."""

    def setUp(self):
        """Set up a mock SafeJiraApi and the service for each test."""
        # Fix: Correct mock instance name and initialization
        self.mock_safe_jira_api = MagicMock(spec=SafeJiraApi)

        # Patch the entire config module
        self.patcher_config = patch("src.services.jira_service.config")
        self.mock_config = self.patcher_config.start()
        self.addCleanup(self.patcher_config.stop)

        # Set attributes on the mocked config module
        self.mock_config.TASK_ISSUE_TYPE_ID = "10002"
        self.mock_config.JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"
        self.mock_config.JIRA_PROJECT_ISSUE_TYPE_ID = "10200"
        self.mock_config.JIRA_PHASE_ISSUE_TYPE_ID = "11001"
        self.mock_config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID = "10100"
        self.mock_config.DEFAULT_DUE_DATE = "2025-01-01"
        self.mock_config.JIRA_ROOT_PARENT_CUSTOM_FIELD_ID = "customfield_12200"

        self.jira_service = JiraService(self.mock_safe_jira_api)
        self.jira_service._current_user_name = None

        self.mock_safe_jira_api.get_myself.return_value = {
            "displayName": "AutomationBot"
        }

    def test_get_issue_delegates_to_safe_api(self):
        """Verify get_issue calls the underlying safe_api method."""
        self.mock_safe_jira_api.get_issue.return_value = {"key": "TEST-1"}
        issue = self.jira_service.get_issue("TEST-1", fields="summary")
        self.assertEqual(issue["key"], "TEST-1")
        self.mock_safe_jira_api.get_issue.assert_called_once_with("TEST-1", "summary")

    @patch("src.services.jira_service.datetime")
    def test_prepare_jira_task_fields(self, mock_datetime):
        """Test that prepare_jira_task_fields correctly constructs the payload."""
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)

        self.jira_service._current_user_name = None

        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="My Summary",
            status="incomplete",
            assignee_name="assignee_user_name",
            due_date="2025-01-15",
            original_page_version=1,
            original_page_version_by="ConfluenceUser",
            original_page_version_when="now",
            context="This is the context.",
        )
        parent_key = "PROJ-123"
        test_request_user = "APIRequester"

        result = self.jira_service.prepare_jira_task_fields(
            mock_task, parent_key, test_request_user
        )

        self.assertEqual(result["fields"]["project"]["key"], "PROJ")
        self.assertEqual(result["fields"]["summary"], "My Summary")
        self.assertEqual(
            result["fields"]["issuetype"]["id"], self.mock_config.TASK_ISSUE_TYPE_ID
        )
        self.assertEqual(result["fields"]["duedate"], "2025-01-15")
        self.assertEqual(result["fields"]["assignee"]["name"], "assignee_user_name")

        self.assertEqual(
            result["fields"][self.mock_config.JIRA_PARENT_WP_CUSTOM_FIELD_ID],
            parent_key,
        )
        self.assertNotIn(self.mock_config.JIRA_PROJECT_ISSUE_TYPE_ID, result["fields"])
        self.assertNotIn(self.mock_config.JIRA_PHASE_ISSUE_TYPE_ID, result["fields"])

        expected_description = (
            "Context from Confluence:\nThis is the context.\n\n"
            f"Created by AutomationBot on 2025-01-01 12:00:00 requested by {test_request_user}"
        )
        self.assertEqual(result["fields"]["description"], expected_description)

    @patch("src.services.jira_service.datetime")
    def test_prepare_jira_task_fields_with_default_request_user(self, mock_datetime):
        """
        Test that `prepare_jira_task_fields` correctly handles the default
        'jira-user' value when passed from create_issue's default.
        """
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)

        self.jira_service._current_user_name = None

        mock_task = ConfluenceTask(
            confluence_page_id="1",
            confluence_page_title="My Page",
            confluence_page_url="http://page.url",
            confluence_task_id="t1",
            task_summary="My Summary",
            status="incomplete",
            assignee_name=None,
            due_date=self.mock_config.DEFAULT_DUE_DATE,
            original_page_version=1,
            original_page_version_by="AnotherConfluenceUser",
            original_page_version_when="now",
            context=None,
        )
        parent_key = "ANOTHER-456"
        test_default_user = "jira-user"

        result = self.jira_service.prepare_jira_task_fields(
            mock_task, parent_key, test_default_user
        )

        self.assertEqual(result["fields"]["project"]["key"], "ANOTHER")
        self.assertEqual(result["fields"]["summary"], "My Summary")
        self.assertEqual(
            result["fields"]["issuetype"]["id"], self.mock_config.TASK_ISSUE_TYPE_ID
        )
        self.assertEqual(result["fields"]["duedate"], self.mock_config.DEFAULT_DUE_DATE)
        self.assertNotIn("assignee", result["fields"])

        self.assertEqual(
            result["fields"][self.mock_config.JIRA_PARENT_WP_CUSTOM_FIELD_ID],
            parent_key,
        )
        self.assertNotIn(self.mock_config.JIRA_PROJECT_ISSUE_TYPE_ID, result["fields"])
        self.assertNotIn(self.mock_config.JIRA_PHASE_ISSUE_TYPE_ID, result["fields"])

        expected_description = f"Created by AutomationBot on 2025-01-01 12:00:00 requested by {test_default_user}"
        self.assertEqual(result["fields"]["description"], expected_description)

    @patch("src.services.jira_service.JiraService.prepare_jira_task_fields")
    def test_create_issue_delegates_and_prepares_fields(self, mock_prepare_fields):
        """
        Test that create_issue correctly prepares fields and calls the API,
        handling both explicit and default request_user.
        """
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
            context="test context",
        )
        parent_key = "PARENT-1"
        expected_jira_key = "NEWISSUE-1"

        prepared_fields_payload = {
            "fields": {
                "project": {"key": "PARENT"},
                "summary": "Test Task",
                "issuetype": {"id": self.mock_config.TASK_ISSUE_TYPE_ID},
                "description": "Prepared description",
                "parent": {"key": parent_key},
                "assignee": {"name": "test_assignee"},
            }
        }
        mock_prepare_fields.return_value = prepared_fields_payload
        self.mock_safe_jira_api.create_issue.return_value = expected_jira_key

        # Test case 1: Explicit request_user
        explicit_request_user = "ExplicitUser"
        jira_key_explicit = self.jira_service.create_issue(
            mock_task, parent_key, explicit_request_user
        )

        self.assertEqual(jira_key_explicit, expected_jira_key)
        mock_prepare_fields.assert_called_once_with(
            mock_task, parent_key, explicit_request_user
        )
        self.mock_safe_jira_api.create_issue.assert_called_once_with(
            prepared_fields_payload
        )

        mock_prepare_fields.reset_mock()
        self.mock_safe_jira_api.create_issue.reset_mock()

        # Test case 2: Default request_user (no request_user provided in call to create_issue)
        jira_key_default = self.jira_service.create_issue(mock_task, parent_key)

        self.assertEqual(jira_key_default, expected_jira_key)
        mock_prepare_fields.assert_called_once_with(mock_task, parent_key, "jira-user")
        self.mock_safe_jira_api.create_issue.assert_called_once_with(
            prepared_fields_payload
        )

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
            due_date=self.mock_config.DEFAULT_DUE_DATE,
            original_page_version=1,
            original_page_version_by="author",
            original_page_version_when="now",
            context=None,
        )
        parent_key = "FAIL-1"

        prepared_fields_payload = {
            "fields": {
                "project": {"key": "FAIL"},
                "summary": "Failing Task",
                "issuetype": {"id": self.mock_config.TASK_ISSUE_TYPE_ID},
                "description": "Failing description",
                "parent": {"key": parent_key},
            }
        }
        with patch(
            "src.services.jira_service.JiraService.prepare_jira_task_fields",
            return_value=prepared_fields_payload,
        ) as mock_prepare_fields_call:
            self.mock_safe_jira_api.create_issue.return_value = None

            result_key = self.jira_service.create_issue(
                mock_task, parent_key, "TestUser"
            )

            self.assertIsNone(result_key)
            mock_prepare_fields_call.assert_called_once()
            self.mock_safe_jira_api.create_issue.assert_called_once()

    def test_search_issues_by_jql_delegation(self):
        """Test that search_issues_by_jql delegates to SafeJiraApi correctly."""
        mock_issues = [{"key": "JQL-1"}]
        self.mock_safe_jira_api.search_issues.return_value = mock_issues

        jql_query = "project = ABC AND status = Done"
        result = self.jira_service.search_issues_by_jql(jql_query, fields="key")

        self.assertEqual(result, mock_issues)
        self.mock_safe_jira_api.search_issues.assert_called_once_with(
            jql_query, fields="key"
        )

    def test_get_issue_type_name_by_id_success(self):
        """Test get_issue_type_name_by_id returns the correct name."""
        mock_issue_type_details = {"id": "10000", "name": "Epic"}
        self.mock_safe_jira_api.get_issue_type_details_by_id.return_value = (
            mock_issue_type_details
        )

        type_name = self.jira_service.get_issue_type_name_by_id("10000")

        self.assertEqual(type_name, "Epic")
        self.mock_safe_jira_api.get_issue_type_details_by_id.assert_called_once_with(
            "10000"
        )

    def test_get_issue_type_name_by_id_failure(self):
        """Test get_issue_type_name_by_id returns None on API failure."""
        self.mock_safe_jira_api.get_issue_type_details_by_id.return_value = None

        type_name = self.jira_service.get_issue_type_name_by_id("99999")

        self.assertIsNone(type_name)
        self.mock_safe_jira_api.get_issue_type_details_by_id.assert_called_once_with(
            "99999"
        )


if __name__ == "__main__":
    unittest.main()
