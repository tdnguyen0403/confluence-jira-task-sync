# main.py - Refactored to use the Safe API services exclusively

import datetime
import logging
import os
import re
import sys
import uuid
import warnings
from typing import Any, Dict, List, Optional

import pandas as pd
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
        """Wrapper for recursively getting all child page IDs."""
        child_pages = self.confluence.get_page_child_by_type(page_id, type="page")
        all_ids = []
        for child in child_pages:
            all_ids.append(child['id'])
            all_ids.extend(self._get_all_descendants(child['id']))
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
        soup = BeautifulSoup(page_details["content"], "html.parser")
        for task_element in soup.find_all("ac:task"):
            if task_element.find_parent("ac:structured-macro", {"ac:name": lambda x: x in config.AGGREGATE_MACRO_NAMES}): continue
            if task_element.find("ac:task-status").get_text() == "incomplete":
                tasks.append(self._parse_single_task(task_element, page_details, default_assignee))
        return [t for t in tasks if t]

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
        return {
            "confluence_page_id": page_details["id"], "confluence_page_title": page_details["title"],
            "confluence_page_url": page_details.get("_links", {}).get("webui"), "confluence_task_id": task_id.get_text(),
            "task_summary": task_body.get_text().strip(), "assignee_name": assignee_name, "due_date": due_date,
            "original_page_version": page_details["version"]["number"], "original_page_version_by": page_details["version"]["by"]["displayName"],
            "original_page_version_when": page_details["version"]["when"]
        }

    def _update_page_with_jira_links(self, page_id: str, mappings: List[Dict]):
        page = self.confluence.get_page_by_id(page_id, expand="body.storage,version")
        if not page: return
        soup = BeautifulSoup(page["body"]["storage"]["value"], "html.parser")
        for m in mappings:
            if task_id_tag := soup.find("ac:task-id", string=m['confluence_task_id']):
                if task_tag := task_id_tag.find_parent("ac:task"):
                    jira_macro_xml = f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}"><ac:parameter ac:name="key">{m["jira_key"]}</ac:parameter></ac:structured-macro></p>'
                    task_tag.replace_with(BeautifulSoup(jira_macro_xml, "html.parser").p)
        for tl in soup.find_all("ac:task-list"):
            if not tl.find("ac:task"): tl.decompose()
        self.confluence.update_page(page_id=page_id, title=page['title'], body=str(soup))
    
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
        self.results.append({**task_data, "Status": status, "New Jira Task Key": new_key, "Linked Work Package": linked_wp})
    def _load_input_file(self):
        try: return pd.read_excel("input.xlsx")
        except FileNotFoundError: logging.error("ERROR: 'input.xlsx' not found."); return None
    def _save_results(self):
        if self.results:
            os.makedirs("output", exist_ok=True)
            path = os.path.join("output", f"automation_results_{self.timestamp}.xlsx")
            pd.DataFrame(self.results).to_excel(path, index=False)
            logging.info(f"Results saved to '{path}'")
    def _setup_logging(self):
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"automation_run_{self.timestamp}.log")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
                            handlers=[logging.FileHandler(log_file, 'w', 'utf-8'), logging.StreamHandler(sys.stdout)])
        logging.info(f"Logging to '{log_file}'")

if __name__ == "__main__":
    jira_client = Jira(url=config.JIRA_URL, token=config.JIRA_API_TOKEN, cloud=False, verify_ssl=False)
    confluence_client = Confluence(url=config.CONFLUENCE_URL, token=config.CONFLUENCE_API_TOKEN, cloud=False, verify_ssl=False)
    safe_jira = SafeJiraService(jira_client)
    safe_confluence = SafeConfluenceService(confluence_client)
    AutomationOrchestrator(safe_confluence, safe_jira).run()
