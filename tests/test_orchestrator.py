import unittest
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import sys
import os
import logging

from main import AutomationOrchestrator
from undo_automation import UndoOrchestrator
from interfaces.api_service_interface import ApiServiceInterface
from services.issue_finder_service import IssueFinderService
from models.data_models import ConfluenceTask
import config

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestAutomationOrchestrator(unittest.TestCase):
    """Tests the main high-level automation workflow."""

    def setUp(self):
        # Create mock objects that adhere to the service interfaces
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.mock_jira_service = Mock(spec=ApiServiceInterface)
        self.mock_issue_finder = Mock(spec=IssueFinderService)
        
        self.orchestrator = AutomationOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service,
            self.mock_issue_finder
        )

    @patch('main.pd.read_excel')
    @patch('main.AutomationOrchestrator._save_results')
    def test_run_with_tasks(self, mock_save, mock_read_excel):
        """Verify the full workflow when tasks are found."""
        mock_read_excel.return_value = pd.DataFrame([{"ConfluencePageURL": "http://test.url/123"}])
        
        self.mock_confluence_service.get_page_id_from_url.return_value = "123"
        # Correctly mock get_all_descendants to return an empty list for this test
        self.mock_confluence_service.get_all_descendants.return_value = []
        
        task1 = ConfluenceTask(confluence_page_id='123', task_summary='Task 1', confluence_task_id='t1', assignee_name='user', due_date='2025-01-01', original_page_version=1, confluence_page_title='Page 1', confluence_page_url='/page1', original_page_version_by='user', original_page_version_when='now')
        
        self.mock_confluence_service.get_page_by_id.return_value = {
            "body": {
                "storage": {
                    "value": "Dummy Content"
                }
            }
        }
        
        self.mock_confluence_service.get_tasks_from_page.return_value = [task1]
        self.mock_issue_finder.find_issue_on_page.return_value = {"key": "WP-1"}
        self.mock_jira_service.create_issue.return_value = {"key": "JIRA-1"}
        self.mock_jira_service.prepare_jira_task_fields.return_value = {} 

        self.orchestrator.run()

        # Assertions
        self.mock_confluence_service.get_page_id_from_url.assert_called_once()
        self.mock_issue_finder.find_issue_on_page.assert_called_once_with('123', config.WORK_PACKAGE_ISSUE_TYPE_ID)
        self.mock_jira_service.create_issue.assert_called_once()
        self.mock_jira_service.transition_issue.assert_called_once()
        self.mock_confluence_service.update_page_with_jira_links.assert_called_once()
        mock_save.assert_called_once()

    @patch('main.pd.read_excel')
    @patch('main.AutomationOrchestrator._save_results')
    def test_run_no_work_package(self, mock_save, mock_read_excel):
        """Verify workflow when no work package is found for a task."""
        mock_read_excel.return_value = pd.DataFrame([{"ConfluencePageURL": "http://test.url/123"}])
        
        self.mock_confluence_service.get_page_id_from_url.return_value = "123"
        self.mock_confluence_service.get_all_descendants.return_value = []
        task1 = ConfluenceTask(confluence_page_id='123', task_summary='Task 1', confluence_task_id='t1', assignee_name='user', due_date='2025-01-01', original_page_version=1, confluence_page_title='Page 1', confluence_page_url='/page1', original_page_version_by='user', original_page_version_when='now')
        
        self.mock_confluence_service.get_page_by_id.return_value = {
            "body": {
                "storage": {
                    "value": "Dummy Content"
                }
            }
        }
        
        self.mock_confluence_service.get_tasks_from_page.return_value = [task1]
        
        # Mock the finder to return None
        self.mock_issue_finder.find_issue_on_page.return_value = None

        self.orchestrator.run()

        # Assert that Jira creation was NOT called
        self.mock_jira_service.create_issue.assert_not_called()
        # Assert that the result was logged as skipped
        self.assertEqual(len(self.orchestrator.results), 1)
        self.assertEqual(self.orchestrator.results[0].status, "Skipped - No Work Package found")
        mock_save.assert_called_once()
        
    @patch('main.pd.read_excel')
    def test_run_input_file_not_found(self, mock_read_excel):
        """Verify the script handles a missing input.xlsx file gracefully."""
        mock_read_excel.side_effect = FileNotFoundError
        # We expect the orchestrator to log an error and exit, so no methods on the services should be called.
        self.orchestrator.run()
        self.mock_confluence_service.get_page_id_from_url.assert_not_called()

    @patch('main.pd.read_excel')
    def test_run_invalid_confluence_url(self, mock_read_excel):
        """Verify that an invalid Confluence URL is handled correctly."""
        mock_read_excel.return_value = pd.DataFrame([{"ConfluencePageURL": "invalid-url"}])
        self.mock_confluence_service.get_page_id_from_url.return_value = None
        self.orchestrator.run()
        self.mock_confluence_service.get_page_id_from_url.assert_called_once_with("invalid-url")
        # Ensure that no further processing happens for an invalid URL
        self.mock_confluence_service.get_all_descendants.assert_not_called()


    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

