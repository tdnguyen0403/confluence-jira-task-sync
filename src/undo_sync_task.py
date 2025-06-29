"""
Orchestrates the process of undoing a synchronization run.

This module provides the `UndoSyncTaskOrchestrator`, which is responsible for
reversing the actions of a previous automation run. It reads a results object
(in JSON format, processed via pandas for robustness) and performs two main
actions:
1. Transitions any created Jira tasks back to a 'Backlog' status.
2. Reverts the modified Confluence pages to their state before the script ran,
   using the version number captured in the results data.

This script expects a JSON object containing the results data.
"""

import json
import logging
import os
import warnings
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import requests
from atlassian import Confluence, Jira

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.interfaces.api_service_interface import ApiServiceInterface
from src.services.confluence_service import ConfluenceService
from src.services.jira_service import JiraService
from src.utils.logging_config import setup_logging
from src.exceptions import UndoError, InvalidInputError, MissingRequiredDataError # Import custom exceptions

# Suppress insecure request warnings for local/dev environments.
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)

# Initialize logger for this module
logger = logging.getLogger(__name__)


class UndoSyncTaskOrchestrator:
    """
    Orchestrates the undo process by coordinating service interactions.
    """

    def __init__(
        self,
        confluence_service: ApiServiceInterface,
        jira_service: ApiServiceInterface,
    ):
        """
        Initializes the UndoSyncTaskOrchestrator.

        Args:
            confluence_service (ApiServiceInterface): A service for Confluence ops.
            jira_service (ApiServiceInterface): A service for Jira ops.
        """
        self.confluence = confluence_service
        self.jira = jira_service

    def run(self, results_json_data: List[Dict[str, Any]]) -> None:
        """
        Main entry point for the undo workflow.

        Args:
            results_json_data (List[Dict[str, Any]]): A JSON object (list of dicts)
                containing the results data directly. This is a mandatory input.
        Raises:
            InvalidInputError: If required input data is missing or malformed.
            UndoError: For general errors during the undo process.
        """
        setup_logging("logs/logs_undo", "undo_sync_task_run")
        logging.info("\n--- Starting Undo Automation Script ---")

        if not results_json_data:
            logger.error("ERROR: No results JSON data provided. Aborting.")
            raise InvalidInputError("No results JSON data provided for undo operation.")

        results_df = self._load_results_from_json(results_json_data)
        if results_df is None or results_df.empty:
            logger.error(
                "ERROR: Provided JSON data is empty or could not be processed. No actions to perform."
            )
            raise InvalidInputError("Provided JSON data is empty or could not be processed for undo operation.")

        jira_keys, pages_to_rollback = self._parse_results_for_undo(results_df)
        self._transition_jira_tasks(jira_keys)
        self._rollback_confluence_pages(pages_to_rollback)

        logging.info("\n--- Undo Automation Script Finished ---")
        logging.info("Review the log file and Confluence/Jira to confirm changes.")

    def _transition_jira_tasks(self, jira_keys: Set[str]) -> None:
        """Transitions a set of Jira tasks back to the 'undo' status."""
        if not jira_keys:
            logging.info("No Jira tasks to transition.")
            return

        logging.info(
            f"\n--- Phase 1: Transitioning {len(jira_keys)} Jira Tasks to Backlog ---"
        )
        target_status = config.JIRA_TARGET_STATUSES["undo"]
        for key in sorted(list(jira_keys)):
            try:
                self.jira.transition_issue(key, target_status)
            except Exception as e:
                logger.error(f"Failed to transition Jira issue '{key}' to '{target_status}': {e}", exc_info=True)
                # Decide if this is critical enough to stop the whole undo and raise UndoError
                # For now, it will log and continue with other transitions.

    def _rollback_confluence_pages(self, pages: Dict[str, int]) -> None:
        """Rolls back a set of Confluence pages to a specific version."""
        if not pages:
            logging.info("No Confluence pages to roll back.")
            return

        logging.info(
            f"\n--- Phase 2: Rolling back {len(pages)} Confluence Pages ---"
        )
        logging.warning(
            "NOTE: This operation reverts pages to their state *before* the script ran."
        )
        for page_id, version in sorted(pages.items()):
            logging.info(f"Attempting to roll back page {page_id} to version {version}")
            try:
                historical_page = self.confluence.get_page_by_id(
                    page_id, version=version, expand="body.storage"
                )
                current_page = self.confluence.get_page_by_id(page_id)

                if (
                    historical_page
                    and current_page
                    and "body" in historical_page
                    and "storage" in historical_page["body"]
                ):
                    historical_content = historical_page["body"]["storage"]["value"]
                    self.confluence.update_page_content(
                        page_id, current_page["title"], historical_content
                    )
                else:
                    error_msg = f"Failed to get content for page '{page_id}' version {version}. Skipping rollback."
                    logger.error(error_msg)
                    # Decide if this failure should halt the entire undo process.
                    # For now, it just logs and skips this page.
            except Exception as e:
                logger.error(f"Error rolling back page '{page_id}' to version {version}: {e}", exc_info=True)
                # Similar to Jira transition, decide if this should halt everything.


    def _load_results_from_json(
        self, json_data: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Loads results data from a JSON object into a pandas DataFrame."""
        logging.info("Using provided JSON data for undo.")
        # No explicit error handling here, as InvalidInputError is raised higher up if json_data is empty.
        # Errors during DataFrame creation (e.g., malformed dicts) might raise pandas errors,
        # which would be caught by the run method's general exception.
        return pd.DataFrame(json_data)

    def _parse_results_for_undo(
        self, df: pd.DataFrame
    ) -> Tuple[Set[str], Dict[str, int]]:
        """
        Parses the results DataFrame to extract data needed for the undo actions.

        Args:
            df (pd.DataFrame): The DataFrame loaded from the results data.

        Returns:
            A tuple containing:
            - A set of Jira issue keys to be transitioned.
            - A dictionary mapping Confluence page IDs to the version number
              they should be rolled back to.
        Raises:
            MissingRequiredDataError: If essential columns are missing from the results data.
        """
        jira_keys: Set[str] = set()
        pages: Dict[str, int] = {}
        required_cols = [
            "Status",
            "New Jira Task Key",
            "confluence_page_id",
            "original_page_version",
        ]

        if not all(col in df.columns for col in required_cols):
            error_msg = f"Results data is missing required columns. Expected: {required_cols}, Found: {list(df.columns)}"
            logger.error(f"ERROR: {error_msg}")
            raise MissingRequiredDataError(error_msg) # <-- Raise custom exception

        for _, row in df.iterrows():
            if str(row.get("Status")).startswith("Success"):
                if pd.notna(row.get("New Jira Task Key")):
                    jira_keys.add(row["New Jira Task Key"])
                if pd.notna(row.get("confluence_page_id")) and pd.notna(
                    row.get("original_page_version")
                ):
                    pages[str(int(row["confluence_page_id"]))] = int(
                        row["original_page_version"]
                    )
        return jira_keys, pages