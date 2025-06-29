"""
Orchestrates the process of undoing a synchronization run.

This module provides the `UndoSyncTaskOrchestrator`, which is responsible for
reversing the actions of a previous automation run. It reads a results file
(in JSON format, processed via pandas for robustness) and performs two main
actions:
1. Transitions any created Jira tasks back to a 'Backlog' status.
2. Reverts the modified Confluence pages to their state before the script ran,
   using the version number captured in the results file.

This script can be run with a specific results file path or, if none is
provided, it will automatically find and use the most recent results file.
"""

import json
import logging
import os
import warnings
from typing import Dict, Optional, Set, Tuple

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

# Suppress insecure request warnings for local/dev environments.
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)


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

    def run(self, results_file_override: Optional[str] = None) -> None:
        """
        Main entry point for the undo workflow.

        Args:
            results_file_override (Optional[str]): A specific path to a results
                file. If None, the latest results file will be used.
        """
        setup_logging("logs_undo", "undo_run")
        logging.info("\n--- Starting Undo Automation Script ---")

        results_df = self._load_results_file(results_file_override)
        if results_df is None or results_df.empty:
            logging.warning(
                "Results file is empty or could not be read. No actions to perform."
            )
            return

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
            self.jira.transition_issue(key, target_status)

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
                logging.error(
                    f"Failed to get content for page '{page_id}' version {version}. "
                    "Skipping rollback."
                )

    def _load_results_file(
        self, file_override: Optional[str]
    ) -> Optional[pd.DataFrame]:
        """Loads the specified or latest results file into a pandas DataFrame."""
        if file_override:
            path = file_override
        else:
            path = self._find_latest_results_file(config.OUTPUT_DIRECTORY)
            if path:
                logging.info(f"Found latest results file: '{os.path.basename(path)}'")

        if not path or not os.path.exists(path):
            logging.error("ERROR: Results file not found. Aborting.")
            return None

        logging.info(f"Using results file: '{path}'")
        try:
            with open(path, "r") as f:
                data = json.load(f)
            # Convert to DataFrame for easier and more robust data handling.
            return pd.DataFrame(data)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logging.error(
                f"ERROR: Failed to read or parse JSON file '{path}'. Details: {e}"
            )
            return None

    def _find_latest_results_file(self, folder: str) -> Optional[str]:
        """Finds the most recent automation results file in a directory."""
        if not os.path.exists(folder):
            return None
        files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.startswith("automation_results_") and f.endswith(".json")
        ]
        return max(files, key=os.path.getmtime) if files else None

    def _parse_results_for_undo(
        self, df: pd.DataFrame
    ) -> Tuple[Set[str], Dict[str, int]]:
        """
        Parses the results DataFrame to extract data needed for the undo actions.

        Args:
            df (pd.DataFrame): The DataFrame loaded from the results file.

        Returns:
            A tuple containing:
            - A set of Jira issue keys to be transitioned.
            - A dictionary mapping Confluence page IDs to the version number
              they should be rolled back to.
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
            logging.error(
                f"Results file is missing required columns. Expected: {required_cols}, "
                f"Found: {list(df.columns)}"
            )
            return jira_keys, pages

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


if __name__ == "__main__":
    # 1. Initialize raw API clients.
    jira_client = Jira(
        url=config.JIRA_URL,
        token=config.JIRA_API_TOKEN,
        cloud=False,
        verify_ssl=False,
    )
    confluence_client = Confluence(
        url=config.CONFLUENCE_URL,
        token=config.CONFLUENCE_API_TOKEN,
        cloud=False,
        verify_ssl=False,
    )

    # 2. Instantiate the low-level, resilient API handlers.
    safe_jira_api = SafeJiraApi(jira_client)
    safe_confluence_api = SafeConfluenceApi(confluence_client)

    # 3. Instantiate the high-level service implementations.
    jira_service = JiraService(safe_jira_api)
    confluence_service = ConfluenceService(safe_confluence_api)

    # 4. Inject services into the orchestrator and run it.
    undo_orchestrator = UndoSyncTaskOrchestrator(
        confluence_service, jira_service
    )
    undo_orchestrator.run()
