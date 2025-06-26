import logging
import re
import uuid
from typing import Optional, Dict, Any, List

import requests
from atlassian import Confluence
from bs4 import BeautifulSoup

import config
from models.data_models import ConfluenceTask

class SafeConfluenceApi:
    """A resilient, low-level service for all Confluence operations."""
    def __init__(self, confluence_client: Confluence):
        self.client = confluence_client
        self.base_url = config.CONFLUENCE_URL.rstrip('/')
        self.headers = {"Authorization": f"Bearer {config.CONFLUENCE_API_TOKEN}", "Content-Type": "application/json"}

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Extracts the Confluence page ID from either a standard long URL or a short link.
        This method uses requests directly as it's a utility for URL resolution.
        """
        # Check for a standard long URL first
        long_url_match = re.search(r'/pages/(\d+)', url)
        if long_url_match:
            return long_url_match.group(1)

        # If not, assume it's a short URL and resolve it
        logging.info(f"  Attempting to resolve short URL: {url}")
        try:
            response = requests.head(url, headers=self.headers, allow_redirects=True, timeout=15, verify=False)
            response.raise_for_status()
            final_url = response.url
            logging.info(f"  Short URL resolved to: {final_url}")
            
            resolved_match = re.search(r'/pages/(\d+)', final_url)
            if resolved_match:
                return resolved_match.group(1)
            
            logging.error(f"  ERROR: Could not extract page ID from the final resolved URL: {final_url}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"  ERROR: Could not resolve the short URL '{url}'. Details: {e}")
            return None

    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        try:
            return self.client.get_page_by_id(page_id, **kwargs)
        except Exception as e:
            logging.warning(f"Library get_page_by_id for '{page_id}' failed. Falling back. Error: {e}")
            return self._fallback_get_page_by_id(page_id, **kwargs)

    def _fallback_get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        url = f"{self.base_url}/rest/api/content/{page_id}"
        try:
            response = requests.get(url, headers=self.headers, params=params, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_page_by_id for '{page_id}' failed. Error: {e}")
            return None

    def get_page_child_by_type(self, page_id: str, type: str = "page") -> List[Dict[str, Any]]:
        try:
            return self.client.get_page_child_by_type(page_id, type=type)
        except Exception as e:
            logging.warning(f"Library get_page_child_by_type for '{page_id}' failed. Falling back. Error: {e}")
            return self._fallback_get_page_child_by_type(page_id, type)

    def _fallback_get_page_child_by_type(self, page_id: str, type: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/content/{page_id}/child/{type}"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_page_child_by_type for '{page_id}' failed. Error: {e}")
            return []

    def update_page(self, page_id: str, title: str, body: str, **kwargs) -> bool:
        try:
            self.client.update_page(page_id=page_id, title=title, body=body)
            logging.info(f"  Successfully updated page {page_id} via library call.")
            return True
        except Exception as e:
            logging.warning(f"Library update_page for '{page_id}' failed. Falling back. Error: {e}")
            return self._fallback_update_page(page_id, title, body, **kwargs)

    def _fallback_update_page(self, page_id: str, title: str, body: str, **kwargs) -> bool:
        url = f"{self.base_url}/rest/api/content/{page_id}"
        current_page = self.get_page_by_id(page_id, expand="version")
        if not current_page:
            return False
            
        new_version = current_page["version"]["number"] + 1
        payload = {
            "version": {"number": new_version}, "type": "page", "title": title,
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        try:
            response = requests.put(url, headers=self.headers, json=payload, verify=False, timeout=20)
            response.raise_for_status()
            logging.info(f"  Successfully updated page {page_id} via REST call.")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback update_page for '{page_id}' failed. Error: {e}")
            return False

    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        try:
            return self.client.create_page(**kwargs)
        except Exception as e:
            logging.warning(f"Library create_page failed. Falling back. Error: {e}")
            return self._fallback_create_page(**kwargs)

    def _fallback_create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/content"
        payload = {
            "type": "page", "title": kwargs.get("title"), "space": {"key": kwargs.get("space")},
            "body": {"storage": {"value": kwargs.get("body"), "representation": "storage"}},
            "ancestors": [{"id": kwargs.get("parent_id")}] if kwargs.get("parent_id") else []
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload, verify=False, timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback create_page for title '{kwargs.get('title')}' failed. Error: {e}")
            return None

    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            return self.client.get_user_details_by_username(username)
        except Exception as e:
            logging.warning(f"Library get_user_details_by_username failed. Falling back. Error: {e}")
            return self._fallback_get_user_details("username", username)
            
    def get_user_details_by_userkey(self, userkey: str) -> Optional[Dict[str, Any]]:
        try:
            return self.client.get_user_details_by_userkey(userkey)
        except Exception as e:
            logging.warning(f"Library get_user_details_by_userkey failed. Falling back. Error: {e}")
            return self._fallback_get_user_details("key", userkey)
            
    def _fallback_get_user_details(self, identifier_type: str, identifier_value: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/user?{identifier_type}={identifier_value}"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_user_details for '{identifier_value}' failed. Error: {e}")
            return None
            
    def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Recursively finds all descendant page IDs using safe API calls.
        This logic is now correctly placed in the low-level API handler.
        """
        all_ids = []
        # This now uses its own get_page_child_by_type method, which is resilient.
        child_pages = self.get_page_child_by_type(page_id, type="page")
        for child in child_pages:
            child_id = child['id']
            all_ids.append(child_id)
            # Recursive call to build the full list
            all_ids.extend(self.get_all_descendants(child_id))
        return all_ids
        
    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]:
        """Extracts all incomplete Confluence tasks from a page's HTML content."""
        tasks: List[ConfluenceTask] = []
        html_content = page_details.get("body", {}).get("storage", {}).get("value", "")
        if not html_content:
            return tasks

        soup = BeautifulSoup(html_content, "html.parser")
        
        for task_element in soup.find_all("ac:task"):
            if task_element.find_parent("ac:structured-macro", {"ac:name": lambda x: x in config.AGGREGATE_MACRO_NAMES}):
                continue

            if task_element.find("ac:task-status").get_text(strip=True) == "incomplete":
                parsed_task = self._parse_single_task(task_element, page_details)
                if parsed_task:
                    tasks.append(parsed_task)
        return tasks

    def _parse_single_task(self, task_element: Any, page_details: Dict) -> Optional[ConfluenceTask]:
        """Parses a single <ac:task> element into a ConfluenceTask object."""
        task_body = task_element.find("ac:task-body")
        task_id_tag = task_element.find("ac:task-id")
        if not (task_body and task_id_tag):
            return None
        
        assignee_name: Optional[str] = None
        if user_mention := task_element.find("ri:user"):
            if user_key := user_mention.get("ri:userkey"):
                # This call now correctly uses another method from the same low-level class
                user_details = self.get_user_details_by_userkey(user_key)
                if user_details:
                    assignee_name = user_details.get("username")

        due_date_tag = task_element.find("time")
        due_date = due_date_tag['datetime'] if due_date_tag and 'datetime' in due_date_tag.attrs else config.DEFAULT_DUE_DATE
        
        page_version = page_details.get("version", {})
        
        return ConfluenceTask(
            confluence_page_id=page_details.get("id", "N/A"),
            confluence_page_title=page_details.get("title", "N/A"),
            confluence_page_url=page_details.get("_links", {}).get("webui", ""),
            confluence_task_id=task_id_tag.get_text(strip=True),
            task_summary=' '.join(task_body.get_text(separator=' ').split()), # Corrected line
            assignee_name=assignee_name,
            due_date=due_date,
            original_page_version=int(page_version.get("number", -1)),
            original_page_version_by=page_version.get("by", {}).get("displayName", "Unknown"),
            original_page_version_when=page_version.get("when", "N/A")
            )
            
    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None:
        """
        Replaces completed Confluence tasks with Jira issue macros using a robust method.
        """
        page = self.get_page_by_id(page_id, expand="body.storage,version")
        if not page:
            logging.error(f"Could not retrieve page {page_id} to update.")
            return

        soup = BeautifulSoup(page["body"]["storage"]["value"], "html.parser")
        modified = False
        
        mapping_dict = {m['confluence_task_id']: m['jira_key'] for m in mappings}

        for task_list in soup.find_all("ac:task-list"):
            macros_to_insert = []
            tasks_to_remove = []

            for task in task_list.find_all("ac:task"):
                task_id_tag = task.find("ac:task-id")
                if task_id_tag and task_id_tag.string in mapping_dict:
                    jira_key = mapping_dict[task_id_tag.string]
                    jira_macro_html = self._generate_jira_macro_html(jira_key)
                    macros_to_insert.append(BeautifulSoup(jira_macro_html, "html.parser"))
                    tasks_to_remove.append(task)
                    modified = True
                    logging.info(f"  Prepared task '{task_id_tag.string}' for replacement with Jira macro for '{jira_key}'.")
            
            # Perform the DOM modifications after iterating
            for task in tasks_to_remove:
                task.decompose()
            
            if macros_to_insert:
                # Insert the new macros after the task list they came from
                for macro_soup in reversed(macros_to_insert):
                    task_list.insert_after(macro_soup)

        if modified:
            # Clean up any task lists that may now be empty
            for tl in soup.find_all("ac:task-list"):
                if not tl.find("ac:task"):
                    tl.decompose()
            
            self.update_page(page_id, page['title'], str(soup))
        else:
            logging.warning(f"  No tasks were successfully replaced on page {page_id}. Skipping page update.")

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        """Generates the Confluence storage format for a Jira macro."""
        macro_id = str(uuid.uuid4())
        return (
            f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{macro_id}">'
            f'<ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>'
            f'<ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>'
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f'</ac:structured-macro></p>'
        )
