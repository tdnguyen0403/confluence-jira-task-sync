import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import logging
from datetime import datetime
import uuid  # Import uuid for creating mock UUID objects
from bs4 import BeautifulSoup  # Added: Import BeautifulSoup for HTML parsing

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.scripts.generate_confluence_tree import ConfluenceTreeGenerator
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business_logic.issue_finder_service import IssueFinderService


logging.disable(logging.CRITICAL)  # Disable logging during tests


class TestConfluenceTreeGenerator(unittest.TestCase):
    """Unit tests for the ConfluenceTreeGenerator class."""

    def setUp(self):
        self.mock_confluence_service = Mock(spec=ConfluenceService)
        self.mock_jira_service = Mock(spec=JiraService)
        self.mock_issue_finder_service = Mock(spec=IssueFinderService)

        # Set up mock config values used by the generator
        self.mock_config_patcher = patch("src.scripts.generate_confluence_tree.config")
        self.mock_config = self.mock_config_patcher.start()
        self.mock_config.JIRA_MACRO_SERVER_NAME = "TestJiraServer"
        self.mock_config.JIRA_MACRO_SERVER_ID = "TestJiraServerId"
        self.mock_config.DEFAULT_DUE_DATE = "2025-01-01"
        self.mock_config.BASE_PARENT_CONFLUENCE_PAGE_ID = "base_parent_id"
        self.mock_config.CONFLUENCE_SPACE_KEY = "TESTSPACE"
        self.mock_config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS = "testuser"
        self.mock_config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE = ["WP-1", "WP-2"]
        self.mock_config.DEFAULT_MAX_DEPTH = 1
        self.mock_config.DEFAULT_TASKS_PER_PAGE = 1
        self.mock_config.DEFAULT_NUM_WORK_PACKAGES = 2

        # Simplify mock UUID objects - they just need a .hex attribute now
        # Their exact string representation or specific hex value is less critical
        self.mock_uuid_obj_1 = MagicMock(spec=uuid.UUID)
        self.mock_uuid_obj_1.hex = "jira_macro_uuid_abc"

        self.mock_uuid_obj_2 = MagicMock(spec=uuid.UUID)
        self.mock_uuid_obj_2.hex = (
            "task_id_uuid_xyz"  # This will be sliced to [:4] in app code
        )

        self.mock_uuid4_patcher = patch(
            "src.scripts.generate_confluence_tree.uuid.uuid4",
            side_effect=[
                self.mock_uuid_obj_1,
                self.mock_uuid_obj_2,
            ],  # Provide only as many as needed by test
        )
        self.mock_uuid4 = self.mock_uuid4_patcher.start()

        # Configure mock service return values
        self.mock_confluence_service.get_user_details_by_username.return_value = {
            "accountId": "test_account_id"
        }
        self.mock_confluence_service.create_page.return_value = {
            "id": "new_page_id",
            "_links": {"webui": "/new/page/url"},
        }

        self.generator = ConfluenceTreeGenerator(
            confluence_service=self.mock_confluence_service,
            jira_service=self.mock_jira_service,
            issue_finder_service=self.mock_issue_finder_service,
            base_parent_page_id=self.mock_config.BASE_PARENT_CONFLUENCE_PAGE_ID,
            confluence_space_key=self.mock_config.CONFLUENCE_SPACE_KEY,
            assignee_username=self.mock_config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS,
            test_work_package_keys=self.mock_config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE,
            max_depth=self.mock_config.DEFAULT_MAX_DEPTH,
            tasks_per_page=self.mock_config.DEFAULT_TASKS_PER_PAGE,
        )

    def tearDown(self):
        """Clean up patches after each test."""
        self.mock_config_patcher.stop()
        self.mock_uuid4_patcher.stop()
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    def test_init(self):
        """Verify initialization sets up attributes correctly."""
        self.assertEqual(self.generator.base_parent_page_id, "base_parent_id")
        self.assertEqual(self.generator.assignee_account_id, "test_account_id")
        self.mock_confluence_service.get_user_details_by_username.assert_called_once_with(
            "testuser"
        )

    @patch("src.scripts.generate_confluence_tree.datetime")
    def test_generate_page_hierarchy_single_page(self, mock_datetime):
        """Test generating a single page with tasks and a WP link."""
        mock_datetime.now.return_value = datetime(2025, 7, 5, 10, 0, 0)
        mock_time_str = mock_datetime.now().strftime("%H%M%S")

        self.mock_confluence_service.create_page.return_value = {
            "id": "new_page_id",
            "_links": {"webui": "/new/page/url"},
        }

        expected_page_title = "Test Page (Depth 0-0) 20250705100000"
        expected_wp_key = "WP-1"
        expected_task_summary_part = (
            f"Generated Task 0 for {expected_wp_key} ({mock_time_str})"
        )

        results = self.generator.generate_page_hierarchy(
            parent_page_id="base_parent_id"
        )

        # Assert create_page was called with correct basic arguments
        self.mock_confluence_service.create_page.assert_called_once_with(
            space="TESTSPACE",
            title=expected_page_title,
            body=unittest.mock.ANY,  # Use ANY to not assert the whole HTML string
            parent_id="base_parent_id",
        )

        # Now, get the actual body argument passed to create_page
        actual_body_html = self.mock_confluence_service.create_page.call_args[1]["body"]
        soup = BeautifulSoup(actual_body_html, "html.parser")

        # Assert the presence and content of the Jira macro
        jira_macro = soup.find("ac:structured-macro", {"ac:name": "jira"})
        self.assertIsNotNone(jira_macro, "Jira macro not found in page body.")
        self.assertEqual(
            jira_macro.find("ac:parameter", {"ac:name": "key"}).get_text(strip=True),
            expected_wp_key,
            "Jira macro key does not match expected Work Package.",
        )
        self.assertIsNotNone(jira_macro.get("ac:macro-id"), "Jira macro ID is missing.")

        # Assert the presence and content of the tasks
        task_elements = soup.find_all("ac:task")
        self.assertEqual(
            len(task_elements),
            self.mock_config.DEFAULT_TASKS_PER_PAGE,
            "Incorrect number of tasks generated.",
        )

        for task_elem in task_elements:
            task_id_tag = task_elem.find("ac:task-id")
            task_summary_span = task_elem.find("ac:task-body").find("span")
            task_assignee = task_elem.find("ac:task-assignee")
            task_due_date = task_elem.find("time")

            self.assertIsNotNone(task_id_tag, "Task ID tag missing.")
            self.assertIsNotNone(
                task_id_tag.get_text(strip=True), "Task ID is empty."
            )  # Just check presence, not exact ID
            self.assertTrue(
                task_summary_span.get_text(strip=True).startswith(
                    expected_task_summary_part
                ),
                "Task summary does not start with expected text.",
            )
            self.assertIsNotNone(task_assignee, "Task assignee tag missing.")
            self.assertEqual(
                task_assignee.get("ac:account-id"),
                "test_account_id",
                "Task assignee account ID mismatch.",
            )
            self.assertIsNotNone(task_due_date, "Task due date tag missing.")
            self.assertEqual(
                task_due_date.get("datetime"), "2025-01-01", "Task due date mismatch."
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "/new/page/url")
        self.assertEqual(results[0]["linked_work_package"], expected_wp_key)

    def test_generate_page_hierarchy_max_depth_zero(self):
        """Test that no pages are generated if max_depth is 0."""
        self.generator.max_depth = 0
        results = self.generator.generate_page_hierarchy(
            parent_page_id="base_parent_id"
        )
        self.assertEqual(len(results), 0)
        self.mock_confluence_service.create_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()
