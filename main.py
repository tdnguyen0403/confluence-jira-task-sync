# main.py - Corrected to properly generate the Jira Macro structure on update.

import datetime
import logging
import os
import re
import sys
import uuid
import warnings
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from atlassian import Confluence, Jira
from bs4 import BeautifulSoup

import config
from safe_api import SafeJiraService, SafeConfluenceService

# --- Suppress SSL Warnings ---
urllib3 = requests.packages.urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)


class AutomationOrchestrator:
    """Orchestrates the end-to-end automation process using safe API services."""

    def __init__(self, safe_confluence: SafeConfluenceService, safe_jira: SafeJiraService):
        self.confluence = safe_confluence
        self.jira = safe_jira
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results: List[Dict[str, Any]] = []

    def run(self):
        """Executes the main automation logic."""
        self._setup_logging()
        logging.info("--- Starting Jira/Confluence Automation Script ---")

        input_df = self._load_input_file()
        if input_df is None: return

        for _, row in input_df.iterrows():
            main_page_url = row["ConfluencePageURL"]
            self.process_page_hierarchy(main_page_url)

        self._save_results()
        logging.info("\n--- Script Finished ---")

    def process_page_hierarchy(self, main_page_url: str):
        """Processes a single root page and all its descendants."""
        logging.info(f"\nProcessing hierarchy starting from: {main_page_url}")
        
        main_page_id = self.confluence.get_page_id_from_url(main_page_url)
        if not main_page_id: 
            logging.error(f"Could not determine page ID for URL: {main_page_url}. Skipping.")
            return

        main_wp = self._find_wp_on_single_page(main_page_id)
        fallback_assignee = self._get_fallback_assignee(main_wp)

        all_pages_to_scan = [main_page_id] + self._get_all_descendants(main_page_id)
        logging.info(f"  Found {len(all_pages_to_scan)} total page(s) to scan.")

        all_tasks = []
        for page_id in all_pages_to_scan:
            page_details = self.confluence.get_page_by_id(page_id, expand="body.storage,version")
            if page_details:
                all_tasks.extend(self._get_tasks_from_page(page_details, fallback_assignee))

        if not all_tasks:
            logging.info("No incomplete tasks found across all pages.")
            return

        logging.info(f"\nDiscovered {len(all_tasks)} incomplete tasks. Now processing...")
        tasks_to_update_on_pages: Dict[str, List] = {}
        for task in all_tasks:
            self._process_single_task(task, tasks_to_update_on_pages)

        if tasks_to_update_on_pages:
            logging.info("\nAll Jira tasks processed. Now updating Confluence pages...")
            for page_id, mappings in tasks_to_update_on_pages.items():
                self._update_page_with_jira_links(page_id, mappings)

    def _get_all_descendants(self, page_id: str) -> List[str]:
        """
        CORRECTED: Recursively finds all descendant pages (children, grandchildren, etc.)
        of a given page.
        """
        all_ids = []
        # Get the direct children of the current page
        child_pages = self.confluence.get_page_child_by_type(page_id, type="page")
        
        # Iterate through the direct children
        for child in child_pages:
            child_id = child['id']
            all_ids.append(child_id)
            # For each child, recursively call this function to get its descendants
            all_ids.extend(self._get_all_descendants(child_id))
            
        return all_ids

    def _process_single_task(self, task_data: Dict, tasks_to_update: Dict):
        page_id = task_data["confluence_page_id"]
        logging.info(f"\nProcessing task: '{task_data['task_summary']}' from page ID: {page_id}")
        
        closest_wp = self._get_closest_ancestor_work_package(page_id)
        if not closest_wp:
            self._log_result(task_data, "Skipped - No closest Work Package found")
            return

        closest_wp_key = closest_wp["key"]
        final_assignee = task_data["assignee_name"] or self._get_fallback_assignee(closest_wp)
        
        issue_fields = self._prepare_jira_task_fields(task_data, closest_wp_key, final_assignee)
        new_issue = self.jira.issue_create(fields=issue_fields)

        if new_issue and new_issue.get("key"):
            new_key = new_issue["key"]
            self.jira.transition_issue(new_key, config.JIRA_TARGET_STATUS_NAME, "11")
            self._log_result(task_data, "Success", new_key, closest_wp_key)
            tasks_to_update.setdefault(page_id, []).append({
                "confluence_task_id": task_data["confluence_task_id"], "jira_key": new_key,
            })
        else:
            self._log_result(task_data, "Failed - Jira task creation", linked_wp=closest_wp_key)

    def _find_wp_on_single_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        page_content = self.confluence.get_page_by_id(page_id, expand="body.storage")
        if not (page_content and 'body' in page_content and 'storage' in page_content['body']): return None
        soup = BeautifulSoup(page_content["body"]["storage"]["value"], "html.parser")
        for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            if macro.find_parent("ac:structured-macro", {"ac:name": lambda x: x in config.AGGREGATE_MACRO_NAMES}): continue
            key_param = macro.find("ac:parameter", {"ac:name": "key"})
            if key_param:
                issue_key = key_param.get_text()
                jira_issue = self.jira.get_issue(issue_key, fields="issuetype")
                if jira_issue and jira_issue.get("fields", {}).get("issuetype", {}).get("id") == config.WORK_PACKAGE_ISSUE_TYPE_ID:
                    return self.jira.get_issue(issue_key, fields="issuetype,assignee,reporter")
        return None

    def _get_closest_ancestor_work_package(self, page_id: str) -> Optional[Dict[str, Any]]:
        page_info = self.confluence.get_page_by_id(page_id, expand="ancestors")
        if not page_info: return None
        for ancestor in reversed(page_info.get("ancestors", []) + [page_info]):
            if wp_issue := self._find_wp_on_single_page(ancestor["id"]): return wp_issue
        return None

    def _get_tasks_from_page(self, page_details: Dict, default_assignee: Optional[str]) -> List[Dict]:
        tasks = []
        html_content = page_details.get("body", {}).get("storage", {}).get("value", "")
        soup = BeautifulSoup(html_content, "html.parser")
        
        for task_element in soup.find_all("ac:task"):
            if task_element.find_parent("ac:structured-macro", {"ac:name": lambda x: x in config.AGGREGATE_MACRO_NAMES}):
                continue
            if task_element.find("ac:task-status").get_text() == "incomplete":
                parsed_task = self._parse_single_task(task_element, page_details, default_assignee)
                if parsed_task:
                    tasks.append(parsed_task)
        return tasks

    def _parse_single_task(self, task_element, page_details, default_assignee) -> Optional[Dict]:
        task_body = task_element.find("ac:task-body")
        task_id = task_element.find("ac:task-id")
        if not (task_body and task_id): return None
        
        assignee_name = default_assignee
        if user_mention := task_element.find("ri:user"):
            if user_key := user_mention.get("ri:userkey"):
                user_details = self.confluence.get_user_details_by_userkey(user_key)
                if user_details: assignee_name = user_details.get("username", default_assignee)

        due_date_tag = task_element.find("time")
        due_date = due_date_tag['datetime'] if due_date_tag and 'datetime' in due_date_tag.attrs else config.DEFAULT_DUE_DATE
        
        page_version = page_details.get("version", {})
        
        return {
            "confluence_page_id": page_details["id"], "confluence_page_title": page_details["title"],
            "confluence_page_url": page_details.get("_links", {}).get("webui"), "confluence_task_id": task_id.get_text(),
            "task_summary": task_body.get_text().strip(), "assignee_name": assignee_name, "due_date": due_date,
            "original_page_version": page_version.get("number", "N/A"), 
            "original_page_version_by": page_version.get("by", {}).get("displayName", "Unknown"),
            "original_page_version_when": page_version.get("when", "N/A")
        }

    def _update_page_with_jira_links(self, page_id: str, mappings: List[Dict]):
        """
        CORRECTED: Fetches a Confluence page, replaces specified task IDs with
        Jira macros by inserting the macro *after* the containing task list,
        and then updates the page.
        """
        page = self.confluence.get_page_by_id(page_id, expand="body.storage,version")
        if not page:
            logging.error(f"Could not retrieve page {page_id} to update.")
            return

        soup = BeautifulSoup(page["body"]["storage"]["value"], "html.parser")
        modified = False

        # A dictionary to look up Jira keys from Confluence task IDs
        mapping_dict = {m['confluence_task_id']: m['jira_key'] for m in mappings}

        # Find all task lists on the page to process them individually
        for task_list in soup.find_all("ac:task-list"):
            macros_to_insert_html = []
            
            # Find all tasks within this specific list
            for task in task_list.find_all("ac:task"):
                task_id_tag = task.find("ac:task-id")
                if task_id_tag and task_id_tag.string in mapping_dict:
                    jira_key = mapping_dict[task_id_tag.string]
                    
                    # Prepare the valid Jira macro XML
                    jira_macro_xml = (
                        f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">'
                        f'<ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>'
                        f'<ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>'
                        f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
                        f'</ac:structured-macro></p>'
                    )
                    macros_to_insert_html.append(jira_macro_xml)
                    
                    # Remove the original task element from the soup
                    task.decompose()
                    modified = True
                    logging.info(f"  Prepared task '{task_id_tag.string}' for replacement with Jira macro for '{jira_key}'.")

            # After checking all tasks in this list, insert the collected macros AFTER the list
            if macros_to_insert_html:
                full_insertion_soup = BeautifulSoup("".join(macros_to_insert_html), "html.parser")
                task_list.insert_after(full_insertion_soup)

        # After processing all task lists, clean up any that are now empty
        if modified:
            for tl in soup.find_all("ac:task-list"):
                if not tl.find("ac:task"): 
                    tl.decompose()
            
            self.confluence.update_page(page_id=page_id, title=page['title'], body=str(soup))
            logging.info(f"  Successfully sent update for page {page_id}.")
        else:
            logging.warning(f"  No tasks were successfully replaced on page {page_id}. Skipping update.")

    def _get_fallback_assignee(self, wp):
        if not wp: return None
        return wp.get("fields", {}).get("assignee", {}).get("name") or wp.get("fields", {}).get("reporter", {}).get("name")

    def _prepare_jira_task_fields(self, task_data, parent_key, assignee_name):
        desc = f"Source: [{task_data['confluence_page_title']}|{task_data['confluence_page_url']}]"
        fields = {
            "project": {"key": config.JIRA_PROJECT_KEY}, "summary": task_data['task_summary'],
            "issuetype": {"id": config.TASK_ISSUE_TYPE_ID}, "description": desc,
            "duedate": task_data['due_date'], config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key
        }
        if assignee_name: fields["assignee"] = {"name": assignee_name}
        return fields

    def _log_result(self, task_data, status, new_key=None, linked_wp=None):
        result_data = task_data.copy()
        result_data["Status"] = status
        result_data["New Jira Task Key"] = new_key
        result_data["Linked Work Package"] = linked_wp
        self.results.append(result_data)

    def _load_input_file(self):
        try: 
            return pd.read_excel("input.xlsx")
        except FileNotFoundError: 
            logging.error("ERROR: 'input.xlsx' not found. Please create the file with a 'ConfluencePageURL' column.")
            return None

    def _save_results(self):
        if self.results:
            os.makedirs("output", exist_ok=True)
            path = os.path.join("output", f"automation_results_{self.timestamp}.xlsx")
            pd.DataFrame(self.results).to_excel(path, index=False)
            logging.info(f"Results have been saved to '{path}'")
        else:
            logging.info("No actionable tasks were found. No results file generated.")

    def _setup_logging(self):
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"automation_run_{self.timestamp}.log")
        
        root_logger = logging.getLogger()
        # Clear existing handlers to avoid duplicate logs
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
            
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
                            handlers=[logging.FileHandler(log_file, 'w', 'utf-8'), logging.StreamHandler(sys.stdout)])
        logging.info(f"Logging to '{log_file}'")


if __name__ == "__main__":
    jira_client = Jira(url=config.JIRA_URL, token=config.JIRA_API_TOKEN, cloud=False, verify_ssl=False)
    confluence_client = Confluence(url=config.CONFLUENCE_URL, token=config.CONFLUENCE_API_TOKEN, cloud=False, verify_ssl=False)
    
    safe_jira = SafeJiraService(jira_client)
    safe_confluence = SafeConfluenceService(confluence_client)
    
    AutomationOrchestrator(safe_confluence, safe_jira).run()
