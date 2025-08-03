# File: src/services/orchestration/undo_sync_task_orchestrator.py

import asyncio
import logging
from typing import Any, Callable, Dict, List, Set, Tuple

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import (
    UndoActionResult,
    UndoSyncTaskRequest,
    UndoSyncTaskResponse,
)

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

    async def run(
        self, undo_requests: List[UndoSyncTaskRequest], request_id: str
    ) -> UndoSyncTaskResponse:
        """
        Main entry point for the undo workflow. Returns a complete
        UndoSyncTaskResponse object with the overall status and detailed results.
        """
        logging.info("\n--- Starting Concurrent Undo Automation Script ---")

        if not undo_requests:
            raise InvalidInputError("No data provided for undo operation.")

        jira_keys, pages = self._parse_undo_requests(undo_requests)

        action_coroutines = []
        for key in jira_keys:
            action_coroutines.append(self._transition_jira_task(key))
        for page_id, version in pages.items():
            action_coroutines.append(self._rollback_confluence_page(page_id, version))

        if not action_coroutines:
            raise InvalidInputError("No valid undo actions could be parsed.")

        # Execute all operations in parallel and collect individual results
        results = await asyncio.gather(*action_coroutines, return_exceptions=True)

        processed_results: List[UndoActionResult] = []
        for res in results:
            if isinstance(res, UndoActionResult):
                processed_results.append(res)
            elif isinstance(res, Exception):
                logger.error(f"Error during undo action: {res}", exc_info=res)
                processed_results.append(
                    UndoActionResult(
                        action_type="unknown_error",
                        target_id="N/A",
                        success=False,
                        status_message=f"An unexpected error occurred: {res}",
                        error_message=str(res),
                    )
                )

        overall_status = self._determine_overall_status(
            processed_results, lambda r: r.success
        )
        logging.info(f"\n--- Undo Automation Script Finished: {overall_status} ---")

        return UndoSyncTaskResponse(
            request_id=request_id,
            overall_status=overall_status,
            results=processed_results,
        )

    async def _transition_jira_task(self, jira_key: str) -> UndoActionResult:
        """Transitions a single Jira task back to the 'undo' status."""
        target_status = config.JIRA_TARGET_STATUSES["undo"]
        try:
            logging.info(f"Transitioning Jira issue '{jira_key}' to '{target_status}'.")
            success = await self.jira_service.transition_issue(jira_key, target_status)
            if success:
                return UndoActionResult(
                    action_type="jira_transition",
                    target_id=jira_key,
                    success=True,
                    status_message=f"Successfully transitioned to '{target_status}'.",
                )
            else:
                raise Exception(
                    f"API returned failure for transition to {target_status}"
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
        """Rolls back a single Confluence page to a specific version."""
        logging.info(f"Rolling back page {page_id} to version {version}.")
        page_title = "N/A"
        try:
            page = await self.confluence_service.get_page_by_id(
                page_id, version=version, expand="body.storage"
            )
            if not page or "body" not in page or "storage" not in page["body"]:
                raise Exception(f"Failed to get historical content for v{version}.")

            page_title = page.get("title", page_title)
            historical_content = page["body"]["storage"]["value"]
            success = await self.confluence_service.update_page_content(
                page_id, page_title, historical_content
            )

            if success:
                return UndoActionResult(
                    action_type="confluence_rollback",
                    target_id=page_id,
                    success=True,
                    status_message=(
                        f"Rolled back page '{page_title}' to version {version}."
                    ),
                )
            else:
                raise Exception("API returned failure for page update.")
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

    def _parse_undo_requests(
        self, requests_data: List[UndoSyncTaskRequest]
    ) -> Tuple[Set[str], Dict[str, int]]:
        """
        Parses requests to find unique Jira keys and the earliest page version.
        """
        jira_keys: Set[str] = set()
        pages: Dict[str, int] = {}

        for item in requests_data:
            if item.new_jira_task_key:
                jira_keys.add(item.new_jira_task_key)

            if item.confluence_page_id and item.original_page_version is not None:
                page_id = item.confluence_page_id
                version = item.original_page_version
                if page_id not in pages or version < pages[page_id]:
                    pages[page_id] = version
            else:
                logger.warning(
                    f"Skipping undo item with missing data: {item.model_dump()}"
                )

        return jira_keys, pages

    def _determine_overall_status(
        self, results: List[Any], success_check: Callable[[Any], bool]
    ) -> str:
        """
        Determines the overall status from a list of result objects.
        """
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
