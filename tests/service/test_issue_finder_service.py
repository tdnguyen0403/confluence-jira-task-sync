"""
Unit tests for the IssueFinderService class.

This module tests the specialized IssueFinderService, which is responsible for
finding the parent Jira issue (e.g., a Work Package) on a Confluence page.
"""

import logging
import os
import sys
import unittest
from unittest.mock import Mock

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.services.issue_finder_service import IssueFinderService

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestIssueFinderService(unittest.TestCase):
    """Tests the specialized IssueFinderService."""

    def setUp(self):
        """Set up mock APIs and the finder service for each test."""
        self.mock_confluence_api = Mock(spec=SafeConfluenceApi)
        self.mock_jira_api = Mock(spec=SafeJiraApi)
        self.issue_finder = IssueFinderService(
            self.mock_confluence_api, self.mock_jira_api
        )

    def tearDown(self):
        """Reset mocks after each test to prevent side effects."""
        self.mock_jira_api.reset_mock()

    def test_find_issue_on_page_success_work_package(self):
        """Test finding a work package successfully."""
        page_html = """
             <div><ac:structured-macro ac:name="jira">
                 <ac:parameter ac:name="key">WP-1</ac:parameter>
             </ac:structured-macro></div>"""
        self.mock_confluence_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": page_html}}
        }
        # Mock the two API calls: first to check type, second to get details.
        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Work Package"]}}},
            {"key": "WP-1", "fields": {"summary": "Full WP Details"}},
        ]

        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "WP-1")
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)
        self.mock_jira_api.get_issue.assert_any_call("WP-1", fields="issuetype")
        self.mock_jira_api.get_issue.assert_any_call(
            "WP-1", fields="key,issuetype,assignee,reporter"
        )

    def test_find_issue_on_page_success_risk(self):
        """Test finding a Risk issue successfully."""
        page_html = """
            <div><ac:structured-macro ac:name="jira">
                <ac:parameter ac:name="key">RISK-1</ac:parameter>
            </ac:structured-macro></div>"""
        self.mock_confluence_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": page_html}}
        }
        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Risk"]}}},
            {"key": "RISK-1", "fields": {"summary": "Full Risk Details"}},
        ]

        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "RISK-1")
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)

    def test_find_issue_on_page_success_deviation(self):
        """Test finding a Deviation issue successfully."""
        page_html = """
            <div><ac:structured-macro ac:name="jira">
                <ac:parameter ac:name="key">DEV-1</ac:parameter>
            </ac:structured-macro></div>"""
        self.mock_confluence_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": page_html}}
        }
        self.mock_jira_api.get_issue.side_effect = [
            {"fields": {"issuetype": {"id": config.PARENT_ISSUES_TYPE_ID["Deviation"]}}},
            {"key": "DEV-1", "fields": {"summary": "Full Deviation Details"}},
        ]

        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["key"], "DEV-1")
        self.assertEqual(self.mock_jira_api.get_issue.call_count, 2)

    def test_find_issue_on_page_not_found(self):
        """Test when no matching macro is on the page."""
        page_html = "<p>No Jira macros here.</p>"
        self.mock_confluence_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": page_html}}
        }

        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )

        self.assertIsNone(result)
        self.mock_jira_api.get_issue.assert_not_called()

    def test_find_issue_on_page_wrong_issue_type(self):
        """Test that a Jira macro with a non-target issue type is ignored."""
        page_html = """
            <ac:structured-macro ac:name="jira">
                <ac:parameter ac:name="key">TASK-123</ac:parameter>
            </ac:structured-macro>"""
        self.mock_confluence_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": page_html}}
        }
        # Simulate returning an issue type that is not a parent type.
        self.mock_jira_api.get_issue.return_value = {
            "fields": {"issuetype": {"id": config.TASK_ISSUE_TYPE_ID}}
        }

        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )

        self.assertIsNone(result)
        self.mock_jira_api.get_issue.assert_called_once_with(
            "TASK-123", fields="issuetype"
        )

    def test_find_issue_on_page_no_page_content(self):
        """Test the finder when the Confluence API returns no content."""
        self.mock_confluence_api.get_page_by_id.return_value = None
        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )
        self.assertIsNone(result)
        self.mock_jira_api.get_issue.assert_not_called()

    def test_find_issue_on_page_in_ignored_macro(self):
        """Test that a Jira macro inside an aggregation macro is ignored."""
        # Test with one of the aggregation macros.
        macro_name = "excerpt"
        page_html = f"""
            <ac:structured-macro ac:name="{macro_name}">
                <ac:rich-text-body>
                    <ac:structured-macro ac:name="jira">
                        <ac:parameter ac:name="key">WP-999</ac:parameter>
                    </ac:structured-macro>
                </ac:rich-text-body>
            </ac:structured-macro>
        """
        self.mock_confluence_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": page_html}}
        }

        result = self.issue_finder.find_issue_on_page(
            "123", config.PARENT_ISSUES_TYPE_ID
        )

        self.assertIsNone(result)
        self.mock_jira_api.get_issue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
