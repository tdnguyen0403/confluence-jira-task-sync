import logging
from typing import Any, Dict, List, Optional

# Removed requests import as it's no longer directly used
# from src.config import config # Already imported in services
from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)
from src.models.data_models import AutomationResult, ConfluenceTask, SyncContext
from src.exceptions import (
    SyncError,
    InvalidInputError,
)  # Added MissingRequiredDataError

# Removed warnings filter as it's related to synchronous requests
# warnings.filterwarnings(
#     "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
# )

logger = logging.getLogger(__name__)


class SyncTaskOrchestrator:
    """
    Orchestrates the automation by coordinating service layer interactions.
    """

    def __init__(
        self,
        confluence_service: ConfluenceApiServiceInterface,
        jira_service: JiraApiServiceInterface,
        issue_finder_service: IssueFinderServiceInterface,  # Renamed from issue_finder to issue_finder_service for consistency
        confluence_issue_updater_service: Any,  # Type hint for ConfluenceIssueUpdaterService, to avoid circular import
    ):
        """
        Initializes the SyncTaskOrchestrator with dependency-injected services.

        Args:
            confluence_service (ConfluenceApiServiceInterface): A service for handling
                Confluence operations.
            jira_service (JiraApiServiceInterface): A service for handling Jira
                operations.
            issue_finder_service (IssueFinderServiceInterface): A service for finding specific
                Jira issues on Confluence pages.
            confluence_issue_updater_service (Any): A service for updating Confluence issues.
        """
        self.confluence_service = confluence_service
        self.jira_service = jira_service
        self.issue_finder_service = issue_finder_service
        self.confluence_issue_updater_service = (
            confluence_issue_updater_service  # Added this
        )
        self.results: List[AutomationResult] = []  # Initialize results
        self.request_user: Optional[str] = None  # Initialize request_user

    async def run(self, json_input: Dict[str, Any], context: SyncContext) -> None:
        """
        The main entry point for executing the automation workflow asynchronously.

        Args:
            json_input (Dict[str, Any]): A JSON object containing
                'confluence_page_urls' (list of URLs) and 'context' (SyncContext object).
            context (SyncContext): Contextual information for the sync operation.
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

        # Iterate and process each page hierarchy asynchronously
        for url in page_urls:
            await self.process_page_hierarchy(url, context)  # Await this call

        logging.info("\n--- Script Finished ---")

    async def process_page_hierarchy(
        self, root_page_url: str, context: SyncContext
    ) -> None:
        """
        Processes a root Confluence page and all of its descendants asynchronously.

        Args:
            root_page_url (str): The URL of the top-level page to start from.
            context (SyncContext): Contextual information for the sync operation.
        Raises:
            SyncError: If the root page ID cannot be found.
        """
        logging.info(f"\nProcessing hierarchy starting from: {root_page_url}")
        root_page_id = await self.confluence_service.get_page_id_from_url(
            root_page_url
        )  # Await service call
        if not root_page_id:
            logger.error(f"Could not find page ID for URL: {root_page_url}. Skipping.")
            raise SyncError(
                f"Could not find Confluence page ID for URL: {root_page_url}."
            )

        all_page_ids = [
            root_page_id
        ] + await self.confluence_service.get_all_descendants(  # Await service call
            root_page_id
        )
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        all_tasks = await self._collect_tasks(all_page_ids)  # Await this call
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return

        logging.info(
            f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing..."
        )
        await self._process_tasks(all_tasks, context)  # Await this call

    async def _collect_tasks(self, page_ids: List[str]) -> List[ConfluenceTask]:
        """Collects all tasks from a list of Confluence page IDs asynchronously."""
        tasks: List[ConfluenceTask] = []
        for page_id in page_ids:
            page_details = (
                await self.confluence_service.get_page_by_id(  # Await service call
                    page_id, expand="body.storage,version"
                )
            )
            if page_details:
                tasks.extend(
                    await self.confluence_service.get_tasks_from_page(page_details)
                )  # Await service call
        return tasks

    async def _process_tasks(
        self, tasks: List[ConfluenceTask], context: SyncContext
    ) -> None:
        """
        Processes a list of tasks, creates Jira issues, and tracks results asynchronously.
        Raises:
            MissingRequiredDataError: If a Work Package cannot be found for a task.
            SyncError: If Jira task creation fails.
        """
        tasks_to_update_on_pages: Dict[str, List] = {}
        self.request_user = context.request_user  # Set request_user from context

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
            # Pass confluence_service to find_issue_on_page
            closest_wp = await self.issue_finder_service.find_issue_on_page(  # Await service call
                task.confluence_page_id,
                config.PARENT_ISSUES_TYPE_ID,
                self.confluence_service,
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
                        status_text="Skipped - No Work Package found",
                        request_user=context.request_user,
                    )
                )
                continue

            closest_wp_key = closest_wp["key"]

            if task.assignee_name:
                logger.info(
                    f"Assigning task from Confluence task: {task.assignee_name}"
                )
            elif closest_wp and closest_wp.get("fields", {}).get("assignee", {}).get(
                "name"
            ):
                task.assignee_name = closest_wp["fields"]["assignee"]["name"]
                logger.info(
                    f"Assigning task from parent Work Package: {task.assignee_name}"
                )
            else:
                logger.info(
                    "No assignee found in Confluence task or parent Work Package. Leaving unassigned."
                )

            new_issue = await self.jira_service.create_issue(
                task, closest_wp_key, context
            )  # Await service call

            if new_issue:  # new_issue is now the key of the created issue, not a dict
                new_key = new_issue

                # Handle task status logic.
                if task.status == "complete":
                    target_status = config.JIRA_TARGET_STATUSES["completed_task"]
                    await self.jira_service.transition_issue(
                        new_key, target_status
                    )  # Await service call
                    self.results.append(
                        AutomationResult(
                            task_data=task,
                            status_text="Success - Completed Task Created",
                            new_jira_task_key=new_key,
                            linked_work_package=closest_wp_key,
                            request_user=context.request_user,
                        )
                    )
                else:
                    # For new, incomplete tasks in a development environment, transition to a specific status for new_tasks.
                    if config.DEV_ENVIRONMENT:
                        target_status = config.JIRA_TARGET_STATUSES["new_task_dev"]
                        await self.jira_service.transition_issue(
                            new_key, target_status
                        )  # Await service call
                    # If not in development, create the task in the default status.
                    self.results.append(
                        AutomationResult(
                            task_data=task,
                            status_text="Success",
                            new_jira_task_key=new_key,
                            linked_work_package=closest_wp_key,
                            request_user=context.request_user,
                        )
                    )

                # Group the successful mappings by page ID for batch updates.
                tasks_to_update_on_pages.setdefault(task.confluence_page_id, []).append(
                    {"confluence_task_id": task.confluence_task_id, "jira_key": new_key}
                )
            else:
                # --- Log error and continue, do NOT raise SyncError here ---
                error_msg = (
                    f"Failed to create Jira task for '{task.task_summary}' (ID: {task.confluence_task_id}) "
                    f"on page ID: {task.confluence_page_id} linked to WP: {closest_wp_key}. "
                    f"Skipping further processing for this task."
                )
                logger.error(f"ERROR: {error_msg}")
                self.results.append(
                    AutomationResult(
                        task_data=task,
                        status_text="Failed - Jira task creation",
                        linked_work_package=closest_wp_key,
                        request_user=self.request_user,
                        error_message=error_msg,
                    )
                )
                # Continue to the next task in the loop
                continue

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            for page_id, mappings in tasks_to_update_on_pages.items():
                await self.confluence_service.update_page_with_jira_links(
                    page_id, mappings
                )  # Await service call
