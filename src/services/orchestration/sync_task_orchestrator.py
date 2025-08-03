# File: src/services/orchestration/sync_task_orchestrator.py

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config import config
from src.exceptions import ConfluenceApiError, InvalidInputError, JiraApiError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import (
    ConfluencePageUpdateResult,
    JiraTaskCreationResult,
    SingleTaskResult,
    SyncTaskContext,
    SyncTaskResponse,
)
from src.models.data_models import ConfluenceTask

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
    ):
        """
        Initializes the SyncTaskOrchestrator with dependency-injected services.
        """
        self.confluence_service = confluence_service
        self.jira_service = jira_service
        self.issue_finder_service = issue_finder_service
        self.request_user: Optional[str] = None

    async def run(
        self,
        json_input: Dict[str, Any],
        context: SyncTaskContext,
        request_id: str,
    ) -> SyncTaskResponse:
        """
        The main entry point for executing the automation workflow asynchronously.
        Returns a SyncTaskResponse object containing overall statuses and detailed
        results for both Jira task creation and Confluence page updates.
        """
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        if not json_input or not json_input.get("confluence_page_urls"):
            raise InvalidInputError("No 'confluence_page_urls' provided.")

        page_urls = json_input["confluence_page_urls"]
        hierarchy_tasks = [
            self.process_page_hierarchy(url, context) for url in page_urls
        ]
        results = await asyncio.gather(*hierarchy_tasks, return_exceptions=True)

        all_jira_results: List[JiraTaskCreationResult] = []
        all_confluence_results: List[ConfluencePageUpdateResult] = []

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Error processing page hierarchy: {res}", exc_info=res)
                continue
            all_jira_results.extend(res[0])
            all_confluence_results.extend(res[1])

        jira_status = self._determine_overall_status(
            all_jira_results, lambda r: r.success
        )
        confluence_status = self._determine_overall_status(
            all_confluence_results, lambda r: r.updated
        )

        overall_status = self._get_final_status(jira_status, confluence_status)

        logging.info("\n--- Script Finished ---")
        return SyncTaskResponse(
            request_id=request_id,
            overall_status=overall_status,
            overall_jira_task_creation_status=jira_status,
            overall_confluence_page_update_status=confluence_status,
            jira_task_creation_results=all_jira_results,
            confluence_page_update_results=all_confluence_results,
        )

    async def process_page_hierarchy(
        self, root_page_url: str, context: SyncTaskContext
    ) -> Tuple[List[JiraTaskCreationResult], List[ConfluencePageUpdateResult]]:
        """
        Processes a root Confluence page and all of its descendants.
        """
        logging.info(f"\nProcessing hierarchy starting from: {root_page_url}")
        root_page_id = await self.confluence_service.get_page_id_from_url(root_page_url)
        if not root_page_id:
            logger.error(f"Could not find page ID for URL: {root_page_url}. Skipping.")
            return [], []

        all_page_ids = [
            root_page_id
        ] + await self.confluence_service.get_all_descendants(root_page_id)
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        all_tasks = await self._collect_tasks(all_page_ids)
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return [], []

        logging.info(f"Discovered {len(all_tasks)} incomplete tasks. Now processing...")
        return await self._process_tasks(all_tasks, context)

    async def _collect_tasks(self, page_ids: List[str]) -> List[ConfluenceTask]:
        """Collects all tasks from a list of Confluence page IDs concurrently."""
        page_detail_coroutines = [
            self.confluence_service.get_page_by_id(
                page_id, expand="body.storage,version"
            )
            for page_id in page_ids
        ]
        all_page_details = await asyncio.gather(*page_detail_coroutines)

        tasks: List[ConfluenceTask] = []
        for page_details in all_page_details:
            if page_details:
                tasks.extend(
                    await self.confluence_service.get_tasks_from_page(page_details)
                )
        return tasks

    async def _process_tasks(
        self, tasks: List[ConfluenceTask], context: SyncTaskContext
    ) -> Tuple[List[JiraTaskCreationResult], List[ConfluencePageUpdateResult]]:
        """
        Processes tasks, creates Jira issues, and then updates Confluence pages.
        """
        processing_coroutines = [self._process_single_task(t, context) for t in tasks]
        internal_results = await asyncio.gather(*processing_coroutines)

        jira_results: List[JiraTaskCreationResult] = []
        tasks_to_update: Dict[str, List[Dict[str, Any]]] = {}

        for result in internal_results:
            jira_results.append(
                JiraTaskCreationResult(
                    confluence_page_id=result.task_data.confluence_page_id,
                    confluence_task_id=result.task_data.confluence_task_id,
                    task_summary=result.task_data.task_summary,
                    original_page_version=result.task_data.original_page_version,
                    request_user=result.request_user,
                    new_jira_task_key=result.new_jira_task_key,
                    creation_status_text=result.status_text,
                    success=result.status_text.startswith("Success"),
                    error_message=(
                        result.status_text
                        if not result.status_text.startswith("Success")
                        else None
                    ),
                )
            )
            if result.status_text.startswith("Success") and result.new_jira_task_key:
                tasks_to_update.setdefault(
                    result.task_data.confluence_page_id, []
                ).append(
                    {
                        "confluence_task_id": result.task_data.confluence_task_id,
                        "jira_key": result.new_jira_task_key,
                    }
                )

        if tasks_to_update:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            update_coroutines = [
                self._update_confluence_page(pid, mappings)
                for pid, mappings in tasks_to_update.items()
            ]
            confluence_results = await asyncio.gather(*update_coroutines)
        else:
            logging.info("No successful Jira tasks, skipping Confluence updates.")
            confluence_results = []

        return jira_results, confluence_results

    async def _update_confluence_page(
        self, page_id: str, mappings: List[Dict[str, Any]]
    ) -> ConfluencePageUpdateResult:
        """Updates a single Confluence page and returns its result."""
        page_title = "N/A"
        try:
            page_details = await self.confluence_service.get_page_by_id(page_id)
            if not page_details:
                raise ConfluenceApiError(f"Could not find page {page_id} for update.")
            page_title = page_details.get("title", page_title)

            success = await self.confluence_service.update_page_with_jira_links(
                page_id, mappings
            )
            if success:
                return ConfluencePageUpdateResult(
                    page_id=page_id,
                    page_title=page_title,
                    updated=True,
                    jira_keys_replaced=[m["jira_key"] for m in mappings],
                )
            else:
                raise ConfluenceApiError(f"Update failed for page '{page_title}'.")
        except Exception as e:
            logger.error(
                f"Failed to update Confluence page {page_id}: {e}", exc_info=True
            )
            return ConfluencePageUpdateResult(
                page_id=page_id,
                page_title=page_title,
                updated=False,
                error_message=str(e),
            )

    async def _process_single_task(
        self, task: ConfluenceTask, context: SyncTaskContext
    ) -> SingleTaskResult:
        """Processes a single Confluence task into a Jira issue."""
        logging.info(
            f"\nProcessing task: '{task.task_summary}' from page ID: "
            f"{task.confluence_page_id}"
        )

        if not task.task_summary or not task.task_summary.strip():
            logger.warning(
                "Skipping empty task on page ID: %s.", task.confluence_page_id
            )
            return SingleTaskResult(
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
                f"Skipped task '{task.task_summary}' on page ID: "
                f"{task.confluence_page_id} - No Work Package found."
            )
            logger.error(f"ERROR: {error_msg}")
            return SingleTaskResult(
                task_data=task,
                status_text="Failed - No Work Package found",
                request_user=context.request_user,
            )

        closest_wp_key = closest_wp.get("key")
        if not closest_wp_key:
            logger.error(f"CRITICAL ERROR: WP missing 'key': {closest_wp}")
            return SingleTaskResult(
                task_data=task,
                status_text="Failed - Work Package key missing",
                request_user=context.request_user,
            )

        assignee_from_wp = None
        fields = closest_wp.get("fields")
        if isinstance(fields, dict):
            assignee_data = fields.get("assignee")
            if isinstance(assignee_data, dict):
                assignee_from_wp = assignee_data.get("name")

        if not task.assignee_name:
            if assignee_from_wp:
                task.assignee_name = assignee_from_wp
                logger.info(f"Assigning task from parent WP: {task.assignee_name}")
            else:
                logger.info("Task has no assignee in Confluence or parent WP.")
        else:
            logger.info(f"Assigning task from Confluence: {task.assignee_name}")

        new_issue_key = None
        status_text = "Failed - Jira task creation"
        try:
            new_issue_key = await self.jira_service.create_issue(
                task, closest_wp_key, context
            )

            if new_issue_key:
                status_text = "Success"
                if task.status == "complete":
                    target = config.JIRA_TARGET_STATUSES["completed_task"]
                    if await self.jira_service.transition_issue(new_issue_key, target):
                        status_text = "Success - Completed Task Created"
                    else:
                        status_text = "Success - Task Created (Transition Failed)"
                elif config.DEV_ENVIRONMENT:
                    target = config.JIRA_TARGET_STATUSES["new_task_dev"]
                    if not await self.jira_service.transition_issue(
                        new_issue_key, target
                    ):
                        status_text = "Success - Task Created (Dev Transition Failed)"

                if assignee_from_wp is None and task.assignee_name is None:
                    if not await self.jira_service.assign_issue(new_issue_key, None):
                        logger.warning(
                            f"Failed to explicitly unassign issue {new_issue_key}."
                        )
            else:
                logger.error(f"Jira API returned no key for task '{task.task_summary}'")
                status_text = "Failed - Jira API (No Key)"

        except JiraApiError as e:
            logger.error(
                f"Jira API error for '{task.task_summary}': {e}", exc_info=True
            )
            status_text = f"Failed - JiraApiError: {str(e)}"

        return SingleTaskResult(
            task_data=task,
            status_text=status_text,
            new_jira_task_key=new_issue_key,
            linked_work_package=closest_wp_key,
            request_user=context.request_user,
        )

    def _get_final_status(self, jira_status: str, confluence_status: str) -> str:
        """Determine the single overall status from the two sub-statuses."""
        is_jira_ok = "Success" in jira_status or "Skipped" in jira_status
        is_conf_ok = "Success" in confluence_status or "Skipped" in confluence_status

        if is_jira_ok and is_conf_ok:
            return "Success"
        if "Failed" in jira_status and "Failed" in confluence_status:
            return "Failed"
        return "Partial Success"

    def _determine_overall_status(
        self, results: List[Any], success_check: Callable[[Any], bool]
    ) -> str:
        """Determines the overall status from a list of result objects."""
        if not results:
            return "Skipped - No actions processed"

        all_successful = all(success_check(r) for r in results)
        any_successful = any(success_check(r) for r in results)

        if all_successful:
            return "Success"
        elif any_successful:
            return "Partial Success"
        else:
            return "Failed"
