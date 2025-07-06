import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
import logging
import pandas as pd

logging.disable(logging.CRITICAL)

from src.undo_sync_task import UndoSyncTaskOrchestrator
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import ConfluenceTask
from src.config import config
from src.exceptions import InvalidInputError, MissingRequiredDataError # Import custom exceptions

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestUndoSyncTaskOrchestrator(unittest.TestCase):
    """Tests the high-level undo workflow."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ConfluenceApiServiceInterface)
        self.mock_jira_service = Mock(spec=JiraApiServiceInterface)
        
        self.undo_orchestrator = UndoSyncTaskOrchestrator(
            self.mock_confluence_service,
            self.mock_jira_service
        )
    def test_undo_run(self):
        """Verify the full undo workflow with direct JSON data."""
        mock_data = [
            {"Status": "Success", "New Jira Task Key": "JIRA-101", "confluence_page_id": "12345", "original_page_version": 2, "Request User": "test_user"},
            {"Status": "Success - Completed Task Created", "New Jira Task Key": "JIRA-102", "confluence_page_id": "12345", "original_page_version": 2, "Request User": "test_user"}
        ]
        
        self.mock_confluence_service.get_page_by_id.return_value = {
            "title": "Test Page",
            "body": {"storage": {"value": "Old content"}}
        }
        self.undo_orchestrator.run(results_json_data=mock_data)

        self.assertEqual(self.mock_jira_service.transition_issue.call_count, 2)
        self.assertEqual(self.mock_confluence_service.update_page_content.call_count, 1)
        self.mock_confluence_service.update_page_content.assert_called_with('12345', 'Test Page', 'Old content')
    
    def test_undo_run_empty_or_no_results_json_data(self):
        """Verify the undo script aborts if no or empty JSON data is provided by raising InvalidInputError."""
        with self.assertRaises(InvalidInputError) as cm: # Assert it raises the specific error
            self.undo_orchestrator.run(results_json_data=[])
        self.assertIn("No results JSON data provided", str(cm.exception)) # Check exception message

        # No actions should be taken if the results JSON is empty.
        self.mock_jira_service.transition_issue.assert_not_called()
        self.mock_confluence_service.update_page_content.assert_not_called()



    def test_undo_run_missing_required_columns(self):
        """Verify the undo script aborts if JSON data has missing required columns by raising MissingRequiredDataError."""
        mock_data = [
            {"Status": "Success", "New Jira Task Key": "JIRA-101", "original_page_version": 2} # Missing confluence_page_id
        ]
        with self.assertRaises(MissingRequiredDataError) as cm: # Assert it raises the specific error
            self.undo_orchestrator.run(results_json_data=mock_data)
        self.assertIn("Results data is missing required columns", str(cm.exception)) # Check exception message

        self.mock_jira_service.transition_issue.assert_not_called()
        self.mock_confluence_service.update_page_content.assert_not_called()

    def tearDown(self):
        """Clean up logging handlers after each test."""
        # This tearDown might still be necessary if other parts of the test suite
        # (not shown) add handlers or if the test environment has other complexities.
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

if __name__ == '__main__':
    unittest.main()