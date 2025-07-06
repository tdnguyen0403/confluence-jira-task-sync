"""
Unit tests for the Confluence Test Data Generator.

This module contains tests for the `TestDataGenerator` class, which is used
to create a hierarchy of test pages in Confluence. The tests use mocking to
isolate the generator from its service dependencies, allowing for focused
testing of its logic without making real API calls.
"""

import logging
import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to the system path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import config
from src.generate_confluence_tree import TestDataGenerator
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestTestDataGenerator(unittest.TestCase):
    """
    Test suite for the Confluence test data generator.
    """

    def setUp(self):
        """
        Set up the test environment before each test case.

        This method creates a mock object for the Confluence service and
        initializes the `TestDataGenerator` with this mock.
        """
        self.mock_confluence_service = Mock(spec=ConfluenceApiServiceInterface)
        self.generator = TestDataGenerator(self.mock_confluence_service)

    def tearDown(self):
        """
        Clean up logging handlers after each test to prevent side effects.

        This ensures that file resources from logging are released properly.
        """
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    @patch("src.generate_confluence_tree.setup_logging")
    def test_run_successful_generation(self, mock_setup_logging):
        """
        Verifies the full workflow for generating a test data tree.

        Arrange:
            - Mock the Confluence service to simulate successful user lookups
              and page creations.
        Act:
            - Call the `run` method of the generator with valid parameters.
        Assert:
            - The `create_page` method is called the correct number of times
              (once for the root, once for the child).
            - The total number of created pages and tasks are correctly tracked.
        """
        # Arrange
        self.mock_confluence_service.get_user_details_by_username.return_value = {
            "userKey": "test-user-key"
        }
        # Simulate the creation of a root page and one child page.
        self.mock_confluence_service.create_page.side_effect = [
            {"id": "main-page-id", "_links": {"webui": "/main"}},
            {"id": "child-1", "_links": {"webui": "/child1"}},
        ]

        # Act
        self.generator.run(
            base_parent_id="parent-id",
            wp_keys=["WP-1"],
            max_depth=1,
            tasks_per_page=5,
        )

        # Assert
        self.assertEqual(self.mock_confluence_service.create_page.call_count, 2)
        self.assertEqual(len(self.generator.all_created_pages), 2)
        # 5 tasks on the root page + 5 tasks on the child page = 10
        self.assertEqual(self.generator.task_counter, 10)

    @patch("src.generate_confluence_tree.setup_logging")
    def test_run_aborts_with_no_wp_keys(self, mock_setup_logging):
        """
        Verifies that the generator handles cases where no work package keys
        are provided, which is a required input.

        Arrange:
            - An empty list is provided for `wp_keys`.
        Act:
            - Call the `run` method of the generator.
        Assert:
            - The `create_page` method is never called, as the run should
              abort early.
        """
        # Act
        self.generator.run(
            base_parent_id="parent-id", wp_keys=[], max_depth=1, tasks_per_page=1
        )

        # Assert
        self.mock_confluence_service.create_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()
