# undo_automation.py - Corrected to parse the results file with the right column names.

import datetime
import logging
import os
import sys
import warnings
from typing import Optional, Set, Dict, Tuple

import pandas as pd
import requests
from atlassian import Confluence, Jira

import config
from safe_api import SafeJiraService, SafeConfluenceService

# --- Suppress SSL Warnings ---
urllib3 = requests.packages.urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)


class UndoOrchestrator:
    """Orchestrates the undo process using safe API services."""

    def __init__(self, safe_confluence: SafeConfluenceService, safe_jira: SafeJiraService):
        self.confluence = safe_confluence
        self.jira = safe_jira
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def run(self, results_file_override: Optional[str] = None):
        """Executes the main undo logic."""
        self._setup_logging()
        logging.info("\n--- Starting Undo Automation Script ---")

        results_df = self._load_results_file(results_file_override)
        if results_df is None or results_df.empty:
            logging.warning("Results file is empty or could not be read. No actions to perform.")
            return

        jira_keys, pages_to_rollback = self._parse_results(results_df)

        self._transition_jira_tasks(jira_keys)
        self._rollback_confluence_pages(pages_to_rollback)

        logging.info("\n--- Undo Automation Script Finished ---")
        logging.info("Review the log file and Confluence/Jira to confirm changes.")

    def _transition_jira_tasks(self, jira_keys: Set[str]):
        """Transitions all identified Jira tasks using the safe service."""
        logging.info(f"\n--- Phase 1: Transitioning {len(jira_keys)} Jira Tasks ---")
        if not jira_keys:
            logging.info("  No Jira tasks to transition.")
            return
        for key in sorted(list(jira_keys)):
            self.jira.transition_issue(key, config.JIRA_TARGET_STATUS_NAME, "11")

    def _rollback_confluence_pages(self, pages: Dict[str, int]):
        """Rolls back all identified Confluence pages using the safe service."""
        logging.info(f"\n--- Phase 2: Rolling back {len(pages)} Confluence Pages ---")
        if not pages:
            logging.info("  No Confluence pages to roll back.")
            return
        
        logging.warning("NOTE: This operation reverts pages to their state *before* the script ran. Any other changes made since will also be undone.")
        for page_id, version in sorted(pages.items()):
            logging.info(f"Attempting to roll back page {page_id} to version {version}")
            page_content = self.confluence.get_page_by_id(page_id, version=version, expand="body.storage")
            current_page = self.confluence.get_page_by_id(page_id)
            if page_content and current_page:
                self.confluence.update_page(
                    page_id=page_id,
                    title=current_page['title'],
                    body=page_content['body']['storage']['value']
                )
            else:
                logging.error(f"  Failed to get content for page '{page_id}' version {version}.")

    def _load_results_file(self, file_override: Optional[str]) -> Optional[pd.DataFrame]:
        """Finds the latest or uses the specified results file."""
        path = file_override if file_override else self._find_latest_results_file("output")
        
        if not path or not os.path.exists(path):
            logging.error(f"ERROR: Results file not found at '{path}'. Aborting.")
            return None

        logging.info(f"Using results file: '{path}'")
        try:
            return pd.read_excel(path)
        except Exception as e:
            logging.error(f"ERROR: Failed to read Excel file '{path}'. Details: {repr(e)}")
            return None

    def _find_latest_results_file(self, folder: str) -> Optional[str]:
        """Finds the most recent automation results file in a folder."""
        latest_file = None
        latest_ts = None
        if not os.path.exists(folder):
            logging.error(f"Output folder '{folder}' does not exist.")
            return None
            
        for filename in os.listdir(folder):
            if filename.startswith("automation_results_") and filename.endswith(".xlsx"):
                try:
                    ts_str = filename.replace("automation_results_", "").replace(".xlsx", "")
                    file_ts = datetime.datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    if not latest_ts or file_ts > latest_ts:
                        latest_ts = file_ts
                        latest_file = os.path.join(folder, filename)
                except ValueError:
                    continue
        return latest_file

    def _parse_results(self, df: pd.DataFrame) -> Tuple[Set[str], Dict[str, int]]:
        """
        CORRECTED: Parses the DataFrame to extract items to be undone,
        using the actual column names generated by main.py.
        """
        jira_keys = set()
        pages = {}
        
        # CORRECTED: These are the actual column names generated by main.py
        required_cols = ["Status", "New Jira Task Key", "confluence_page_id", "original_page_version"]
        if not all(col in df.columns for col in required_cols):
            logging.error(f"Results file is missing one of the required columns: {required_cols}")
            logging.error(f"Available columns are: {list(df.columns)}")
            return jira_keys, pages

        for _, row in df.iterrows():
            if row.get("Status") == "Success":
                # Use the correct column names to access the data
                if pd.notna(row.get("New Jira Task Key")):
                    jira_keys.add(row["New Jira Task Key"])
                
                if pd.notna(row.get("confluence_page_id")) and pd.notna(row.get("original_page_version")):
                    page_id = str(int(row["confluence_page_id"]))
                    version = int(row["original_page_version"])
                    if page_id not in pages:
                        pages[page_id] = version
                        
        return jira_keys, pages

    def _setup_logging(self):
        log_dir = "logs_undo"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"undo_run_{self.timestamp}.log")
        
        root_logger = logging.getLogger()
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
            
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
                            handlers=[logging.FileHandler(log_file, 'w', 'utf-8'), logging.StreamHandler(sys.stdout)])


if __name__ == "__main__":
    # Initialize raw clients
    jira_client_raw = Jira(url=config.JIRA_URL, token=config.JIRA_API_TOKEN, cloud=False, verify_ssl=False)
    confluence_client_raw = Confluence(url=config.CONFLUENCE_URL, token=config.CONFLUENCE_API_TOKEN, cloud=False, verify_ssl=False)

    # Wrap clients in Safe Services
    safe_jira = SafeJiraService(jira_client_raw)
    safe_confluence = SafeConfluenceService(confluence_client_raw)

    # Instantiate and Run Orchestrator
    orchestrator = UndoOrchestrator(safe_confluence, safe_jira)
    orchestrator.run()
