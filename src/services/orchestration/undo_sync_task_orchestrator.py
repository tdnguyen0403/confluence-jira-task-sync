import asyncio
import logging
from typing import Any, Dict, List, Set, Tuple

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import (
    UndoRequestItem,
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
        issue_finder_service: Any,
    ):
        self.confluence_service = confluence_service
        self.jira_service = jira_service
        self.issue_finder_service = issue_finder_service

    async def run(self, results_json_data: List[Dict[str, Any]]) -> None:
        """
        Main entry point for the undo workflow asynchronously.
        Parses results data and runs all undo operations concurrently.
        """
        logging.info("\n--- Starting Concurrent Undo Automation Script ---")

        if not results_json_data:
            raise InvalidInputError("No results JSON data provided for undo operation.")

        # The _parse_results_for_undo method returns two distinct collections:
        # 1. A set of Jira keys to be transitioned.
        # 2. A dictionary of Confluence pages and the version to roll back to.
        # They must be unpacked into two separate variables.
        jira_keys_to_transition, pages_to_rollback = self._parse_results_for_undo(
            results_json_data
        )

        # Create a list of coroutines for each distinct action.
        jira_coroutines = [
            self._transition_jira_task(key) for key in jira_keys_to_transition
        ]
        confluence_coroutines = [
            self._rollback_confluence_page(page_id, version)
            for page_id, version in pages_to_rollback.items()
        ]

        # Combine the lists and execute all operations in parallel.
        all_coroutines = jira_coroutines + confluence_coroutines
        if all_coroutines:
            await asyncio.gather(*all_coroutines, return_exceptions=True)

        logging.info("\n--- Undo Automation Script Finished ---")
        logging.info("Review the log file and Confluence/Jira to confirm changes.")

    async def _transition_jira_task(self, jira_key: str) -> None:
        """Transitions a single Jira task back to the 'undo' status."""
        target_status = config.JIRA_TARGET_STATUSES["undo"]
        try:
            logging.info(f"Transitioning Jira issue '{jira_key}' to '{target_status}'.")
            await self.jira_service.transition_issue(jira_key, target_status)
            logging.info(f"Successfully transitioned Jira issue '{jira_key}'.")
        except Exception as e:
            logger.error(
                f"Failed to transition Jira issue '{jira_key}': {e}", exc_info=True
            )
            # Re-raise the exception so asyncio.gather can report it as a failure.
            raise

    async def _rollback_confluence_page(self, page_id: str, version: int) -> None:
        """Rolls back a single Confluence page to a specific version."""
        logging.info(f"Attempting to roll back page {page_id} to version {version}.")
        try:
            historical_page = await self.confluence_service.get_page_by_id(
                page_id, version=version, expand="body.storage"
            )
            current_page = await self.confluence_service.get_page_by_id(page_id)

            if (
                historical_page
                and current_page
                and "body" in historical_page
                and "storage" in historical_page["body"]
            ):
                historical_content = historical_page["body"]["storage"]["value"]
                await self.confluence_service.update_page_content(
                    page_id, current_page["title"], historical_content
                )
                logging.info(
                    f"Successfully rolled back page {page_id} to version {version}."
                )
            else:
                raise InvalidInputError(
                    f"Failed to get required content for page '{page_id}'"
                    f" version {version} to perform rollback."
                )
        except Exception as e:
            logger.error(f"Error rolling back page '{page_id}': {e}", exc_info=True)
            # Re-raise the exception for asyncio.gather.
            raise

    def _parse_results_for_undo(
        self, results_data: List[Dict[str, Any]]
    ) -> Tuple[Set[str], Dict[str, int]]:
        """
        Parses results to find all unique Jira keys to transition and the
        single oldest page version for each Confluence page to roll back to.
        """
        jira_keys: Set[str] = set()
        pages_to_rollback: Dict[str, int] = {}

        for item_data in results_data:
            try:
                item = UndoRequestItem(**item_data)
                if (
                    item.status_text
                    and item.status_text.startswith("Success")
                    and item.new_jira_task_key
                ):
                    jira_keys.add(item.new_jira_task_key)
                    if (
                        item.confluence_page_id not in pages_to_rollback
                        or item.original_page_version
                        < pages_to_rollback[item.confluence_page_id]
                    ):
                        pages_to_rollback[item.confluence_page_id] = (
                            item.original_page_version
                        )
            except Exception as e:
                logger.warning(f"Skipping malformed undo item: {item_data}. Error: {e}")

        # The error message must match the test expectation exactly.
        if not jira_keys and not pages_to_rollback:
            raise InvalidInputError(
                "No successful undo items found after processing results data."
            )

        return jira_keys, pages_to_rollback
