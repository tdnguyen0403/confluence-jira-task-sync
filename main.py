import logging
import os
import pandas as pd
from typing import List, Dict
import warnings
from datetime import datetime

from atlassian import Confluence, Jira
import requests

import config
from models.data_models import AutomationResult, ConfluenceTask
from interfaces.api_service_interface import ApiServiceInterface
from services.confluence_service import ConfluenceService
from services.jira_service import JiraService
from services.issue_finder_service import IssueFinderService
from api.safe_jira_api import SafeJiraApi
from api.safe_confluence_api import SafeConfluenceApi
from utils.logging_config import setup_logging

warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

class AutomationOrchestrator:
    """Orchestrates the automation by depending on service interfaces."""

    def __init__(self, confluence_service: ApiServiceInterface, jira_service: ApiServiceInterface, issue_finder: IssueFinderService):
        self.confluence = confluence_service
        self.jira = jira_service
        self.issue_finder = issue_finder
        self.results: List[AutomationResult] = []

    def run(self, input_file: str = "input.xlsx"):
        setup_logging("logs", "automation_run")
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        try:
            input_df = pd.read_excel(input_file)
        except FileNotFoundError:
            logging.error(f"ERROR: Input file not found at '{input_file}'. Aborting.")
            return

        for _, row in input_df.iterrows():
            self.process_page_hierarchy(row["ConfluencePageURL"])

        self._save_results()
        logging.info("\n--- Script Finished ---")

    def process_page_hierarchy(self, root_page_url: str):
        logging.info(f"\nProcessing hierarchy starting from: {root_page_url}")
        root_page_id = self.confluence.get_page_id_from_url(root_page_url)
        if not root_page_id:
            logging.error(f"Could not find page ID for URL: {root_page_url}. Skipping.")
            return

        all_page_ids = [root_page_id] + self.confluence.get_all_descendants(root_page_id)
        logging.info(f"Found {len(all_page_ids)} total page(s) to scan.")
        
        all_tasks = self._collect_tasks(all_page_ids)
        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return

        logging.info(f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing...")
        self._process_tasks(all_tasks)

    def _collect_tasks(self, page_ids: List[str]) -> List[ConfluenceTask]:
        tasks: List[ConfluenceTask] = []
        for page_id in page_ids:
            page_details = self.confluence.get_page_by_id(page_id, expand="body.storage,version")
            if page_details:
                tasks.extend(self.confluence.get_tasks_from_page(page_details))
        return tasks
        
    def _process_tasks(self, tasks: List[ConfluenceTask]):
        tasks_to_update_on_pages: Dict[str, List] = {}
        for task in tasks:
            logging.info(f"\nProcessing task: '{task.task_summary}' from page ID: {task.confluence_page_id}")
            
            closest_wp = self.issue_finder.find_issue_on_page(task.confluence_page_id, config.WORK_PACKAGE_ISSUE_TYPE_ID)
            
            if not closest_wp:
                self.results.append(AutomationResult(task, "Skipped - No Work Package found"))
                continue

            closest_wp_key = closest_wp["key"]
            issue_fields = self.jira.prepare_jira_task_fields(task, closest_wp_key)
            new_issue = self.jira.create_issue(issue_fields)

            if new_issue and new_issue.get("key"):
                new_key = new_issue["key"]
                self.jira.transition_issue(new_key, config.JIRA_TARGET_STATUS_NAME, config.JIRA_TRANSITION_ID_BACKLOG)
                self.results.append(AutomationResult(task, "Success", new_key, closest_wp_key))
                tasks_to_update_on_pages.setdefault(task.confluence_page_id, []).append({
                    "confluence_task_id": task.confluence_task_id, "jira_key": new_key
                })
            else:
                self.results.append(AutomationResult(task, "Failed - Jira task creation", linked_work_package=closest_wp_key))

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            for page_id, mappings in tasks_to_update_on_pages.items():
                self.confluence.update_page_with_jira_links(page_id, mappings)

    def _save_results(self):
        if not self.results:
            logging.info("No actionable tasks were found. No results file generated.")
            return
        os.makedirs("output", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join("output", f"automation_results_{timestamp}.xlsx")
        results_df = pd.DataFrame([res.to_dict() for res in self.results])
        results_df.to_excel(file_path, index=False)
        logging.info(f"Results have been saved to '{file_path}'")

if __name__ == "__main__":
    # 1. Initialize raw clients
    jira_client = Jira(url=config.JIRA_URL, token=config.JIRA_API_TOKEN, cloud=False, verify_ssl=False)
    confluence_client = Confluence(url=config.CONFLUENCE_URL, token=config.CONFLUENCE_API_TOKEN, cloud=False, verify_ssl=False)

    # 2. Instantiate the low-level API handlers
    safe_jira_api = SafeJiraApi(jira_client)
    safe_confluence_api = SafeConfluenceApi(confluence_client)
    
    # 3. Instantiate the high-level service implementations
    jira_service = JiraService(safe_jira_api)
    confluence_service = ConfluenceService(safe_confluence_api)
    
    # 4. Instantiate the specialized finder service
    issue_finder = IssueFinderService(safe_confluence_api, safe_jira_api)

    # 5. Inject all services into the orchestrator
    orchestrator = AutomationOrchestrator(confluence_service, jira_service, issue_finder)
    orchestrator.run()