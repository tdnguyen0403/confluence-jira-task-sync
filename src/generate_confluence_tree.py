import argparse
import json
import logging
import uuid
import warnings
import sys
from datetime import datetime
from typing import Dict, List

import requests
from atlassian import Confluence, Jira

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.services.confluence_service import ConfluenceService
from src.services.issue_finder_service import IssueFinderService
from src.services.jira_service import JiraService
from src.utils.logging_config import setup_logging_local

# Suppress insecure request warnings for local/dev environments
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)

logger = logging.getLogger(__name__)


class ConfluenceTreeGenerator:
    """
    Generates a hierarchy of Confluence pages with embedded tasks for testing.
    """

    def __init__(
        self,
        confluence_service: ConfluenceService,
        jira_service: JiraService,
        issue_finder_service: IssueFinderService,
        base_parent_page_id: str,
        confluence_space_key: str,
        assignee_username: str,
        test_work_package_keys: List[str],
        max_depth: int,
        tasks_per_page: int,
    ):
        """
        Initializes the ConfluenceTreeGenerator.

        Args:
            confluence_service (ConfluenceService): Service for Confluence operations.
            jira_service (JiraService): Service for Jira operations.
            issue_finder_service (IssueFinderService): Service for finding Jira issues.
            base_parent_page_id (str): ID of the existing parent page under which
                                       new pages will be created.
            confluence_space_key (str): Key of the Confluence space.
            assignee_username (str): Username to assign tasks to.
            test_work_package_keys (List[str]): List of Jira Work Package keys to
                                                 distribute among tasks.
            max_depth (int): Maximum depth of the page hierarchy to generate.
            tasks_per_page (int): Number of tasks to generate per page.
        """
        self.confluence = confluence_service
        self.jira = jira_service
        self.issue_finder = issue_finder_service
        self.base_parent_page_id = base_parent_page_id
        self.confluence_space_key = confluence_space_key
        self.assignee_username = assignee_username
        self.test_work_package_keys = test_work_package_keys
        self.max_depth = max_depth
        self.tasks_per_page = tasks_per_page
        self.generated_page_ids: List[str] = []

        # Get assignee account ID once for efficiency
        self.assignee_account_id = None
        user_details = self.confluence.get_user_details_by_username(assignee_username)
        if user_details:
            self.assignee_account_id = user_details.get("accountId")
            logger.info(
                f"Assignee '{assignee_username}' account ID: {self.assignee_account_id}"
            )
        else:
            logger.warning(
                f"Could not find account ID for assignee: {assignee_username}. Tasks might not be assignable."
            )

    def generate_page_hierarchy(
        self, parent_page_id: str, current_depth: int = 0
    ) -> List[Dict[str, str]]:
        """
        Recursively generates a hierarchy of pages and adds tasks.

        Args:
            parent_page_id (str): The ID of the current parent page.
            current_depth (int): The current depth in the hierarchy.

        Returns:
            List[Dict[str, str]]: A list of dictionaries, each mapping a
                                  generated Confluence page URL to its linked
                                  Jira Work Package.
        """
        if current_depth >= self.max_depth:
            return []

        results: List[Dict[str, str]] = []

        num_children = 1  # Always create one child page for simplicity

        for i in range(num_children):
            page_title = f"Test Page (Depth {current_depth}-{i}) {datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info(f"Creating page: '{page_title}' under parent {parent_page_id}")

            # Include a Jira macro for a Work Package on the page for _issue_finder_service
            # Assign a random Work Package from the predefined list
            wp_key = self.test_work_package_keys[i % len(self.test_work_package_keys)]

            # Confluence storage format for Jira macro
            jira_macro_html = (
                f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">'
                f'<ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>'
                f'<ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>'
                f'<ac:parameter ac:name="key">{wp_key}</ac:parameter>'
                f"</ac:structured-macro></p>"
            )

            # Generate tasks with random completion status
            tasks_html_parts = []
            for t_idx in range(self.tasks_per_page):
                task_status = "incomplete"  # Force incomplete for sync script testing
                task_summary = f"Generated Task {t_idx} for {wp_key} ({datetime.now().strftime('%H%M%S')})"
                assignee_html = ""
                if self.assignee_account_id:
                    assignee_html = f'<ac:task-assignee ac:account-id="{self.assignee_account_id}"></ac:task-assignee>'

                tasks_html_parts.append(
                    f"<ac:task-list><ac:task><ac:task-id>{uuid.uuid4().hex[:8]}</ac:task-id>"
                    f"<ac:task-status>{task_status}</ac:task-status>"
                    f'<ac:task-body><span>{task_summary} {assignee_html}</span><time datetime="{config.DEFAULT_DUE_DATE}"></time>'
                    f"</ac:task-body></ac:task></ac:task-list>"
                )

            # Combine Jira macro and tasks into the page body
            page_body = f"{jira_macro_html}\n{''.join(tasks_html_parts)}"

            new_page = self.confluence.create_page(
                space=self.confluence_space_key,
                title=page_title,
                body=page_body,
                parent_id=parent_page_id,
            )

            if new_page:
                new_page_id = new_page["id"]
                new_page_url = new_page["_links"]["webui"]
                self.generated_page_ids.append(new_page_id)
                logger.info(f"Created page '{page_title}' (ID: {new_page_id})")
                results.append({"url": new_page_url, "linked_work_package": wp_key})

                # Recursively generate children
                results.extend(
                    self.generate_page_hierarchy(new_page_id, current_depth + 1)
                )
            else:
                logger.error(
                    f"Failed to create page '{page_title}'. Skipping children."
                )

        return results

    # Removed the cleanup_generated_pages method

    @staticmethod
    def _parse_args() -> argparse.Namespace:
        """Parses command-line arguments."""
        parser = argparse.ArgumentParser(
            description="Generate a Confluence page hierarchy with tasks for testing."
        )
        parser.add_argument(
            "--base-parent-page-id",
            type=str,
            default=config.BASE_PARENT_CONFLUENCE_PAGE_ID,
            help="ID of the existing Confluence parent page to create test pages under.",
        )
        parser.add_argument(
            "--confluence-space-key",
            type=str,
            default=config.CONFLUENCE_SPACE_KEY,
            help="Key of the Confluence space to create pages in.",
        )
        parser.add_argument(
            "--assignee-username",
            type=str,
            default=config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS,
            help="Confluence username to assign generated tasks to.",
        )
        parser.add_argument(
            "--test-work-package-keys",
            nargs="+",
            default=config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE,
            help="Space-separated list of Jira Work Package keys to distribute among tasks.",
        )
        parser.add_argument(
            "--max-depth",
            type=int,
            default=config.DEFAULT_MAX_DEPTH,
            help="Maximum depth of the page hierarchy (e.g., 2 for parent -> child).",
        )
        parser.add_argument(
            "--tasks-per-page",
            type=int,
            default=config.DEFAULT_TASKS_PER_PAGE,
            help="Number of tasks to generate per page.",
        )
        parser.add_argument(
            "--num-work-packages",
            type=int,
            default=config.DEFAULT_NUM_WORK_PACKAGES,
            help="Number of Work Packages to distribute tasks among. (Used by config for default WP keys).",
        )
        return parser.parse_args()


