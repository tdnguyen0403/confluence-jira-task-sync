# File: src/services/orchestration/sync_task_orchestrator.py

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config import config
from src.exceptions import (
    ConfluenceApiError,
    InvalidInputError,
    JiraApiError,
)
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import (
    ConfluencePageUpdateResult,
    JiraTaskCreationResult,  # Import all necessary models
    SingleTaskResult,
    SyncTaskContext,
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
        self, json_input: Dict[str, Any], context: SyncTaskContext
    ) -> Dict[str, Any]:  # Changed return type to Dict for comprehensive response
        """
        The main entry point for executing the automation workflow asynchronously.
        Returns a dictionary containing overall statuses and detailed results
        for both Jira task creation and Confluence page updates.
        """
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        all_jira_creation_results: List[JiraTaskCreationResult] = []
        all_confluence_page_update_results: List[ConfluencePageUpdateResult] = []

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

        processing_hierarchy_tasks = [
            self.process_page_hierarchy(url, context) for url in page_urls
        ]
        results_from_hierarchies = await asyncio.gather(
            *processing_hierarchy_tasks, return_exceptions=True
        )  # noqa: E501

        for res_tuple in results_from_hierarchies:
            if isinstance(res_tuple, ConfluenceApiError):
                logger.error(
                    f"Error processing page hierarchy: {res_tuple}", exc_info=res_tuple
                )
                continue

            all_jira_creation_results.extend(res_tuple[0])
            all_confluence_page_update_results.extend(res_tuple[1])

        overall_jira_status = self._determine_overall_status(
            all_jira_creation_results, lambda r: r.success
        )
        overall_confluence_status = (
            self._determine_overall_status(
                all_confluence_page_update_results, lambda r: r.updated
            )
            if all_confluence_page_update_results
            else "Skipped - No updates needed"
        )

        logging.info("\n--- Script Finished ---")
        return {
            "overall_jira_task_creation_status": overall_jira_status,
            "overall_confluence_page_update_status": overall_confluence_status,
            "jira_task_creation_results": all_jira_creation_results,
            "confluence_page_update_results": all_confluence_page_update_results,
        }

    async def process_page_hierarchy(
        self, root_page_url: str, context: SyncTaskContext
    ) -> Tuple[List[JiraTaskCreationResult], List[ConfluencePageUpdateResult]]:
        """
        Processes a root Confluence page and all of its descendants asynchronously.
        Returns collected Jira task creation results and Confluence page update results.
        """
        logging.info(f"\nProcessing hierarchy starting from: {root_page_url}")
        root_page_id = await self.confluence_service.get_page_id_from_url(root_page_url)
        if not root_page_id:
            error_msg = f"Could not find page ID for URL: {root_page_url}. Skipping."
            logger.error(error_msg)
            return [], []  # Return empty lists for both result types

        all_page_ids = [
            root_page_id
        ] + await self.confluence_service.get_all_descendants(root_page_id)
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        all_tasks = await self._collect_tasks(all_page_ids)
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return [], []  # Return empty lists if no tasks found

        logging.info(
            f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing..."
        )
        jira_creation_results, page_update_results = await self._process_tasks(
            all_tasks, context
        )  # noqa: E501
        return jira_creation_results, page_update_results

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
        self, tasks: List[ConfluenceTask], context: SyncTaskContext
    ) -> Tuple[List[JiraTaskCreationResult], List[ConfluencePageUpdateResult]]:
        """
        Processes a list of tasks, creates Jira issues, and tracks results.
        Then updates Confluence pages and tracks those results.
        """
        jira_creation_results: List[JiraTaskCreationResult] = []
        tasks_to_update_on_pages: Dict[str, List[Dict[str, Any]]] = {}
        confluence_page_update_results: List[ConfluencePageUpdateResult] = []

        processing_coroutines = [
            self._process_single_task(task, context) for task in tasks
        ]
        single_task_internal_results = await asyncio.gather(*processing_coroutines)

        for result in single_task_internal_results:
            jira_creation_results.append(
                JiraTaskCreationResult(
                    confluence_page_id=result.task_data.confluence_page_id,
                    confluence_task_id=result.task_data.confluence_task_id,
                    task_summary=result.task_data.task_summary,
                    original_page_version=result.task_data.original_page_version,
                    request_user=result.request_user,
                    new_jira_task_key=result.new_jira_task_key,
                    creation_status_text=result.status_text,
                    success=result.status_text.startswith("Success"),
                    error_message=result.status_text
                    if not result.status_text.startswith("Success")
                    else None,  # noqa: E501
                )
            )
            if result.status_text.startswith("Success") and result.new_jira_task_key:
                tasks_to_update_on_pages.setdefault(
                    result.task_data.confluence_page_id, []
                ).append(  # noqa: E501
                    {
                        "confluence_task_id": result.task_data.confluence_task_id,
                        "jira_key": result.new_jira_task_key,
                    }
                )

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            update_coroutines = []
            for page_id, mappings in tasks_to_update_on_pages.items():
                update_coroutines.append(
                    self._update_confluence_page_and_collect_result(page_id, mappings)
                )
            confluence_page_update_results = await asyncio.gather(*update_coroutines)
        else:
            logging.info("""No Jira tasks were successfully created,
                    skipping Confluence page updates.""")

        return jira_creation_results, confluence_page_update_results

    async def _update_confluence_page_and_collect_result(
        self, page_id: str, mappings: List[Dict[str, Any]]
    ) -> ConfluencePageUpdateResult:
        """
        Helper to update a single Confluence page and return its result.
        """
        page_title = "N/A"  # Default
        try:
            page_details = await self.confluence_service.get_page_by_id(
                page_id, expand="version"
            )  # noqa: E501
            if page_details:
                page_title = page_details.get("title", page_title)
            else:
                # If page details cannot be retrieved, it's a failure.
                raise ConfluenceApiError(
                    f"Could not retrieve page details for ID {page_id} for update."
                )

            update_successful = (
                await self.confluence_service.update_page_with_jira_links(
                    page_id, mappings
                )
            )  # noqa: E501

            if update_successful:  # FIX: Check the boolean result
                jira_keys_replaced = [m["jira_key"] for m in mappings]
                return ConfluencePageUpdateResult(
                    page_id=page_id,
                    page_title=page_title,
                    updated=True,
                    jira_keys_replaced=jira_keys_replaced,
                    error_message=None,
                )
            else:
                error_msg = f"Confluence service reported failure for page {page_id} update via update_page_with_jira_links."  # noqa: E501
                logger.error(error_msg)
                return ConfluencePageUpdateResult(
                    page_id=page_id,
                    page_title=page_title,
                    updated=False,
                    jira_keys_replaced=[],
                    error_message=error_msg,
                )
        except ConfluenceApiError as e:
            logger.error(
                f"Failed to update Confluence page {page_id}: {e}", exc_info=True
            )  # noqa: E501
            return ConfluencePageUpdateResult(
                page_id=page_id,
                page_title=page_title,
                updated=False,
                jira_keys_replaced=[],
                error_message=str(e),
            )
        except Exception as e:
            error_msg = f"An unexpected error occurred while updating Confluence page {page_id}: {e}"  # noqa: E501
            logger.error(error_msg, exc_info=True)
            return ConfluencePageUpdateResult(
                page_id=page_id,
                page_title=page_title,
                updated=False,
                jira_keys_replaced=[],
                error_message=error_msg,
            )

    async def _process_single_task(
        self, task: ConfluenceTask, context: SyncTaskContext
    ) -> SingleTaskResult:
        """
        Helper method to process a single Confluence task.
        Returns SingleTaskResult for internal use to
            build JiraTaskCreationResult.
        """
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
                f"Skipped task '{task.task_summary}' "
                f"(ID: {task.confluence_task_id}) "
                f"on page ID: {task.confluence_page_id} - No Work Package found."
            )
            logger.error(f"ERROR: {error_msg}")
            return SingleTaskResult(
                task_data=task,
                status_text="Failed - No Work Package found",
                request_user=context.request_user,
            )

        closest_wp_key = closest_wp["key"]

        assignee_from_wp = None

        if not isinstance(closest_wp, dict):
            error_msg = (
                f"Closest Work Package (ID: {task.confluence_page_id}) "
                f"is not a dictionary. Type: {type(closest_wp)}. Data: {closest_wp}"
            )
            logger.error(f"CRITICAL ERROR: {error_msg}")
            return SingleTaskResult(
                task_data=task,
                status_text="Failed - Malformed Work Package data",
                request_user=context.request_user,
            )

        closest_wp_key = closest_wp.get("key")
        if not closest_wp_key:
            error_msg = (
                f"Closest Work Package (ID: {task.confluence_page_id}) "
                f"is missing 'key' field. Data: {closest_wp}"
            )
            logger.error(f"CRITICAL ERROR: {error_msg}")
            return SingleTaskResult(
                task_data=task,
                status_text="Failed - Work Package key missing",
                request_user=context.request_user,
            )

        if not task.assignee_name:
            fields = closest_wp.get("fields")
            if isinstance(fields, dict):
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

        new_issue_key = None
        status_text = "Failed - Jira task creation"
        try:
            new_issue_key = await self.jira_service.create_issue(
                task, closest_wp_key, context
            )

            if new_issue_key:
                status_text = "Success"

                if task.status == "complete":
                    target_status = config.JIRA_TARGET_STATUSES["completed_task"]
                    transition_success = await self.jira_service.transition_issue(
                        new_issue_key, target_status
                    )  # noqa: E501
                    if transition_success:
                        status_text = "Success - Completed Task Created"
                    else:
                        status_text = "Success - Task Created (Transition Failed)"
                elif config.DEV_ENVIRONMENT:
                    target_status = config.JIRA_TARGET_STATUSES["new_task_dev"]
                    transition_success = await self.jira_service.transition_issue(
                        new_issue_key, target_status
                    )  # noqa: E501
                    if not transition_success:
                        status_text = "Success - Task Created (Dev Transition Failed)"

                if assignee_from_wp is None and task.assignee_name is None:
                    logger.info(
                        f"Work Package was unassigned (assignee_from_wp is None). "
                        f"Attempting to explicitly unassign newly created Jira issue "
                        f"{new_issue_key}."
                    )
                    unassign_successful = await self.jira_service.assign_issue(
                        new_issue_key, None
                    )
                    if unassign_successful:
                        logger.info(
                            f"Successfully explicitly unassigned issue {new_issue_key}."
                        )
                    else:
                        logger.warning(
                            f"Failed to explicitly unassign issue {new_issue_key} "
                            f"after creation."
                        )
                else:
                    logger.info(
                        f"Issue {new_issue_key} created with assignee "
                        f"from Work Package: {assignee_from_wp}."
                    )
            else:
                error_msg = (
                    f"Failed to create Jira task for '{task.task_summary}' "
                    f"(ID: {task.confluence_task_id}) on page ID: "
                    f"{task.confluence_page_id} linked to WP: {closest_wp_key}. "
                    "Jira API returned no key."
                )
                logger.error(f"ERROR: {error_msg}")
                status_text = "Failed - Jira API (No Key)"

        except JiraApiError as e:
            error_msg = (
                f"An unexpected error occurred during Jira task creation for "
                f"'{task.task_summary}': {e}"
            )
            logger.error(error_msg, exc_info=True)
            status_text = f"Failed - JiraApiError: {str(e)}"

        return SingleTaskResult(
            task_data=task,
            status_text=status_text,
            new_jira_task_key=new_issue_key,
            linked_work_package=closest_wp_key,
            request_user=context.request_user,
        )

    def _determine_overall_status(
        self, results: List[Any], success_check_func: Callable[[Any], bool]
    ) -> str:
        """
        Determines the overall status based on a
        list of results and a success check function.
        """
        if not results:
            return "Skipped - No tasks processed"

        all_successful = all(success_check_func(r) for r in results)
        any_successful = any(success_check_func(r) for r in results)

        if all_successful:
            return "Success"
        elif any_successful:
            return "Partial Success"
        else:
            return "Failed"