class TestUndoOrchestrator(unittest.TestCase):
    """Tests the high-level undo workflow."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.mock_jira_service = Mock(spec=ApiServiceInterface)
        
        self.undo_orchestrator = UndoOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service
        )

    # Add a patch for os.path.exists
    @patch('undo_automation.os.path.exists', return_value=True)
    @patch('undo_automation.UndoOrchestrator._find_latest_results_file', return_value="dummy_path.xlsx")
    @patch('undo_automation.pd.read_excel')
    def test_undo_run(self, mock_read_excel, mock_find_file, mock_exists):
        """Verify the full undo workflow."""
        mock_data = {
            "Status": ["Success", "Success"],
            "New Jira Task Key": ["JIRA-101", "JIRA-102"],
            "confluence_page_id": [12345, 12345],
            "original_page_version": [2, 2]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        self.mock_confluence_service.get_page_by_id.return_value = {
            "title": "Test Page",
            "body": {"storage": {"value": "Old content"}}
        }

        self.undo_orchestrator.run()

        self.assertEqual(self.mock_jira_service.transition_issue.call_count, 2)
        self.assertEqual(self.mock_confluence_service.update_page_content.call_count, 1)
        self.mock_confluence_service.update_page_content.assert_called_with('12345', 'Test Page', 'Old content')

    @patch('undo_automation.os.path.exists', return_value=False)
    def test_undo_run_no_results_file(self, mock_exists):
        """Verify the undo script handles a missing results file."""
        self.undo_orchestrator.run()
        # No actions should be taken if the results file doesn't exist.
        self.mock_jira_service.transition_issue.assert_not_called()
        self.mock_confluence_service.update_page_content.assert_not_called()

    @patch('undo_automation.os.path.exists', return_value=True)
    @patch('undo_automation.UndoOrchestrator._find_latest_results_file', return_value="dummy_path.xlsx")
    @patch('undo_automation.pd.read_excel')
    def test_undo_run_empty_results_file(self, mock_read_excel, mock_find_file, mock_exists):
        """Verify the undo script handles an empty results file."""
        mock_read_excel.return_value = pd.DataFrame()
        self.undo_orchestrator.run()
        self.mock_jira_service.transition_issue.assert_not_called()
        self.mock_confluence_service.update_page_content.assert_not_called()

    @patch('undo_automation.os.path.exists', return_value=True)
    @patch('undo_automation.UndoOrchestrator._find_latest_results_file', return_value="dummy_path.xlsx")
    @patch('undo_automation.pd.read_excel')
    def test_undo_run_results_file_missing_columns(self, mock_read_excel, mock_find_file, mock_exists):
        """Verify the undo script handles a results file with missing columns."""
        mock_data = {
            "Status": ["Success"],
            # Missing "New Jira Task Key"
            "confluence_page_id": [12345],
            "original_page_version": [2]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)
        self.undo_orchestrator.run()
        # Should not proceed with transitioning issues or rolling back pages
        self.mock_jira_service.transition_issue.assert_not_called()
        self.mock_confluence_service.update_page_content.assert_not_called()


    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

class TestConfigFailures(unittest.TestCase):
    
    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    @patch('main.config.JIRA_API_TOKEN', None)
    @patch('main.pd.read_excel')
    @patch('main.Jira')
    def test_run_with_missing_jira_token(self, mock_jira_client, mock_read_excel):
        """Verify that the application handles a missing Jira API token."""
        mock_read_excel.return_value = pd.DataFrame([{"ConfluencePageURL": "http://test.url/123"}])
        
        # Simulate the Jira client raising an exception when initialized with a bad token
        mock_jira_client.side_effect = Exception("Invalid token")

        # We expect the application to fail during initialization, so we wrap the call
        # in an assertRaises block.
        with self.assertRaises(Exception):
            # The application's entry point needs to be called to trigger the initialization
            import main
            main.main()
  
if __name__ == '__main__':
    unittest.main()