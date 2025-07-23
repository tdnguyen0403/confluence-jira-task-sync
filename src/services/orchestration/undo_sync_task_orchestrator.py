import logging
from typing import Any, Dict, List, Set, Tuple

# Removed pandas import as it's no longer used
# Removed warnings import as it's no longer directly used

from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.exceptions import InvalidInputError
from src.models.data_models import (
    UndoRequestItem,
)  # Import UndoRequestItem for direct parsing

logger = logging.getLogger(__name__)


class UndoSyncTaskOrchestrator:
    """
    Orchestrates the undo process by coordinating service interactions.
    """

    def __init__(
        self,
        confluence_service: ConfluenceApiServiceInterface,
        jira_service: JiraApiServiceInterface,
        issue_finder_service: Any,  # Type hint for IssueFinderService to avoid circular import
    ):
        """
        Initializes the UndoSyncTaskOrchestrator.

        Args:
            confluence_service (ConfluenceApiServiceInterface): A service for Confluence ops.
            jira_service (JiraApiServiceInterface): A service for Jira ops.
            issue_finder_service (Any): A service for finding specific Jira issues.
        """
        self.confluence_service = confluence_service
        self.jira_service = jira_service
        self.issue_finder_service = issue_finder_service

    async def run(self, results_json_data: List[Dict[str, Any]]) -> None:
        """
        Main entry point for the undo workflow asynchronously.

        Args:
            results_json_data (List[Dict[str, Any]]): A JSON object (list of dicts)
                containing the results data directly. This is a mandatory input.
        Raises:
            InvalidInputError: If required input data is missing or malformed.
            UndoError: For general errors during the undo process.
        """
        logging.info("\n--- Starting Undo Automation Script ---")

        if not results_json_data:
            logger.error("ERROR: No results JSON data provided. Aborting.")
            raise InvalidInputError("No results JSON data provided for undo operation.")

        # Directly parse the list of dictionaries without DataFrame
        jira_keys, pages_to_rollback = self._parse_results_for_undo(
            results_json_data
        )  #

        if not jira_keys and not pages_to_rollback:
            logger.error(
                "ERROR: Provided JSON data contains no successful tasks for undo actions. No actions to perform."
            )
            raise InvalidInputError(
                "Provided JSON data contains no successful tasks for undo actions."
            )

        await self._transition_jira_tasks(jira_keys)
        await self._rollback_confluence_pages(pages_to_rollback)

        logging.info("\n--- Undo Automation Script Finished ---")
        logging.info("Review the log file and Confluence/Jira to confirm changes.")

    async def _transition_jira_tasks(self, jira_keys: Set[str]) -> None:
        """Transitions a set of Jira tasks back to the 'undo' status asynchronously."""
        if not jira_keys:
            logging.info("No Jira tasks to transition.")
            return

        logging.info(
            f"\n--- Phase 1: Transitioning {len(jira_keys)} Jira Tasks to Backlog ---"
        )
        target_status = config.JIRA_TARGET_STATUSES["undo"]
        for key in sorted(list(jira_keys)):
            try:
                await self.jira_service.transition_issue(key, target_status)
            except Exception as e:
                logger.error(
                    f"Failed to transition Jira issue '{key}' to '{target_status}': {e}",
                    exc_info=True,
                )

    async def _rollback_confluence_pages(self, pages: Dict[str, int]) -> None:
        """Rolls back a set of Confluence pages to a specific version asynchronously."""
        if not pages:
            logging.info("No Confluence pages to roll back.")
            return

        logging.info(f"\n--- Phase 2: Rolling back {len(pages)} Confluence Pages ---")
        logging.warning(
            "NOTE: This operation reverts pages to their state *before* the script ran."
        )
        for page_id, version in sorted(pages.items()):
            logging.info(f"Attempting to roll back page {page_id} to version {version}")
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
                else:
                    error_msg = f"Failed to get content for page '{page_id}' version {version}. Skipping rollback."
                    logger.error(error_msg)
            except Exception as e:
                logger.error(
                    f"Error rolling back page '{page_id}' to version {version}: {e}",
                    exc_info=True,
                )

    def _parse_results_for_undo(
        self, results_data: List[Dict[str, Any]]
    ) -> Tuple[Set[str], Dict[str, int]]:
        """
        Parses the results list of dictionaries to extract data needed for the undo actions.

        Args:
            results_data (List[Dict[str, Any]]): The list of dictionaries loaded from the results data.

        Returns:
            A tuple containing:
            - A set of Jira issue keys to be transitioned.
            - A dictionary mapping Confluence page IDs to the version number
              they should be rolled back to.
        Raises:
            MissingRequiredDataError: If essential data points are missing from an item.
        """
        jira_keys: Set[str] = set()
        pages: Dict[str, int] = {}

        for item_data in results_data:
            try:
                # Use Pydantic's UndoRequestItem to validate and parse each item
                item = UndoRequestItem(**item_data)  #

                # Now check item.status_text start wtih "Success" (for both incomplete & complete tasks)
                if item.status_text and item.status_text.startswith("Success"):  #
                    if item.new_jira_task_key:  #
                        jira_keys.add(item.new_jira_task_key)  #

                    # confluence_page_id and original_page_version are required fields
                    # in UndoRequestItem and will be validated by Pydantic.
                    # No need for pandas.isna equivalent.
                    pages[item.confluence_page_id] = item.original_page_version  #

            except (
                Exception
            ) as e:  # This will catch Pydantic ValidationErrors for malformed items
                logger.warning(
                    f"Skipping malformed or incomplete undo result item: {item_data}. Error: {e}"
                )

        # If after parsing all items, no valid data was found
        if not jira_keys and not pages:
            raise InvalidInputError(
                "No successful undo items found after processing results data."
            )

        return jira_keys, pages
