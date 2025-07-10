import logging
import warnings
from typing import Any, Dict, List, Optional

import requests

from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)  # New import
from src.models.data_models import AutomationResult, ConfluenceTask
from src.exceptions import SyncError, InvalidInputError

warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)

logger = logging.getLogger(__name__)


class SyncTaskOrchestrator:
    """
    Orchestrates the automation by coordinating service layer interactions.
    """

    def __init__(
        self,
        confluence_service: ConfluenceApiServiceInterface,
        jira_service: JiraApiServiceInterface,
        issue_finder: IssueFinderServiceInterface,  # Changed to interface
    ):
        """
        Initializes the SyncTaskOrchestrator with dependency-injected services.

        Args:
            confluence_service (ConfluenceApiServiceInterface): A service for handling
                Confluence operations.
            jira_service (JiraApiServiceInterface): A service for handling Jira
                operations.
            issue_finder (IssueFinderServiceInterface): A service for finding specific
                Jira issues on Confluence pages.
        """
        self.confluence = confluence_service
        self.jira = jira_service
        self.issue_finder = issue_finder
        self.results: List[AutomationResult] = []
        self.request_user: Optional[str] = None

    def run(self, json_input: Dict[str, Any]) -> None:
        """
        The main entry point for executing the automation workflow.

        Args:
            json_input (Dict[str, Any]): A JSON object containing
                'confluence_page_urls' (list of URLs) and 'request_user' (string).
        Raises:
            InvalidInputError: If required input data is missing or malformed.
            SyncError: For general errors during the synchronization process.
        """
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        if not json_input:
            logger.error("ERROR: No input JSON provided. Aborting.")
            raise InvalidInputError("No input JSON provided for sync operation.")

        page_urls = json_input.get("confluence_page_urls", [])
        if not page_urls:
            logger.error(
                "ERROR: No 'confluence_page_urls' found in the input. Aborting."
            )
            raise InvalidInputError(
                "No 'confluence_page_urls' found in the input for sync operation."
            )

        self.request_user = json_input.get("request_user")
        if not self.request_user:
            logger.warning(
                "No 'request_user' found in the input. Results will not include who requested the sync."
            )

        logging.info(f"Processing input for: {self.request_user or 'Unknown User'}")

        for url in page_urls:
            self.process_page_hierarchy(url)

        logging.info("\n--- Script Finished ---")

    def process_page_hierarchy(self, root_page_url: str) -> None:
        """
        Processes a root Confluence page and all of its descendants.

        Args:
            root_page_url (str): The URL of the top-level page to start from.
        Raises:
            SyncError: If the root page ID cannot be found.
        """
        logging.info(f"\nProcessing hierarchy starting from: {root_page_url}")
        root_page_id = self.confluence.get_page_id_from_url(root_page_url)
        if not root_page_id:
            logger.error(f"Could not find page ID for URL: {root_page_url}. Skipping.")
            raise SyncError(
                f"Could not find Confluence page ID for URL: {root_page_url}."
            )

        all_page_ids = [root_page_id] + self.confluence.get_all_descendants(
            root_page_id
        )
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        all_tasks = self._collect_tasks(all_page_ids)
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return

        logging.info(
            f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing..."
        )
        self._process_tasks(all_tasks)

    def _collect_tasks(self, page_ids: List[str]) -> List[ConfluenceTask]:
        """Collects all tasks from a list of Confluence page IDs."""
        tasks: List[ConfluenceTask] = []
        for page_id in page_ids:
            page_details = self.confluence.get_page_by_id(
                page_id, expand="body.storage,version"
            )
            if page_details:
                tasks.extend(self.confluence.get_tasks_from_page(page_details))
        return tasks

    def _process_tasks(self, tasks: List[ConfluenceTask]) -> None:
        """
        Processes a list of tasks, creates Jira issues, and tracks results.
        Raises:
            MissingRequiredDataError: If a Work Package cannot be found for a task.
            SyncError: If Jira task creation fails.
        """
        tasks_to_update_on_pages: Dict[str, List] = {}

        for task in tasks:
            logging.info(
                f"\nProcessing task: '{task.task_summary}' from page ID: "
                f"{task.confluence_page_id}"
            )

            if not task.task_summary or not task.task_summary.strip():
                logger.warning(
                    "Skipping empty task on page ID: %s.", task.confluence_page_id
                )
                continue

            # Find the parent Work Package on the same page as the task.
            closest_wp = self.issue_finder.find_issue_on_page(
                task.confluence_page_id, config.PARENT_ISSUES_TYPE_ID
            )

            if not closest_wp:
                error_msg = (
                    f"Skipped task '{task.task_summary}' (ID: {task.confluence_task_id}) "
                    f"on page ID: {task.confluence_page_id} - No Work Package found."
                )
                logger.error(f"ERROR: {error_msg}")
                self.results.append(
                    AutomationResult(
                        task_data=task,
                        status="Skipped - No Work Package found",
                        request_user=self.request_user,
                    )
                )
                continue

            closest_wp_key = closest_wp["key"]

            new_issue = self.jira.create_issue(task, closest_wp_key, self.request_user)

            if new_issue and new_issue.get("key"):
                new_key = new_issue["key"]

                # Handle task status logic.
                if task.status == "complete":
                    target_status = config.JIRA_TARGET_STATUSES["completed_task"]
                    self.jira.transition_issue(new_key, target_status)
                    self.results.append(
                        AutomationResult(
                            task_data=task,
                            status="Success - Completed Task Created",
                            new_jira_key=new_key,
                            linked_work_package=closest_wp_key,
                            request_user=self.request_user,
                        )
                    )
                else:
                    # For new, incomplete tasks in a non-production environment.
                    if not config.PRODUCTION_MODE:
                        target_status = config.JIRA_TARGET_STATUSES["new_task_dev"]
                        self.jira.transition_issue(new_key, target_status)
                    self.results.append(
                        AutomationResult(
                            task_data=task,
                            status="Success",
                            new_jira_key=new_key,
                            linked_work_package=closest_wp_key,
                            request_user=self.request_user,
                        )
                    )

                # Group the successful mappings by page ID for batch updates.
                tasks_to_update_on_pages.setdefault(task.confluence_page_id, []).append(
                    {"confluence_task_id": task.confluence_task_id, "jira_key": new_key}
                )
            else:
                error_msg = (
                    f"Failed to create Jira task for '{task.task_summary}' (ID: {task.confluence_task_id}) "
                    f"on page ID: {task.confluence_page_id} linked to WP: {closest_wp_key}."
                )
                logger.error(f"ERROR: {error_msg}")
                self.results.append(
                    AutomationResult(
                        task_data=task,
                        status="Failed - Jira task creation",
                        linked_work_package=closest_wp_key,
                        request_user=self.request_user,
                    )
                )
                raise SyncError(error_msg)

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            for page_id, mappings in tasks_to_update_on_pages.items():
                self.confluence.update_page_with_jira_links(page_id, mappings)