# The __main__ block is only for standalone execution.
if __name__ == "__main__":
    setup_logging_local("logs/logs_generate", "generate_tree_run")
    logging.info("--- Starting Confluence Test Data Generation Script ---")

    args = ConfluenceTreeGenerator._parse_args()

    if (
        args.base_parent_page_id == "YOUR_BASE_PARENT_PAGE_ID_HERE"
        or not args.base_parent_page_id
    ):
        logging.error(
            "Please provide a valid --base-parent-page-id via command line or update config.py"
        )
        sys.exit(1)

    try:
        jira_client = Jira(
            url=config.JIRA_URL,
            token=config.JIRA_API_TOKEN,
            cloud=False,
            verify_ssl=False,
        )
        confluence_client = Confluence(
            url=config.CONFLUENCE_URL,
            token=config.CONFLUENCE_API_TOKEN,
            cloud=False,
            verify_ssl=False,
        )

        safe_jira_api = SafeJiraApi(jira_client)
        safe_confluence_api = SafeConfluenceApi(confluence_client)

        jira_service = JiraService(safe_jira_api)
        confluence_service = ConfluenceService(safe_confluence_api)
        issue_finder_service = IssueFinderService(safe_confluence_api, safe_jira_api)

        generator = ConfluenceTreeGenerator(
            confluence_service=confluence_service,
            jira_service=jira_service,
            issue_finder_service=issue_finder_service,
            base_parent_page_id=args.base_parent_page_id,
            confluence_space_key=args.confluence_space_key,
            assignee_username=args.assignee_username,
            test_work_package_keys=args.test_work_package_keys,
            max_depth=args.max_depth,
            tasks_per_page=args.tasks_per_page,
        )

        generated_page_info = generator.generate_page_hierarchy(
            parent_page_id=args.base_parent_page_id
        )

        if generated_page_info:
            output_filename = config.generate_timestamped_filename(
                "generate_page_result", suffix=".json"
            )
            output_path = config.get_output_path("generate", output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(generated_page_info, f, ensure_ascii=False, indent=4)
            logger.info(f"Generated page info saved to: {output_path}")
        else:
            logger.info("No pages were generated.")

    except Exception as e:
        logger.error(f"An error occurred during generation: {e}", exc_info=True)
        sys.exit(1)

    finally:
        # Removed the call to generator.cleanup_generated_pages()
        pass  # The finally block now just passes if cleanup is not needed
        logging.info("--- Confluence Test Data Generation Script Finished ---")
