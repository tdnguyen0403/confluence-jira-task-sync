# File: src/services/orchestration/undo_sync_task_orchestrator.py

import asyncio
import logging
from typing import Any, Callable, Dict, List, Set, Tuple

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import UndoActionResult, UndoSyncTaskRequest

logger = logging.getLogger(__name__)


class UndoSyncTaskOrchestrator:
    """
    Orchestrates the undo process by coordinating service interactions.
    """

    def __init__(
        self,
        confluence_service: ConfluenceApiServiceInterface,
        jira_service: JiraApiServiceInterface,
        issue_finder_service: IssueFinderServiceInterface,
    ):
        self.confluence_service = confluence_service
        self.jira_service = jira_service
        self.issue_finder_service = issue_finder_service

    # Change the input type to List[UndoSyncTaskRequest]
    # and return List[UndoActionResult]
    async def run(
        self, results_data: List[UndoSyncTaskRequest]
    ) -> List[UndoActionResult]:
        """
        Main entry point for the undo workflow asynchronously.
        Processes each undo request and returns a list of detailed results.
        """
        logging.info("\n--- Starting Concurrent Undo Automation Script ---")

        if not results_data:
            raise InvalidInputError("No results data provided for undo operation.")

        # Prepare a list of coroutines, each returning an UndoActionResult
        # Re-using the parsing logic from the old _parse_results_for_undo for robustness
        jira_keys_to_transition, pages_to_rollback = self._parse_undo_requests(
            results_data
        )  # noqa: E501

        # Create coroutines for each distinct action
        action_coroutines = []
        for key in jira_keys_to_transition:
            action_coroutines.append(self._transition_jira_task(key))
        for page_id, version in pages_to_rollback.items():
            action_coroutines.append(self._rollback_confluence_page(page_id, version))

        # Execute all operations in parallel and collect individual results
        all_results = await asyncio.gather(*action_coroutines, return_exceptions=True)

        processed_results: List[UndoActionResult] = []
        for res in all_results:
            if isinstance(res, UndoActionResult):
                processed_results.append(res)
            elif isinstance(res, Exception):
                # Log exceptions caught by gather (e.g.,
                # from _transition_jira_task if it re-raises)
                logger.error(
                    f"An error occurred during an undo action: {res}", exc_info=res
                )

        logging.info("\n--- Undo Automation Script Finished ---")
        return processed_results

    async def _transition_jira_task(self, jira_key: str) -> UndoActionResult:
        """Transitions a single Jira task back to the
        'undo' status and returns an UndoActionResult."""
        target_status = config.JIRA_TARGET_STATUSES["undo"]
        try:
            logging.info(f"Transitioning Jira issue '{jira_key}' to '{target_status}'.")
            success = await self.jira_service.transition_issue(jira_key, target_status)
            if success:
                logging.info(f"Successfully transitioned Jira issue '{jira_key}'.")
                return UndoActionResult(
                    action_type="jira_transition",
                    target_id=jira_key,
                    success=True,
                    status_message=f"Successfully transitioned to '{target_status}'.",
                )
            else:
                error_msg = (
                    f"Failed to transition Jira issue {jira_key} to {target_status}."  # noqa: E501
                )
                logger.error(error_msg)
                return UndoActionResult(
                    action_type="jira_transition",
                    target_id=jira_key,
                    success=False,
                    status_message=error_msg,
                    error_message=error_msg,
                )
        except Exception as e:
            error_msg = f"Exception transitioning Jira issue {jira_key}: {e}"
            logger.error(error_msg, exc_info=True)
            return UndoActionResult(
                action_type="jira_transition",
                target_id=jira_key,
                success=False,
                status_message=error_msg,
                error_message=str(e),
            )

    async def _rollback_confluence_page(
        self, page_id: str, version: int
    ) -> UndoActionResult:
        """Rolls back a single Confluence page to a
        specific version and returns an UndoActionResult."""

        logging.info(f"Attempting to roll back page {page_id} to version {version}.")
        page_title = "N/A"  # Default
        try:
            # Try to get page title for better logging/result reporting
            current_page_details = await self.confluence_service.get_page_by_id(page_id)
            if current_page_details:
                page_title = current_page_details.get("title", page_title)

            historical_page = await self.confluence_service.get_page_by_id(
                page_id, version=version, expand="body.storage"
            )

            if (
                historical_page
                and "body" in historical_page
                and "storage" in historical_page["body"]
            ):
                historical_content = historical_page["body"]["storage"]["value"]
                success = await self.confluence_service.update_page_content(
                    page_id, page_title, historical_content
                )
                if success:
                    logging.info(
                        f"Successfully rolled back page '{page_title}' "
                        f"({page_id}) to version {version}."
                    )
                    return UndoActionResult(
                        action_type="confluence_rollback",
                        target_id=page_id,
                        success=True,
                        status_message=f"Successfully rolled back page '"
                        f"{page_title}' to version {version}.",
                    )
                else:
                    error_msg = (
                        f"Confluence API update failed for page '{page_title}' "
                        f"({page_id}) version {version}."
                    )
                    logger.error(error_msg)
                    return UndoActionResult(
                        action_type="confluence_rollback",
                        target_id=page_id,
                        success=False,
                        status_message=error_msg,
                        error_message=error_msg,
                    )
            else:
                error_msg = (
                    f"Failed to get historical content for page '"
                    f"{page_title}' ({page_id})"
                    f" version {version} to perform rollback."
                )
                logger.error(error_msg)
                return UndoActionResult(
                    action_type="confluence_rollback",
                    target_id=page_id,
                    success=False,
                    status_message=error_msg,
                    error_message=error_msg,
                )
        except Exception as e:
            error_msg = f"Exception rolling back page '{page_title}' ({page_id}): {e}"
            logger.error(error_msg, exc_info=True)
            return UndoActionResult(
                action_type="confluence_rollback",
                target_id=page_id,
                success=False,
                status_message=error_msg,
                error_message=str(e),
            )

    def _parse_undo_requests(  # Renamed from _parse_results_for_undo for clarity
        self, requests_data: List[UndoSyncTaskRequest]
    ) -> Tuple[Set[str], Dict[str, int]]:
        """
        Parses a list of UndoSyncTaskRequest objects to identify unique Jira keys
        to transition and the earliest version for each Confluence page to roll back.
        """
        jira_keys: Set[str] = set()
        pages_to_rollback: Dict[str, int] = {}

        for item in requests_data:
            if item.new_jira_task_key:
                jira_keys.add(item.new_jira_task_key)

            if item.confluence_page_id and item.original_page_version is not None:
                if (
                    item.confluence_page_id not in pages_to_rollback
                    or item.original_page_version
                    < pages_to_rollback[item.confluence_page_id]
                ):
                    pages_to_rollback[item.confluence_page_id] = (
                        item.original_page_version
                    )
            else:
                logger.warning(
                    f"Skipping undo item due to missing confluence_page_id or"
                    f"original_page_version required for page rollback. Item: "
                    f"{item.model_dump()}"
                )

        if not jira_keys and not pages_to_rollback:
            raise InvalidInputError(
                "No valid undo actions found after processing requests data."
            )

        return jira_keys, pages_to_rollback

    def _determine_overall_status(
        self, results: List[Any], success_check_func: Callable[[Any], bool]
    ) -> str:
        """
        Determines the overall status based on a
        list of results and a success check function.
        """
        if not results:
            return "Skipped - No actions processed"

        all_successful = all(success_check_func(r) for r in results)
        any_successful = any(success_check_func(r) for r in results)

        if all_successful:
            return "Success"
        elif any_successful:
            return "Partial Success"
        else:
            return "Failed"
