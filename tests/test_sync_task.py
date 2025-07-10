import unittest
from unittest.mock import Mock
import sys
import os
import logging

from src.sync_task import SyncTaskOrchestrator
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.services.issue_finder_service import IssueFinderService
from src.models.data_models import ConfluenceTask
from src.config import config
from src.exceptions import InvalidInputError  # Import InvalidInputError

logging.disable(logging.CRITICAL)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestSyncTaskOrchestrator(unittest.TestCase):
    """Tests the sync_task high-level automation workflow."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ConfluenceApiServiceInterface)
        self.mock_jira_service = Mock(spec=JiraApiServiceInterface)
        self.mock_issue_finder = Mock(spec=IssueFinderService)

        self.orchestrator = SyncTaskOrchestrator(
            self.mock_confluence_service, self.mock_jira_service, self.mock_issue_finder
        )

    def test_run_skips_empty_task(self):
        """
        Verify that a task with an empty summary is skipped.
        """
        # 1. Arrange
        # Mock the input to provide a URL for the orchestrator to run.
        # Changed key from "ConfluencePageURLs" to "confluence_page_urls"
        json_input = {
            "confluence_page_urls": ["http://test.url/12345"],
            "request_user": "test_user",
        }

        # Create a task with an empty summary.
        empty_task = ConfluenceTask(
            confluence_page_id="12345",
            task_summary="",  # This is the important part
            confluence_task_id="empty_task_id",
            status="incomplete",
            assignee_name=None,
            due_date=config.DEFAULT_DUE_DATE,
            original_page_version=1,
            confluence_page_title="Test Page",
            confluence_page_url="/test-page",
            original_page_version_by="test_user",
            original_page_version_when="now",
        )

        # Set up the mock service calls that happen before task processing.
        self.mock_confluence_service.get_page_id_from_url.return_value = "12345"
        self.mock_confluence_service.get_all_descendants.return_value = []
        self.mock_confluence_service.get_tasks_from_page.return_value = [empty_task]

        # 2. Act
        # Run the main orchestration logic.
        self.orchestrator.run(json_input)

        # 3. Assert
        # The main check: Ensure that no attempt was ever made to create a Jira issue.
        self.mock_jira_service.create_issue.assert_not_called()
        self.assertEqual(
            len(self.orchestrator.results), 0
        )  # No result should be appended for empty task

    def test_run_with_incomplete_task_in_dev_mode(self):
        """Verify an incomplete task is created and transitioned to Backlog in dev mode."""
        config.PRODUCTION_MODE = False
        # Changed key from "ConfluencePageURLs" to "confluence_page_urls"
        json_input = {
            "confluence_page_urls": ["http://test.url/123"],
            "request_user": "test_user",
        }

        self.mock_confluence_service.get_page_id_from_url.return_value = "123"
        self.mock_confluence_service.get_all_descendants.return_value = []
        task1 = ConfluenceTask(
            confluence_page_id="123",
            task_summary="Task 1",
            confluence_task_id="t1",
            status="incomplete",
            assignee_name="user",
            due_date="2025-01-01",
            original_page_version=1,
            confluence_page_title="Page 1",
            confluence_page_url="/page1",
            original_page_version_by="user",
            original_page_version_when="now",
        )
        self.mock_confluence_service.get_tasks_from_page.return_value = [task1]
        self.mock_issue_finder.find_issue_on_page.return_value = {"key": "WP-1"}
        self.mock_jira_service.create_issue.return_value = {"key": "JIRA-1"}

        self.orchestrator.run(json_input)

        self.mock_jira_service.transition_issue.assert_called_once_with(
            "JIRA-1", config.JIRA_TARGET_STATUSES["new_task_dev"]
        )
        self.assertEqual(len(self.orchestrator.results), 1)
        self.assertEqual(self.orchestrator.results[0].request_user, "test_user")

    def test_run_with_incomplete_task_in_prod_mode(self):
        """Verify an incomplete task is created and NOT transitioned in production mode."""
        config.PRODUCTION_MODE = True
        # Changed key from "ConfluencePageURLs" to "confluence_page_urls"
        json_input = {
            "confluence_page_urls": ["http://test.url/123"],
            "request_user": "test_user",
        }

        self.mock_confluence_service.get_page_id_from_url.return_value = "123"
        self.mock_confluence_service.get_all_descendants.return_value = []

        task1 = ConfluenceTask(
            confluence_page_id="123",
            task_summary="Task 1",
            confluence_task_id="t1",
            status="incomplete",
            assignee_name="user",
            due_date="2025-01-01",
            original_page_version=1,
            confluence_page_title="Page 1",
            confluence_page_url="/page1",
            original_page_version_by="user",
            original_page_version_when="now",
        )

        self.mock_confluence_service.get_tasks_from_page.return_value = [task1]
        self.mock_issue_finder.find_issue_on_page.return_value = {"key": "WP-1"}
        self.mock_jira_service.create_issue.return_value = {"key": "JIRA-1"}

        self.orchestrator.run(json_input)

        self.mock_jira_service.create_issue.assert_called_once()
        self.mock_jira_service.transition_issue.assert_not_called()
        self.assertEqual(len(self.orchestrator.results), 1)
        self.assertEqual(self.orchestrator.results[0].request_user, "test_user")

    def test_run_no_confluence_page_urls_in_input(self):
        """Verify the script handles missing 'confluence_page_urls' in input JSON by raising InvalidInputError."""
        json_input = {"request_user": "test_user"}
        with self.assertRaises(
            InvalidInputError
        ) as cm:  # Assert it raises the specific error
            self.orchestrator.run(json_input)
        self.assertIn(
            "No 'confluence_page_urls' found", str(cm.exception)
        )  # Check exception message
        self.mock_confluence_service.get_page_id_from_url.assert_not_called()
        self.assertEqual(len(self.orchestrator.results), 0)

    def test_run_empty_input_json(self):
        """Verify the script handles an empty input JSON by raising InvalidInputError."""
        json_input = {}
        with self.assertRaises(
            InvalidInputError
        ) as cm:  # Assert it raises the specific error
            self.orchestrator.run(json_input)
        self.assertIn(
            "No input JSON provided", str(cm.exception)
        )  # Check exception message
        self.mock_confluence_service.get_page_id_from_url.assert_not_called()
        self.assertEqual(len(self.orchestrator.results), 0)

    def tearDown(self):
        """Clean up logging handlers to release file resources."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)


# Removed TestInputFileHandling class as file input is no longer used.

if __name__ == "__main__":  # Changed from '__sync_task__'
    unittest.main()  # Changed from unittest.sync_task()
