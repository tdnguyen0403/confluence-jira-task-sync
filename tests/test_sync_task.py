import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
import logging
import pandas as pd

# Disable logging for cleaner test output
logging.disable(logging.CRITICAL)

from src.sync_task import SyncTaskOrchestrator
from src.interfaces.api_service_interface import ApiServiceInterface
from src.services.issue_finder_service import IssueFinderService
from src.models.data_models import ConfluenceTask
from src.config import config

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestSyncTaskOrchestrator(unittest.TestCase):
    """Tests the sync_task high-level automation workflow."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.mock_jira_service = Mock(spec=ApiServiceInterface)
        self.mock_issue_finder = Mock(spec=IssueFinderService)
        
        self.orchestrator = SyncTaskOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service,
            self.mock_issue_finder
        )
        
    @patch('src.sync_task.open', new_callable=unittest.mock.mock_open, read_data='{}')
    @patch('src.sync_task.json.load')
    @patch('src.sync_task.SyncTaskOrchestrator._save_results')
    def test_run_skips_empty_task(self, mock_save, mock_json_load, mock_open):
        """
        Verify that a task with an empty summary is skipped.
        """
        # 1. Arrange
        # Mock the input file to provide a URL for the orchestrator to run.
        mock_json_load.return_value = {"ConfluencePageURLs": ["http://test.url/12345"]}
        
        # Create a task with an empty summary.
        empty_task = ConfluenceTask(
            confluence_page_id='12345',
            task_summary='',  # This is the important part
            confluence_task_id='empty_task_id',
            status='incomplete',
            assignee_name=None,
            due_date=None,
            original_page_version=1,
            confluence_page_title='Test Page',
            confluence_page_url='/test-page',
            original_page_version_by='test_user',
            original_page_version_when='now'
        )

        # Set up the mock service calls that happen before task processing.
        self.mock_confluence_service.get_page_id_from_url.return_value = "12345"
        self.mock_confluence_service.get_all_descendants.return_value = []
        self.mock_confluence_service.get_tasks_from_page.return_value = [empty_task]

        # 2. Act
        # Run the main orchestration logic.
        self.orchestrator.run()

        # 3. Assert
        # The main check: Ensure that no attempt was ever made to create a Jira issue.
        self.mock_jira_service.create_issue.assert_not_called()
        
    @patch('src.sync_task.open', new_callable=unittest.mock.mock_open, read_data='{}')
    @patch('src.sync_task.json.load')
    @patch('src.sync_task.SyncTaskOrchestrator._save_results')
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

    @patch('src.sync_task.open', new_callable=unittest.mock.mock_open, read_data='{}')
    @patch('src.sync_task.json.load')
    @patch('src.sync_task.SyncTaskOrchestrator._save_results')
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
        
        self.orchestrator = SyncTaskOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service,
            self.mock_issue_finder
        )

    @patch('src.sync_task.open')
    def test_run_input_file_not_found(self, mock_open):
        """Verify the script handles a missing user_input.json file gracefully."""
        mock_open.side_effect = FileNotFoundError
        self.orchestrator.run()
        self.mock_confluence_service.get_page_id_from_url.assert_not_called()

    @patch('src.sync_task.open', new_callable=unittest.mock.mock_open, read_data='{"bad json"}')
    @patch('src.sync_task.json.load')
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



if __name__ == '__sync_task__':
    unittest.sync_task()