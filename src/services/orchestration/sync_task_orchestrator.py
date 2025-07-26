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
        results_for_this_process_call: List[AutomationResult] = []

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
                results_for_this_process_call.append(
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
                    "No assignee found in Confluence task or parent Work Package. "
                    "Leaving unassigned."
                )

            new_issue = await self.jira_service.create_issue(
                task, closest_wp_key, context
            )

            if new_issue:
                new_key = new_issue

                if task.status == "complete":
                    target_status = config.JIRA_TARGET_STATUSES["completed_task"]
                    await self.jira_service.transition_issue(new_key, target_status)
                    results_for_this_process_call.append(
                        AutomationResult(
                            task_data=task,
                            status_text="Success - Completed Task Created",
                            new_jira_task_key=new_key,
                            linked_work_package=closest_wp_key,
                            request_user=context.request_user,
                        )
                    )
                else:
                    if config.DEV_ENVIRONMENT:
                        target_status = config.JIRA_TARGET_STATUSES["new_task_dev"]
                        await self.jira_service.transition_issue(new_key, target_status)
                    results_for_this_process_call.append(
                        AutomationResult(
                            task_data=task,
                            status_text="Success",
                            new_jira_task_key=new_key,
                            linked_work_package=closest_wp_key,
                            request_user=context.request_user,
                        )
                    )

                tasks_to_update_on_pages.setdefault(task.confluence_page_id, []).append(
                    {"confluence_task_id": task.confluence_task_id, "jira_key": new_key}
                )
            else:
                error_msg = (
                    f"Failed to create Jira task for '{task.task_summary}' "
                    f"(ID: {task.confluence_task_id}) on page ID: "
                    f"{task.confluence_page_id} linked to WP: {closest_wp_key}. "
                    "Skipping further processing for this task."
                )
                logger.error(f"ERROR: {error_msg}")
                results_for_this_process_call.append(
                    AutomationResult(
                        task_data=task,
                        status_text="Failed - Jira task creation",
                        linked_work_package=closest_wp_key,
                        request_user=self.request_user,
                        error_message=error_msg,
                    )
                )
                continue

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            for page_id, mappings in tasks_to_update_on_pages.items():
                await self.confluence_service.update_page_with_jira_links(
                    page_id, mappings
                )

        return results_for_this_process_call
