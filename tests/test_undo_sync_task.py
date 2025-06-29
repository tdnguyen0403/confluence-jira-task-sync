import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
import logging
import pandas as pd

# Disable logging for cleaner test output
logging.disable(logging.CRITICAL)

from src.undo_sync_task import UndoSyncTaskOrchestrator
from src.interfaces.api_service_interface import ApiServiceInterface
from src.services.issue_finder_service import IssueFinderService
from src.models.data_models import ConfluenceTask
from src.config import config

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestUndoSyncTaskOrchestrator(unittest.TestCase):
    """Tests the high-level undo workflow."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.mock_jira_service = Mock(spec=ApiServiceInterface)
        
        self.undo_orchestrator = UndoSyncTaskOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service
        )

    @patch('src.undo_sync_task.os.path.exists', return_value=True)
    @patch('src.undo_sync_task.UndoSyncTaskOrchestrator._find_latest_results_file', return_value="dummy_path.json")
    @patch('src.undo_sync_task.open')
    @patch('src.undo_sync_task.json.load')
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
    
    @patch('src.undo_sync_task.UndoSyncTaskOrchestrator._find_latest_results_file', return_value=None)
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

if __name__ == '__sync_task__':
    unittest.sync_task()