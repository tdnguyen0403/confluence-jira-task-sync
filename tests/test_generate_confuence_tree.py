import unittest
from unittest.mock import Mock, patch
import sys
import os
import logging

# Disable logging for cleaner test output
logging.disable(logging.CRITICAL)

from generate_confluence_tree import TestDataGenerator
from interfaces.api_service_interface import ApiServiceInterface
import config

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestTestDataGenerator(unittest.TestCase):
    """Tests the Confluence test data generator."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ApiServiceInterface)
        self.generator = TestDataGenerator(self.mock_confluence_service)

    def tearDown(self):
        """Clean up logging handlers to release file resources."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    @patch('generate_confluence_tree.setup_logging')
    def test_run_successful_generation(self, mock_setup_logging):
        """Verify the full workflow for generating a test data tree."""
        self.mock_confluence_service.get_user_details_by_username.return_value = {"userKey": "test-user-key"}
        self.mock_confluence_service.create_page.side_effect = [
            {"id": "main-page-id", "_links": {"webui": "/main"}},
            {"id": "child-1", "_links": {"webui": "/child1"}},
        ]

        self.generator.run(
            base_parent_id="parent-id",
            wp_keys=["WP-1"],
            max_depth=1,
            tasks_per_page=5
        )

        self.assertEqual(self.mock_confluence_service.create_page.call_count, 2)
        self.assertEqual(len(self.generator.all_created_pages), 2)
        self.assertEqual(self.generator.task_counter, 10)

    @patch('generate_confluence_tree.setup_logging')
    def test_run_no_wp_keys(self, mock_setup_logging):
        """Verify that the generator handles cases where no work package keys are provided."""
        
        self.generator.run(base_parent_id="parent-id", wp_keys=[], max_depth=1, tasks_per_page=1)

        # Assert that no pages were created
        self.mock_confluence_service.create_page.assert_not_called()

if __name__ == '__main__':
    unittest.main()