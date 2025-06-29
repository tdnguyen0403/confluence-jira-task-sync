"""
Main orchestrator for the Jira/Confluence automation script.

This module contains the `SyncTaskOrchestrator`, which serves as the central
controller for the entire workflow. It coordinates various services to:
1. Find and read a user-provided input file containing Confluence page URLs.
2. Scan each page and its descendants for tasks.
3. For each task, find the parent Work Package on the page.
4. Create a corresponding Jira task with the correct context and parent link.
5. Update the original Confluence page to replace the task with a Jira macro.
6. Save a detailed report of all actions taken.

This script is designed to be run as the main entry point for the automation.
"""

import json
import logging
import os
import warnings
from datetime import datetime
from typing import Dict, List

import requests
from atlassian import Confluence, Jira

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.interfaces.api_service_interface import ApiServiceInterface
from src.models.data_models import AutomationResult, ConfluenceTask
from src.services.confluence_service import ConfluenceService
from src.services.issue_finder_service import IssueFinderService
from src.services.jira_service import JiraService
from src.utils.logging_config import setup_logging

# Suppress insecure request warnings, common in corporate/dev environments.
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)


class SyncTaskOrchestrator:
    """
    Orchestrates the automation by coordinating service layer interactions.
    """

    def __init__(
        self,
        confluence_service: ApiServiceInterface,
        jira_service: ApiServiceInterface,
        issue_finder: IssueFinderService,
    ):
        """
        Initializes the SyncTaskOrchestrator with dependency-injected services.

        Args:
            confluence_service (ApiServiceInterface): A service for handling
                Confluence operations.
            jira_service (ApiServiceInterface): A service for handling Jira
                operations.
            issue_finder (IssueFinderService): A service for finding specific
                Jira issues on Confluence pages.
        """
        self.confluence = confluence_service
        self.jira = jira_service
        self.issue_finder = issue_finder
        self.results: List[AutomationResult] = []

    def _find_latest_input_file(
        self, folder: str = config.INPUT_DIRECTORY
    ) -> str | None:
        """
        Finds the most recently modified JSON file in the input folder.

        Args:
            folder (str): The directory to search for input files.

        Returns:
            str | None: The full path to the latest file, or None if no
                        JSON files are found or the directory doesn't exist.
        """
        if not os.path.exists(folder):
            logging.error(f"ERROR: Input directory '{folder}' not found. Aborting.")
            return None

        files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.endswith(".json")
        ]
        if not files:
            logging.error(
                f"ERROR: No JSON input files found in the '{folder}' directory. "
                "Aborting."
            )
            return None

        # Return the file with the most recent modification time.
        return max(files, key=os.path.getmtime)

    def run(self) -> None:
        """
        The main entry point for executing the automation workflow.
        """
        setup_logging("logs", "automation_run")
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        input_file = self._find_latest_input_file()
        if not input_file:
            return  # Abort if no file is found.

        logging.info(f"Processing input file: '{input_file}'")

        try:
            with open(input_file, "r") as f:
                user_input = json.load(f)
            page_urls = user_input.get("ConfluencePageURLs", [])
            if not page_urls:
                logging.error(
                    f"ERROR: No 'ConfluencePageURLs' found in '{input_file}'. "
                    "Aborting."
                )
                return
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(
                f"ERROR: Failed to read or parse JSON file '{input_file}'. "
                f"Details: {e}"
            )
            return

        for url in page_urls:
            self.process_page_hierarchy(url)

        self._save_results()
        logging.info("\n--- Script Finished ---")

    def process_page_hierarchy(self, root_page_url: str) -> None:
        """
        Processes a root Confluence page and all of its descendants.

        Args:
            root_page_url (str): The URL of the top-level page to start from.
        """
        logging.info(f"\nProcessing hierarchy starting from: {root_page_url}")
        root_page_id = self.confluence.get_page_id_from_url(root_page_url)
        if not root_page_id:
            logging.error(f"Could not find page ID for URL: {root_page_url}. Skipping.")
            return

        all_page_ids = [root_page_id] + self.confluence.get_all_descendants(
            root_page_id
        )
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        all_tasks = self._collect_tasks(all_page_ids)
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return

        logging.info(f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing...")
        self._process_tasks(all_tasks)

    def _collect_tasks(self, page_ids: List[str]) -> List[ConfluenceTask]:
        """Collects all tasks from a list of Confluence page IDs."""
        tasks: List[ConfluenceTask] = []
        for page_id in page_ids:
            page_details = self.confluence.get_page_by_id(
                page_id, expand="body.storage,version"
            )
            if page_details:
                tasks.extend(self.confluence.get_tasks_from_page(page_details))
        return tasks

    def _process_tasks(self, tasks: List[ConfluenceTask]) -> None:
        """
        Processes a list of tasks, creates Jira issues, and tracks results.
        """
        tasks_to_update_on_pages: Dict[str, List] = {}

        for task in tasks:
            logging.info(
                f"\nProcessing task: '{task.task_summary}' from page ID: "
                f"{task.confluence_page_id}"
            )

            # Find the parent Work Package on the same page as the task.
            closest_wp = self.issue_finder.find_issue_on_page(
                task.confluence_page_id, config.PARENT_ISSUES_TYPE_ID
            )

            if not closest_wp:
                self.results.append(
                    AutomationResult(task, "Skipped - No Work Package found")
                )
                continue

            closest_wp_key = closest_wp["key"]
            new_issue = self.jira.create_issue(task, closest_wp_key)

            if new_issue and new_issue.get("key"):
                new_key = new_issue["key"]

                # Handle task status logic.
                if task.status == "complete":
                    target_status = config.JIRA_TARGET_STATUSES["completed_task"]
                    self.jira.transition_issue(new_key, target_status)
                    self.results.append(
                        AutomationResult(
                            task,
                            "Success - Completed Task Created",
                            new_key,
                            closest_wp_key,
                        )
                    )
                else:
                    # For new, incomplete tasks in a non-production environment.
                    if not config.PRODUCTION_MODE:
                        target_status = config.JIRA_TARGET_STATUSES["new_task_dev"]
                        self.jira.transition_issue(new_key, target_status)
                    self.results.append(
                        AutomationResult(task, "Success", new_key, closest_wp_key)
                    )

                # Group the successful mappings by page ID for batch updates.
                tasks_to_update_on_pages.setdefault(
                    task.confluence_page_id, []
                ).append(
                    {"confluence_task_id": task.confluence_task_id, "jira_key": new_key}
                )
            else:
                self.results.append(
                    AutomationResult(
                        task,
                        "Failed - Jira task creation",
                        linked_work_package=closest_wp_key,
                    )
                )

        if tasks_to_update_on_pages:
            logging.info(
                "\nAll Jira tasks processed. Now updating Confluence pages..."
            )
            for page_id, mappings in tasks_to_update_on_pages.items():
                self.confluence.update_page_with_jira_links(page_id, mappings)

    def _save_results(self) -> None:
        """Saves the accumulated automation results to a timestamped JSON file."""
        if not self.results:
            logging.info("No actionable tasks were found. No results file generated.")
            return

        output_dir = config.OUTPUT_DIRECTORY
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(output_dir, f"automation_results_{timestamp}.json")

        # Convert result objects to a list of dictionaries for JSON serialization.
        results_data = [res.to_dict() for res in self.results]

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False, indent=4)

        logging.info(f"Results have been saved to '{file_path}'")


if __name__ == "__main__":
    # 1. Initialize raw API clients from configuration.
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

    # 4. Instantiate the specialized finder service.
    issue_finder = IssueFinderService(safe_confluence_api, safe_jira_api)

    # 5. Inject all services into the orchestrator and run it.
    sync_task_orchestrator = SyncTaskOrchestrator(confluence_service, jira_service, issue_finder)
    sync_task_orchestrator.run()
