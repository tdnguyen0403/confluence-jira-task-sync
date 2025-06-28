import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
import logging
import pandas as pd

# Disable logging for cleaner test output
logging.disable(logging.CRITICAL)

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
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.mock_jira_service = Mock(spec=ApiServiceInterface)
        self.mock_issue_finder = Mock(spec=IssueFinderService)
        
        self.orchestrator = AutomationOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service,
            self.mock_issue_finder
        )

    @patch('main.open', new_callable=unittest.mock.mock_open, read_data='{}')
    @patch('main.json.load')
    @patch('main.AutomationOrchestrator._save_results')
    def test_run_with_incomplete_task_in_dev_mode(self, mock_save, mock_json_load, mock_open):
        """Verify an incomplete task is created and transitioned to Backlog in dev mode."""
        config.PRODUCTION_MODE = False
        mock_json_load.return_value = {"ConfluencePageURLs": ["http://test.url/123"]}
        
        self.mock_confluence_service.get_page_id_from_url.return_value = "123"
        self.mock_confluence_service.get_all_descendants.return_value = []
        
        task1 = ConfluenceTask(
            confluence_page_id='123',
            task_summary='Task 1',
            confluence_task_id='t1',
            status='incomplete',
            assignee_name='user',
            due_date='2025-01-01',
            original_page_version=1,
            confluence_page_title='Page 1',
            confluence_page_url='/page1',
            original_page_version_by='user',
            original_page_version_when='now'
        )
        
        self.mock_confluence_service.get_tasks_from_page.return_value = [task1]
        self.mock_issue_finder.find_issue_on_page.return_value = {"key": "WP-1"}
        self.mock_jira_service.create_issue.return_value = {"key": "JIRA-1"}
        self.mock_jira_service.prepare_jira_task_fields.return_value = {}

        self.orchestrator.run()

        self.mock_jira_service.transition_issue.assert_called_once_with("JIRA-1", config.JIRA_TARGET_STATUSES['new_task_dev'])

    @patch('main.open', new_callable=unittest.mock.mock_open, read_data='{}')
    @patch('main.json.load')
    @patch('main.AutomationOrchestrator._save_results')
    def test_run_with_incomplete_task_in_prod_mode(self, mock_save, mock_json_load, mock_open):
        """Verify an incomplete task is created and NOT transitioned in production mode."""
        config.PRODUCTION_MODE = True
        mock_json_load.return_value = {"ConfluencePageURLs": ["http://test.url/123"]}
        
        self.mock_confluence_service.get_page_id_from_url.return_value = "123"
        self.mock_confluence_service.get_all_descendants.return_value = []
        
        task1 = ConfluenceTask(
            confluence_page_id='123',
            task_summary='Task 1',
            confluence_task_id='t1',
            status='incomplete',
            assignee_name='user',
            due_date='2025-01-01',
            original_page_version=1,
            confluence_page_title='Page 1',
            confluence_page_url='/page1',
            original_page_version_by='user',
            original_page_version_when='now'
        )
        
        self.mock_confluence_service.get_tasks_from_page.return_value = [task1]
        self.mock_issue_finder.find_issue_on_page.return_value = {"key": "WP-1"}
        self.mock_jira_service.create_issue.return_value = {"key": "JIRA-1"}

        self.orchestrator.run()

        self.mock_jira_service.create_issue.assert_called_once()
        self.mock_jira_service.transition_issue.assert_not_called()
    
    def tearDown(self):
        """Clean up logging handlers to release file resources."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
            
class TestInputFileHandling(unittest.TestCase):
    """Tests for handling of the user_input.json file."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.mock_jira_service = Mock(spec=ApiServiceInterface)
        self.mock_issue_finder = Mock(spec=IssueFinderService)
        
        self.orchestrator = AutomationOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service,
            self.mock_issue_finder
        )

    @patch('main.open')
    def test_run_input_file_not_found(self, mock_open):
        """Verify the script handles a missing user_input.json file gracefully."""
        mock_open.side_effect = FileNotFoundError
        self.orchestrator.run()
        self.mock_confluence_service.get_page_id_from_url.assert_not_called()

    @patch('main.open', new_callable=unittest.mock.mock_open, read_data='{"bad json"}')
    @patch('main.json.load')
    def test_run_bad_json_format(self, mock_json_load, mock_open):
        """Verify the script handles a malformed JSON file."""
        mock_json_load.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        self.orchestrator.run()
        self.mock_confluence_service.get_page_id_from_url.assert_not_called()

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

    @patch('undo_automation.os.path.exists', return_value=True)
    @patch('undo_automation.UndoOrchestrator._find_latest_results_file', return_value="dummy_path.json")
    @patch('undo_automation.open')
    @patch('undo_automation.json.load')
    def test_undo_run(self, mock_json_load, mock_open, mock_find_file, mock_exists):
        """Verify the full undo workflow."""
        mock_data = [
            {"Status": "Success", "New Jira Task Key": "JIRA-101", "confluence_page_id": 12345, "original_page_version": 2},
            {"Status": "Success - Completed Task Created", "New Jira Task Key": "JIRA-102", "confluence_page_id": 12345, "original_page_version": 2}
        ]
        mock_json_load.return_value = mock_data

        self.mock_confluence_service.get_page_by_id.return_value = {
            "title": "Test Page",
            "body": {"storage": {"value": "Old content"}}
        }
        self.undo_orchestrator.run()

        self.assertEqual(self.mock_jira_service.transition_issue.call_count, 2)
        self.assertEqual(self.mock_confluence_service.update_page_content.call_count, 1)
        self.mock_confluence_service.update_page_content.assert_called_with('12345', 'Test Page', 'Old content')
    
    @patch('undo_automation.UndoOrchestrator._find_latest_results_file', return_value=None)
    def test_undo_run_no_results_file(self, mock_find_file):
        """Verify the undo script handles a missing results file."""
        self.undo_orchestrator.run()
        # No actions should be taken if the results file doesn't exist.
        self.mock_jira_service.transition_issue.assert_not_called()
        self.mock_confluence_service.update_page_content.assert_not_called()

    def tearDown(self):
        """Clean up logging handlers after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

if __name__ == '__main__':
    unittest.main()