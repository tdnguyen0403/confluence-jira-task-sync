import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.config import config
from src.exceptions import (
    InvalidInputError,
    SyncError,
)
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import AutomationResult, ConfluenceTask, SyncContext

logger = logging.getLogger(__name__)


class SyncTaskOrchestrator:
    """
    Orchestrates the automation by coordinating service layer interactions.
    """

    def __init__(
        self,
        confluence_service: ConfluenceApiServiceInterface,
        jira_service: JiraApiServiceInterface,
        issue_finder_service: IssueFinderServiceInterface,
        confluence_issue_updater_service: Any,
    ):
        """
        Initializes the SyncTaskOrchestrator with dependency-injected services.

        Args:
            confluence_service (ConfluenceApiServiceInterface): A service for
                handling Confluence operations.
            jira_service (JiraApiServiceInterface): A service for handling Jira
                operations.
            issue_finder_service (IssueFinderServiceInterface): A service for
                finding specific Jira issues on Confluence pages.
            confluence_issue_updater_service (Any): A service for updating
                Confluence issues.
        """
        self.confluence_service = confluence_service
        self.jira_service = jira_service
        self.issue_finder_service = issue_finder_service
        self.confluence_issue_updater_service = confluence_issue_updater_service
        self.request_user: Optional[str] = None

    async def run(self, json_input: Dict[str, Any], context: SyncContext) -> None:
        """
        The main entry point for executing the automation workflow asynchronously.

        Args:
            json_input (Dict[str, Any]): A JSON object containing
                'confluence_page_urls' (list of URLs) and 'context'
                (SyncContext object).
            context (SyncContext): Contextual information for the sync operation.
        Raises:
            InvalidInputError: If required input data is missing or malformed.
            SyncError: For general errors during the synchronization process.
        """
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        self.results = []
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

        current_run_results: List[AutomationResult] = []

        for url in page_urls:
            current_run_results = await self.process_page_hierarchy(url, context)

        return current_run_results
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
        root_page_id = await self.confluence_service.get_page_id_from_url(root_page_url)
        if not root_page_id:
            logger.error(f"Could not find page ID for URL: {root_page_url}. Skipping.")
            raise SyncError(
                f"Could not find Confluence page ID for URL: {root_page_url}."
            )

        all_page_ids = [
            root_page_id
        ] + await self.confluence_service.get_all_descendants(root_page_id)
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        all_tasks = await self._collect_tasks(all_page_ids)
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return []

        logging.info(
            f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing..."
        )
        return await self._process_tasks(all_tasks, context)

    async def _collect_tasks(self, page_ids: List[str]) -> List[ConfluenceTask]:
        """Collects all tasks from a list of Confluence page IDs asynchronously."""
        tasks: List[ConfluenceTask] = []
        for page_id in page_ids:
            page_details = await self.confluence_service.get_page_by_id(
                page_id, expand="body.storage,version"
            )
            if page_details:
                tasks.extend(
                    await self.confluence_service.get_tasks_from_page(page_details)
                )
        return tasks

    async def _process_tasks(
        self, tasks: List[ConfluenceTask], context: SyncContext
    ) -> None:
        """
        Processes a list of tasks, creates Jira issues, and tracks results.

        Raises:
            MissingRequiredDataError: If a Work Package cannot be found for a task.
            SyncError: If Jira task creation fails.
        """
        tasks_to_update_on_pages: Dict[str, List] = {}

        processing_coroutines = [
            self._process_single_task(task, context) for task in tasks
        ]
        results_for_this_process_call = await asyncio.gather(*processing_coroutines)

        for result in results_for_this_process_call:
            if result.status_text.startswith("Success") and result.new_jira_task_key:
                task = result.task_data
                tasks_to_update_on_pages.setdefault(task.confluence_page_id, []).append(
                    {
                        "confluence_task_id": task.confluence_task_id,
                        "jira_key": result.new_jira_task_key,
                    }
                )

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            update_coroutines = [
                self.confluence_service.update_page_with_jira_links(page_id, mappings)
                for page_id, mappings in tasks_to_update_on_pages.items()
            ]
            await asyncio.gather(*update_coroutines)

        return results_for_this_process_call

    async def _process_single_task(
        self, task: ConfluenceTask, context: SyncContext
    ) -> AutomationResult:
        """Helper method to process a single Confluence task."""
        logging.info(
            f"\nProcessing task: '{task.task_summary}' from page ID: "
            f"{task.confluence_page_id}"
        )

        if not task.task_summary or not task.task_summary.strip():
            logger.warning(
                "Skipping empty task on page ID: %s.", task.confluence_page_id
            )
            return AutomationResult(
                task_data=task,
                status_text="Skipped - Empty Task",
                request_user=context.request_user,
            )

        closest_wp = await self.issue_finder_service.find_issue_on_page(
            task.confluence_page_id,
            config.PARENT_ISSUES_TYPE_ID,
            self.confluence_service,
        )

        if not closest_wp:
            error_msg = (
                f"Skipped task '{task.task_summary}' "
                f"(ID: {task.confluence_task_id}) "
                f"on page ID: {task.confluence_page_id} - No Work Package found."
            )
            logger.error(f"ERROR: {error_msg}")
            return AutomationResult(
                task_data=task,
                status_text="Skipped - No Work Package found",
                request_user=context.request_user,
            )

        closest_wp_key = closest_wp["key"]
        # TODO: fix the logic below because if there is unassigned
        # assignee for Work Package in JIRA it will failed !!

        if not isinstance(closest_wp, dict):
            error_msg = (
                f"Closest Work Package (ID: {task.confluence_page_id}) "
                f"is not a dictionary. Type: {type(closest_wp)}. Data: {closest_wp}"
            )
            logger.error(f"CRITICAL ERROR: {error_msg}")
            return AutomationResult(
                task_data=task,
                status_text="Failed - Malformed Work Package data",
                request_user=context.request_user,
            )

        # This line should now be safe as closest_wp is guaranteed to be a dict
        closest_wp_key = closest_wp.get("key")
        if not closest_wp_key:
            error_msg = (
                f"Closest Work Package (ID: {task.confluence_page_id}) "
                f"is missing 'key' field. Data: {closest_wp}"
            )
            logger.error(f"CRITICAL ERROR: {error_msg}")
            return AutomationResult(
                task_data=task,
                status_text="Failed - Work Package key missing",
                request_user=context.request_user,
            )

        # Safely determine the assignee:
        if (
            not task.assignee_name
        ):  # Only try to assign if the Confluence task doesn't already have an assignee
            assignee_from_wp = None

            # Get 'fields' safely
            fields = closest_wp.get("fields")
            if isinstance(fields, dict):
                # Get 'assignee' safely from 'fields'
                assignee_data = fields.get("assignee")
                if isinstance(assignee_data, dict):
                    assignee_from_wp = assignee_data.get("name")
                else:
                    logger.info(
                        f"Assignee is not a dictionary for task '{task.task_summary}'. "
                        f"Actual type: {type(assignee_data)}. Data: {assignee_data}"
                    )
            else:
                logger.info(
                    f"Fields data is not a dictionary for task '{task.task_summary}'. "
                    f"Actual type: {type(fields)}. Data: {fields}"
                )

            if assignee_from_wp:
                task.assignee_name = assignee_from_wp
                logger.info(
                    f"Assigning task from parent Work Package: {task.assignee_name}"
                )
            else:
                task.assignee_name = None
                logger.info(
                    "No assignee found in Confluence task or parent Work Package. "
                    "Leaving unassigned."
                )
        else:
            logger.info(f"Assigning task from Confluence task: {task.assignee_name}")

        new_issue = await self.jira_service.create_issue(task, closest_wp_key, context)

        if new_issue:
            new_key = new_issue
            status_text = "Success"

            if task.status == "complete":
                target_status = config.JIRA_TARGET_STATUSES["completed_task"]
                await self.jira_service.transition_issue(new_key, target_status)
                status_text = "Success - Completed Task Created"
            elif config.DEV_ENVIRONMENT:
                target_status = config.JIRA_TARGET_STATUSES["new_task_dev"]
                await self.jira_service.transition_issue(new_key, target_status)

            return AutomationResult(
                task_data=task,
                status_text=status_text,
                new_jira_task_key=new_key,
                linked_work_package=closest_wp_key,
                request_user=context.request_user,
            )
        else:
            error_msg = (
                f"Failed to create Jira task for '{task.task_summary}' "
                f"(ID: {task.confluence_task_id}) on page ID: "
                f"{task.confluence_page_id} linked to WP: {closest_wp_key}. "
                "Skipping further processing for this task."
            )
            logger.error(f"ERROR: {error_msg}")
            return AutomationResult(
                task_data=task,
                status_text="Failed - Jira task creation",
                linked_work_package=closest_wp_key,
                request_user=context.request_user,
            )
