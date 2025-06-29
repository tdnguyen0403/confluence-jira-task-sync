"""
Provides a resilient, low-level API wrapper for Confluence operations.

This module contains the SafeConfluenceApi class, which is designed to
interact with the Confluence API in a fault-tolerant way. It uses the
atlassian-python-api library as its primary client but implements custom
fallback mechanisms using direct REST API calls with `requests` for critical
operations. This ensures that the application can continue to function even
if the primary library encounters an issue.

The class handles various operations, including fetching and updating pages,
resolving page URLs, finding tasks within page content, and updating pages
with links to Jira issues.
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

import requests
from atlassian import Confluence
from bs4 import BeautifulSoup

# Local application imports
from src.config import config
from src.models.data_models import ConfluenceTask
from src.utils.context_extractor import get_task_context

# Configure logging for this module
logger = logging.getLogger(__name__)


class SafeConfluenceApi:
    """
    A resilient, low-level service for all Confluence operations.

    This class provides a safe wrapper around the Confluence client, with
    built-in fallbacks to raw REST API calls for increased reliability.

    Attributes:
        client (Confluence): The primary `atlassian-python-api` client.
        base_url (str): The base URL for the Confluence instance.
        headers (Dict[str, str]): The authorization headers for direct
                                  REST API calls.
    """

    def __init__(self, confluence_client: Confluence):
        """
        Initializes the SafeConfluenceApi.

        Args:
            confluence_client (Confluence): An authenticated instance of the
                                            atlassian-python-api Confluence
                                            client.
        """
        self.client = confluence_client
        self.base_url = config.CONFLUENCE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {config.CONFLUENCE_API_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Extracts the Confluence page ID from a standard or short URL.

        This utility method first attempts to parse the ID from a standard
        long-form URL. If that fails, it resolves the URL (assuming it's a
        short link) by making a HEAD request and then parses the ID from the
        final resolved URL.

        Args:
            url (str): The Confluence page URL (long or short form).

        Returns:
            Optional[str]: The extracted page ID, or None if it cannot be
                           resolved or found.
        """
        # First, check for a standard long URL format.
        long_url_match = re.search(r"/pages/(\d+)", url)
        if long_url_match:
            return long_url_match.group(1)

        # If not found, assume it's a short URL and try to resolve it.
        logger.info(f"Attempting to resolve short URL: {url}")
        try:
            # Use a HEAD request for efficiency as we only need the final URL.
            response = requests.head(
                url,
                headers=self.headers,
                allow_redirects=True,
                timeout=15,
                verify=False,
            )
            response.raise_for_status()
            final_url = response.url
            logger.info(f"Short URL resolved to: {final_url}")

            resolved_match = re.search(r"/pages/(\d+)", final_url)
            if resolved_match:
                return resolved_match.group(1)

            logger.error(
                "Could not extract page ID from the final resolved URL: "
                f"{final_url}"
            )
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not resolve the short URL '{url}'. Details: {e}")
            return None

    def get_page_by_id(self, page_id: str,
                       **kwargs) -> Optional[Dict[str, Any]]:
        """
        Safely retrieves a Confluence page by its ID.

        Tries to fetch the page using the library client and falls back to a
        direct REST API call upon failure.

        Args:
            page_id (str): The ID of the Confluence page to retrieve.
            **kwargs: Additional parameters to pass to the API call, such as
                      `expand`.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the page data,
                                      or None if retrieval fails.
        """
        try:
            return self.client.get_page_by_id(page_id, **kwargs)
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while get page '{page_id}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_page_by_id(page_id, **kwargs)
        except Exception as e:
            logger.warning(
                f"Library call get_page_by_id for '{page_id}' failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_page_by_id(page_id, **kwargs)

    def _fallback_get_page_by_id(self, page_id: str,
                                 **kwargs) -> Optional[Dict[str, Any]]:
        """Fallback method to get a page by ID using a direct REST call."""
        params = {k: v for k, v in kwargs.items() if v is not None}
        url = f"{self.base_url}/rest/api/content/{page_id}"
        try:
            response = requests.get(
                url, headers=self.headers, params=params, verify=False, timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Fallback get_page_by_id for '{page_id}' failed. Error: {e}")
            return None

    def get_page_child_by_type(
        self, page_id: str, page_type: str = "page"
    ) -> List[Dict[str, Any]]:
        """
        Safely retrieves child pages of a specific type.

        Args:
            page_id (str): The ID of the parent page.
            page_type (str): The type of child to retrieve (e.g., 'page').

        Returns:
            List[Dict[str, Any]]: A list of child page objects.
        """
        try:
            return self.client.get_page_child_by_type(page_id, type=page_type)
        except Exception as e:
            logger.warning(
                f"Library get_page_child_by_type for '{page_id}' failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_page_child_by_type(page_id, page_type)

    def _fallback_get_page_child_by_type(
        self, page_id: str, page_type: str
    ) -> List[Dict[str, Any]]:
        """Fallback method to get child pages using a direct REST call."""
        url = f"{self.base_url}/rest/api/content/{page_id}/child/{page_type}"
        try:
            response = requests.get(
                url, headers=self.headers, verify=False, timeout=15
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Fallback get_page_child_by_type for '{page_id}' failed. "
                f"Error: {e}"
            )
            return []

    def update_page(self, page_id: str, title: str, body: str, **kwargs) -> bool:
        """
        Safely updates a Confluence page.

        Tries to update the page using the library client and falls back to a
        direct REST API call upon failure.

        Args:
            page_id (str): The ID of the page to update.
            title (str): The new title for the page.
            body (str): The new body content in Confluence storage format.
            **kwargs: Additional parameters, primarily for versioning in the
                      fallback.

        Returns:
            bool: True if the page was updated successfully, False otherwise.
        """
        try:
            self.client.update_page(page_id=page_id, title=title, body=body)
            logger.info(f"Successfully updated page {page_id} via library call.")
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while update page '{page_id}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_update_page(page_id, **kwargs)
        except Exception as e:
            logger.warning(
                f"Library update_page for '{page_id}' failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_update_page(page_id, title, body, **kwargs)

    def _fallback_update_page(self, page_id: str, title: str, body: str,
                              **kwargs) -> bool:
        """Fallback method to update a page using a direct REST call."""
        url = f"{self.base_url}/rest/api/content/{page_id}"
        current_page = self.get_page_by_id(page_id, expand="version")
        if not current_page:
            return False

        new_version = current_page["version"]["number"] + 1
        payload = {
            "version": {"number": new_version},
            "type": "page",
            "title": title,
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        try:
            response = requests.put(
                url, headers=self.headers, json=payload, verify=False, timeout=20
            )
            response.raise_for_status()
            logger.info(f"Successfully updated page {page_id} via REST call.")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Fallback update_page for '{page_id}' failed. Error: {e}")
            return False

    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Safely creates a new Confluence page.

        Args:
            **kwargs: Keyword arguments for page creation, such as `space`,
                      `title`, `body`, and `parent_id`.

        Returns:
            Optional[Dict[str, Any]]: The created page object, or None.
        """
        try:
            return self.client.create_page(**kwargs)
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while create page '{page_id}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_create_page(page_id, **kwargs)
        except Exception as e:
            logger.warning(f"Library create_page failed. Falling back. Error: {e}")
            return self._fallback_create_page(**kwargs)

    def _fallback_create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Fallback method to create a page using a direct REST call."""
        url = f"{self.base_url}/rest/api/content"
        payload = {
            "type": "page",
            "title": kwargs.get("title"),
            "space": {"key": kwargs.get("space")},
            "body": {
                "storage": {"value": kwargs.get("body"), "representation": "storage"}
            },
            "ancestors":
            [{"id": kwargs.get("parent_id")}] if kwargs.get("parent_id") else [],
        }
        try:
            response = requests.post(
                url, headers=self.headers, json=payload, verify=False, timeout=20
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Fallback create_page for title '{kwargs.get('title')}' failed. "
                f"Error: {e}"
            )
            return None

    def get_user_details_by_username(
        self, username: str
    ) -> Optional[Dict[str, Any]]:
        """Safely gets user details by username, with a fallback."""
        try:
            return self.client.get_user_details_by_username(username)
        except Exception as e:
            logger.warning(
                "Library get_user_details_by_username failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_user_details("username", username)

    def get_user_details_by_userkey(self, userkey: str) -> Optional[Dict[str, Any]]:
        """Safely gets user details by user key, with a fallback."""
        try:
            return self.client.get_user_details_by_userkey(userkey)
        except Exception as e:
            logger.warning(
                "Library get_user_details_by_userkey failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_user_details("key", userkey)

    def _fallback_get_user_details(
        self, identifier_type: str, identifier_value: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback for getting user details via direct REST call."""
        url = f"{self.base_url}/rest/api/user?{identifier_type}={identifier_value}"
        try:
            response = requests.get(
                url, headers=self.headers, verify=False, timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Fallback get_user_details for '{identifier_value}' failed. "
                f"Error: {e}"
            )
            return None

    def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Recursively finds all descendant page IDs using safe API calls.

        This method builds a complete list of all child pages, and their
        children, down the entire hierarchy from the starting page ID.

        Args:
            page_id (str): The starting page ID.

        Returns:
            List[str]: A flat list of all descendant page IDs.
        """
        all_ids = []
        # This uses its own resilient get_page_child_by_type method.
        child_pages = self.get_page_child_by_type(page_id, page_type="page")
        for child in child_pages:
            child_id = child["id"]
            all_ids.append(child_id)
            # Recursive call to build the full list of descendants.
            all_ids.extend(self.get_all_descendants(child_id))
        return all_ids

    def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        """
        Extracts all Confluence tasks from a page's HTML content.

        Parses the 'storage' format of the page body to find all task list
        items (`<ac:task>`), ignoring any tasks within specific aggregation
        macros defined in the config.

        Args:
            page_details (Dict[str, Any]): The dictionary containing the full
                                           details of a Confluence page,
                                           including the body content.

        Returns:
            List[ConfluenceTask]: A list of `ConfluenceTask` objects found on
                                  the page.
        """
        tasks: List[ConfluenceTask] = []
        html_content = page_details.get("body", {}).get("storage", {}).get("value", "")
        if not html_content:
            return tasks

        soup = BeautifulSoup(html_content, "html.parser")

        for task_element in soup.find_all("ac:task"):
            # Skip tasks that are inside an aggregation macro
            if task_element.find_parent(
                "ac:structured-macro",
                {"ac:name": lambda x: x in config.AGGREGATION_CONFLUENCE_MACRO},
            ):
                continue

            # Parse the task element into a structured object
            parsed_task = self._parse_single_task(task_element, page_details)
            if parsed_task:
                tasks.append(parsed_task)
        return tasks

    def _parse_single_task(
        self, task_element: Any, page_details: Dict[str, Any]
    ) -> Optional[ConfluenceTask]:
        """
        Parses a single <ac:task> element into a ConfluenceTask object.

        This helper method extracts all relevant details from a task element,
        including its content, status, assignee, and due date.

        Args:
            task_element (Any): The BeautifulSoup tag for an `<ac:task>`.
            page_details (Dict[str, Any]): The details of the parent page.

        Returns:
            Optional[ConfluenceTask]: A populated `ConfluenceTask` object, or
                                      None if the task element is malformed.
        """
        task_body = task_element.find("ac:task-body")
        task_id_tag = task_element.find("ac:task-id")
        task_status_tag = task_element.find("ac:task-status")

        if not (task_body and task_id_tag and task_status_tag):
            return None

        assignee_name: Optional[str] = None
        if user_mention := task_element.find("ri:user"):
            if user_key := user_mention.get("ri:userkey"):
                user_details = self.get_user_details_by_userkey(user_key)
                if user_details:
                    assignee_name = user_details.get("username")

        due_date_tag = task_element.find("time")
        due_date = (
            due_date_tag["datetime"]
            if due_date_tag and "datetime" in due_date_tag.attrs
            else config.DEFAULT_DUE_DATE
        )

        page_version = page_details.get("version", {})
        context = get_task_context(task_element)

        # Create a modifiable copy to avoid altering the main soup object.
        task_body_copy = BeautifulSoup(str(task_body), "html.parser")

        # Remove nested task lists to get only the parent task's summary.
        for nested_task_list in task_body_copy.find_all("ac:task-list"):
            nested_task_list.decompose()

        # Clean the text to get a concise summary.
        task_summary = " ".join(
            task_body_copy.get_text(separator=" ").split()
        ).strip()

        return ConfluenceTask(
            confluence_page_id=page_details.get("id", "N/A"),
            confluence_page_title=page_details.get("title", "N/A"),
            confluence_page_url=page_details.get("_links", {}).get("webui", ""),
            confluence_task_id=task_id_tag.get_text(strip=True),
            task_summary=task_summary,
            status=task_status_tag.get_text(strip=True),
            assignee_name=assignee_name,
            due_date=due_date,
            original_page_version=int(page_version.get("number", -1)),
            original_page_version_by=page_version.get("by", {}).get(
                "displayName", "Unknown"
            ),
            original_page_version_when=page_version.get("when", "N/A"),
            context=context,
        )

    def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> None:
        """
        Replaces completed Confluence tasks with Jira issue macros.

        This method retrieves a page, finds tasks based on the provided
        mappings, removes the original task element, and inserts a Jira
        macro in its place.

        Args:
            page_id (str): The ID of the Confluence page to update.
            mappings (List[Dict[str, str]]): A list of dictionaries, each
                mapping a `confluence_task_id` to a `jira_key`.
        """
        page = self.get_page_by_id(page_id, expand="body.storage,version")
        if not page:
            logger.error(f"Could not retrieve page {page_id} to update.")
            return

        soup = BeautifulSoup(page["body"]["storage"]["value"], "html.parser")
        modified = False

        mapping_dict = {m["confluence_task_id"]: m["jira_key"] for m in mappings}

        for task_list in soup.find_all("ac:task-list"):
            macros_to_insert = []
            tasks_to_remove = []

            for task in task_list.find_all("ac:task"):
                task_id_tag = task.find("ac:task-id")
                if task_id_tag and task_id_tag.string in mapping_dict:
                    jira_key = mapping_dict[task_id_tag.string]
                    jira_macro_html = self._generate_jira_macro_html(jira_key)
                    macros_to_insert.append(
                        BeautifulSoup(jira_macro_html, "html.parser")
                    )
                    tasks_to_remove.append(task)
                    modified = True
                    logger.info(
                        f"Prepared task '{task_id_tag.string}' for replacement "
                        f"with Jira macro for '{jira_key}'."
                    )

            # Perform the DOM modifications after iterating to avoid issues.
            for task in tasks_to_remove:
                task.decompose()

            if macros_to_insert:
                # Insert new macros after the task list they came from.
                for macro_soup in reversed(macros_to_insert):
                    task_list.insert_after(macro_soup)

        if modified:
            # Clean up any task lists that are now empty.
            for tl in soup.find_all("ac:task-list"):
                if not tl.find("ac:task"):
                    tl.decompose()

            self.update_page(page_id, page["title"], str(soup))
        else:
            logger.warning(
                f"No tasks were replaced on page {page_id}. Skipping update."
            )

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        """
        Generates the Confluence storage format for a Jira issue macro.

        Args:
            jira_key (str): The key of the Jira issue (e.g., 'PROJ-123').

        Returns:
            str: A string containing the HTML for the Confluence macro.
        """
        macro_id = str(uuid.uuid4())
        return (
            f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" '
            f'ac:macro-id="{macro_id}">'
            f'<ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>'
            f'<ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>'
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f"</ac:structured-macro></p>"
        )
