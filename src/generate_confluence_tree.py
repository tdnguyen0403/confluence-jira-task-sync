"""
Provides a utility for generating a tree of test data in Confluence.

This module contains the `TestDataGenerator` class, which is designed to
create a hierarchical structure of Confluence pages populated with various
types of content, including Jira issue macros and task lists. This is
essential for creating a consistent and realistic test environment for the main
automation script.

The generator is configurable via the `config.py` file and can create a
multi-level page tree with a specified number of tasks per page, linked to
different work packages.

Usage:
    This script is intended to be run directly from the command line:
    `python -m your_module.test_data_generator`
"""

import logging
import uuid
import warnings
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from atlassian import Confluence, Jira

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.services.confluence_service import ConfluenceService
from src.utils.logging_config import setup_logging

# Suppress insecure request warnings for local/dev environments
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)


class ConfluenceTreeGenerator:
    """
    Generates a Confluence test page structure using a service interface.

    This class orchestrates the creation of a hierarchy of test pages,
    each containing a Jira macro for a work package and a configurable number
    of Confluence tasks.
    """

    def __init__(self, confluence_service: ConfluenceApiServiceInterface):
        """
        Initializes the TestDataGenerator.

        Args:
            confluence_service (ApiServiceInterface): An implementation of the
                API service interface, used to interact with Confluence.
        """
        self.confluence = confluence_service
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.all_created_pages: List[Dict[str, Any]] = []
        self.assignee_userkey: Optional[str] = None
        self.task_counter = 0

    def _initialize_assignee(self, username: Optional[str]) -> None:
        """
        Resolves the Confluence user key for the assignee username.

        This user key is required to correctly assign tasks in the generated
        Confluence pages. The result is cached for the duration of the run.

        Args:
            username (Optional[str]): The username of the assignee.
        """
        if not username:
            logging.warning("No assignee username provided; tasks will be unassigned.")
            return

        logging.info(f"Attempting to resolve userkey for username: '{username}'...")
        user_details = self.confluence.get_user_details_by_username(username=username)
        if user_details and "userKey" in user_details:
            self.assignee_userkey = user_details["userKey"]
            logging.info(f"Successfully resolved userkey '{self.assignee_userkey}'.")
        else:
            logging.error(f"Could not find userkey for username '{username}'.")

    def run(
        self, base_parent_id: str, wp_keys: List[str], max_depth: int,
        tasks_per_page: int
    ) -> None:
        """
        Main method to generate the entire test tree.

        Args:
            base_parent_id (str): The ID of the top-level Confluence page
                under which the test tree will be created.
            wp_keys (List[str]): A list of Jira Work Package keys to embed in
                the generated pages.
            max_depth (int): The maximum depth of the page hierarchy to create.
            tasks_per_page (int): The number of tasks to create on each page.
        """
        setup_logging("logs/logs_generator", "generator_confluence_tree_run")
        logging.info(
            f"\n--- Initiating Test Tree Generation under Parent ID: {base_parent_id} ---"
        )

        if not wp_keys:
            logging.error("ERROR: Must provide at least one Work Package key.")
            return

        self._initialize_assignee(config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS)

        # Create the root page of the test tree.
        main_page_id = self._create_page(
            parent_id=base_parent_id,
            title=f"Gen {self.timestamp} - Main Test Page Root",
            wp_key=wp_keys[0],
            tasks_per_page=tasks_per_page,
        )

        if not main_page_id:
            logging.error("Failed to create the main test page. Aborting.")
            return

        logging.info(
            f"\n--- Generating sub-levels under '{self.all_created_pages[0]['title']}' ---"
        )
        self._generate_tree_recursive(
            parent_id=main_page_id,
            wp_keys=wp_keys,
            current_depth=1,
            max_depth=max_depth,
            tasks_per_page=tasks_per_page,
            wp_index=1,
        )
        self._print_summary()

    def _generate_tree_recursive(
        self,
        parent_id: str,
        wp_keys: List[str],
        current_depth: int,
        max_depth: int,
        tasks_per_page: int,
        wp_index: int,
    ) -> None:
        """
        Recursively generates pages under a given parent to build a tree.

        Args:
            parent_id (str): The ID of the parent page for this level.
            wp_keys (List[str]): The list of work package keys to cycle through.
            current_depth (int): The current depth in the hierarchy.
            max_depth (int): The maximum depth to generate.
            tasks_per_page (int): The number of tasks per page.
            wp_index (int): The current index for selecting a work package key.
        """
        if current_depth > max_depth:
            return

        page_title = f"Gen {self.timestamp} - L{current_depth}"
        # Cycle through the provided work package keys.
        current_wp_key = wp_keys[wp_index % len(wp_keys)]

        new_page_id = self._create_page(
            parent_id=parent_id,
            title=page_title,
            wp_key=current_wp_key,
            tasks_per_page=tasks_per_page,
        )

        if new_page_id:
            # Recursive call for the next level down.
            self._generate_tree_recursive(
                parent_id=new_page_id,
                wp_keys=wp_keys,
                current_depth=current_depth + 1,
                max_depth=max_depth,
                tasks_per_page=tasks_per_page,
                wp_index=wp_index + 1,
            )

    def _create_page(
        self, parent_id: str, title: str, wp_key: str, tasks_per_page: int
    ) -> Optional[str]:
        """Creates a single Confluence page with specified content."""
        tasks = [
            self._generate_task_html(f"Task {i + 1} on page {title}")
            for i in range(tasks_per_page)
        ]
        content_html = self._create_page_body(
            title=title,
            description=f"This page contains Work Package: {wp_key}.",
            main_content_html=self._wrap_in_task_list(tasks),
            jira_macro_html=self._generate_jira_macro_html(wp_key),
        )

        page = self.confluence.create_page(
            space=config.CONFLUENCE_SPACE_KEY,
            parent_id=parent_id,
            title=title,
            body=content_html,
            representation="storage",
        )

        if page and page.get("id"):
            logging.info(
                f"Created page \"{config.CONFLUENCE_SPACE_KEY}\" -> \"{title}\""
            )
            self.all_created_pages.append(
                {
                    "id": page["id"],
                    "url": page.get("_links", {}).get("webui"),
                    "title": title,
                    "wp_on_page": wp_key,
                }
            )
            return page["id"]
        return None

    def _print_summary(self) -> None:
        """Prints a final summary of all created pages to the console."""
        logging.info("\n--- Final Confluence Test Tree Generation Summary ---")
        logging.info(f"Total {len(self.all_created_pages)} pages generated.")
        for page in self.all_created_pages:
            wp_status = (
                f"(WP: {page['wp_on_page']})" if page.get("wp_on_page") else "(No WP)"
            )
            url = page.get("url", "URL not available")
            logging.info(f"- {page['title']} {wp_status}: {url}")

        if self.all_created_pages:
            main_url = self.all_created_pages[0].get("url", "N/A")
            logging.info(
                f"\nTo test, add the Main Test Page URL to input file: {main_url}"
            )

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        """Generates the Confluence storage format for a Jira macro."""
        macro_id = str(uuid.uuid4())
        return (
            f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" '
            f'ac:macro-id="{macro_id}">'
            f'<ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>'
            f'<ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>'
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f"</ac:structured-macro></p>"
        )

    def _generate_task_html(
        self,
        summary: str,
        status: str = "incomplete",
        due_date: Optional[date] = None,
    ) -> str:
        """Generates the Confluence storage format for a single task item."""
        self.task_counter += 1
        assignee_html = (
            f'<ri:user ri:userkey="{self.assignee_userkey}"/>'
            if self.assignee_userkey
            else ""
        )
        date_html = f'<time datetime="{due_date.strftime("%Y-%m-%d")}"/>' if due_date else ""
        task_id = f"task-{uuid.uuid4().hex[:4]}-{self.task_counter}"
        return (
            f"<ac:task><ac:task-id>{task_id}</ac:task-id>"
            f"<ac:task-status>{status}</ac:task-status>"
            f"<ac:task-body><span>{summary} {assignee_html}{date_html}</span></ac:task-body></ac:task>"
        )

    def _wrap_in_task_list(self, tasks: List[str]) -> str:
        """Wraps a list of task HTML strings in a task list container."""
        return f"<ac:task-list>{''.join(tasks)}</ac:task-list>"

    def _create_page_body(self, **kwargs: Any) -> str:
        """Constructs the full HTML body for a Confluence page."""
        return (
            f"<h1>{kwargs['title']}</h1>"
            f"<p>{kwargs['description']}</p>"
            f"{kwargs.get('jira_macro_html', '')}"
            f"{kwargs.get('main_content_html', '')}"
        )


if __name__ == "__main__":
    if config.BASE_PARENT_CONFLUENCE_PAGE_ID == "YOUR_BASE_PARENT_PAGE_ID_HERE":
        logging.error("Please update BASE_PARENT_CONFLUENCE_PAGE_ID in config.py")
    else:
        # Use new config variables for customization.
        wp_keys_to_use = config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE[
            : config.DEFAULT_NUM_WORK_PACKAGES
        ]

        # 1. Initialize raw API clients.
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

        # 2. Instantiate the low-level, resilient API handlers.
        safe_jira_api = SafeJiraApi(jira_client)
        safe_confluence_api = SafeConfluenceApi(confluence_client)

        # 3. Instantiate the high-level service implementation.
        confluence_service = ConfluenceService(safe_confluence_api)

        # 4. Inject the service into the generator and run it.
        generator = TestDataGenerator(confluence_service)
        generator.run(
            base_parent_id=config.BASE_PARENT_CONFLUENCE_PAGE_ID,
            wp_keys=wp_keys_to_use,
            max_depth=config.DEFAULT_MAX_DEPTH,
            tasks_per_page=config.DEFAULT_TASKS_PER_PAGE,
        )
