"""
Provides a resilient, low-level API wrapper for Confluence operations.

This module contains the SafeConfluenceApi class, which is designed to
interact with the Confluence API in a fault-tolerant way. It uses the
asynchronous HTTPSHelper for all direct REST API calls, ensuring robustness
and high performance.

The class handles various operations, including fetching and updating pages,
resolving page URLs, finding tasks within page content, and updating pages
with links to Jira issues.
"""

import logging
import re
import uuid
import asyncio  # Required for concurrent operations like get_all_descendants_concurrently
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

# Local application imports
from src.config import config
from src.models.data_models import ConfluenceTask
from src.utils.context_extractor import get_task_context
from src.api.https_helper import HTTPSHelper  # Import the asynchronous HTTPSHelper

# Configure logging for this module
logger = logging.getLogger(__name__)


class SafeConfluenceApi:
    """
    A resilient, low-level service for all Confluence operations.

    This class provides a safe wrapper around the Confluence API, using
    HTTPSHelper for all network interactions to ensure asynchronous operation.

    Attributes:
        base_url (str): The base URL for the Confluence instance.
        https_helper (HTTPSHelper): An instance of the asynchronous HTTPSHelper.
        headers (Dict[str, str]): The authorization headers for direct
                                   REST API calls.
        jira_macro_server_name (str): The name of the Jira server for macros.
        jira_macro_server_id (str): The ID of the Jira server for macros.
    """

    def __init__(
        self,
        base_url: str,  # Pass base_url directly
        https_helper: HTTPSHelper,  # Inject HTTPSHelper
        jira_macro_server_name: str = config.JIRA_MACRO_SERVER_NAME,
        jira_macro_server_id: str = config.JIRA_MACRO_SERVER_ID,
    ):
        """
        Initializes the SafeConfluenceApi.

        Args:
            base_url (str): The base URL for the Confluence instance.
            https_helper (HTTPSHelper): An authenticated instance of the
                                        asynchronous HTTPSHelper client.
            jira_macro_server_name (str): The name of the Jira server for macros.
            jira_macro_server_id (str): The ID of the Jira server for macros.
        """
        self.base_url = config.CONFLUENCE_URL.rstrip("/")
        self.https_helper = https_helper
        # Construct the Authorization header directly using Bearer Token
        self.headers = {
            "Authorization": f"Bearer {config.CONFLUENCE_API_TOKEN}",  # Using config.CONFLUENCE_API_TOKEN directly
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.jira_macro_server_name = jira_macro_server_name
        self.jira_macro_server_id = jira_macro_server_id

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Extracts the Confluence page ID from a standard or short URL asynchronously.

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
        # First, check for a standard long URL format with pageId query param
        page_id_query_match = re.search(r"pageId=(\d+)", url)
        if page_id_query_match:
            return page_id_query_match.group(1)

        # Then, check for clean /pages/<id> format
        long_url_path_match = re.search(r"/pages/(\d+)", url)
        if long_url_path_match:
            return long_url_path_match.group(1)

        # If not found, assume it's a short URL and try to resolve it.
        logger.info(f"Attempting to resolve short URL: {url}")
        try:
            # Use an async HEAD request for efficiency as we only need the final URL.
            # HTTPSHelper._make_request returns httpx.Response directly.
            response = await self.https_helper._make_request(
                "HEAD",
                url,
                headers=self.headers,
                timeout=5,
                follow_redirects=True,
            )
            if 300 <= response.status_code < 400 and response.headers.get("Location"):
                redirect_url = response.headers["Location"]
                logger.info(
                    f"Received redirect status {response.status_code}. Following redirect to: {redirect_url}"
                )
                return await self.get_page_id_from_url(redirect_url)
            elif response.status_code == 200:
                # If it's a 200 OK, then response.url should be the final URL.
                final_url = str(response.url)
                logger.info(f"Short URL resolved to: {final_url}")
            else:
                # For other non-200/3xx statuses, it's an unexpected response.
                logger.error(
                    f"Unexpected status code {response.status_code} when resolving short URL '{url}'."
                )
                return None

            # Apply both regex checks to the final_url explicitly and separately
            resolved_page_id_query_match = re.search(r"pageId=(\d+)", final_url)
            if resolved_page_id_query_match:
                return resolved_page_id_query_match.group(1)

            resolved_long_url_path_match = re.search(r"/pages/(\d+)", final_url)
            if resolved_long_url_path_match:
                return resolved_long_url_path_match.group(1)

            logger.error(
                "Could not extract page ID from the final resolved URL: " f"{final_url}"
            )
            return None
        except Exception as e:  # Catch all exceptions from _make_request
            logger.error(f"Could not resolve the short URL '{url}'. Details: {e}")
            return None

    async def get_page_by_id(
        self, page_id: str, expand: Optional[str] = None, version: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:  # <--- Added version parameter
        """
        Retrieves a Confluence page by its ID asynchronously.
        Can optionally retrieve a specific version of the page.

        Args:
            page_id (str): The ID of the Confluence page to retrieve.
            expand (Optional[str]): A comma-separated list of properties to expand.
            version (Optional[int]): The specific version number of the page to retrieve.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the page data,
                                      or None if retrieval fails.
        """
        if version is not None:
            # The /rest/api/content/{id} endpoint supports 'version' as a query parameter.
            url = f"{self.base_url}/rest/api/content/{page_id}"
            params = {"version": version}  # Version is a query parameter
            if expand:
                params["expand"] = expand
        else:
            url = f"{self.base_url}/rest/api/content/{page_id}"
            params = {"expand": expand} if expand else {}

        try:
            return await self.https_helper.get(url, headers=self.headers, params=params)
        except Exception as e:
            logger.error(
                f"Failed to get Confluence page {page_id} (version {version if version else 'latest'}): {e}"
            )
            return None

    async def get_page_child_by_type(
        self, page_id: str, page_type: str = "page"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves child pages of a specific type asynchronously, with pagination.

        Args:
            page_id (str): The ID of the parent page.
            page_type (str): The type of child to retrieve (e.g., 'page').

        Returns:
            List[Dict[str, Any]]: A list of child page objects.
        """
        all_results: List[Dict[str, Any]] = []
        start = 0
        limit = 50

        while True:
            url = (
                f"{self.base_url}/rest/api/content/{page_id}/child/{page_type}"
                f"?start={start}&limit={limit}"
            )
            try:
                response_data = await self.https_helper.get(url, headers=self.headers)
            except Exception as e:
                logger.error(
                    f"Failed to retrieve child pages for '{page_id}' "
                    f"at start={start}. Returning partial results. Error: {e}"
                )
                break  # Exit loop on API failure

            current_results = response_data.get("results", [])
            all_results.extend(current_results)

            # Check if there are more results based on size and _links.next
            if not current_results or len(current_results) < limit:
                break

            start += len(current_results)

        return all_results

    async def update_page(self, page_id: str, title: str, body: str) -> bool:
        """
        Updates a Confluence page asynchronously.

        Args:
            page_id (str): The ID of the page to update.
            title (str): The new title for the page.
            body (str): The new body content in Confluence storage format.

        Returns:
            bool: True if the page was updated successfully, False otherwise.
        """
        url = f"{self.base_url}/rest/api/content/{page_id}"
        current_page = await self.get_page_by_id(page_id, expand="version")
        if not current_page:
            logger.error(f"Could not retrieve page '{page_id}' for update.")
            return False

        new_version = current_page["version"]["number"] + 1
        payload = {
            "version": {"number": new_version},
            "type": "page",
            "title": title,
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        try:
            response = await self.https_helper.put(
                url,
                headers=self.headers,
                json_data=payload,
            )
            if response:  # httpx.put returns a response object, check its status implicitly via raise_for_status()
                logger.info(f"Successfully updated page {page_id} via REST call.")
                return True
        except Exception as e:
            logger.error(f"Failed to update page {page_id}: {e}")
        return False

    async def create_page(
        self, space_key: str, title: str, body: str, parent_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a new Confluence page asynchronously.

        Args:
            space_key (str): The key of the space where the page will be created.
            title (str): The title of the new page.
            body (str): The body content in Confluence storage format.
            parent_id (Optional[str]): The ID of the parent page, if it's a child page.

        Returns:
            Optional[Dict[str, Any]]: The created page object, or None.
        """
        url = f"{self.base_url}/rest/api/content"
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": body, "representation": "storage"}},
            "ancestors": ([{"id": parent_id}] if parent_id else []),
        }
        try:
            response = await self.https_helper.post(
                url,
                headers=self.headers,
                json_data=payload,
            )
            if response:
                return response  # httpx.post returns the JSON directly if successful
        except Exception as e:
            logger.error(f"Failed to create Confluence page '{title}': {e}")
        return None

    async def get_user_details_by_username(
        self, username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves user details by username asynchronously.
        """
        url = f"{self.base_url}/rest/api/user?username={username}"
        try:
            return await self.https_helper.get(url, headers=self.headers)
        except Exception as e:
            logger.error(f"Failed to get user details for username '{username}': {e}")
            return None

    async def get_user_details_by_userkey(
        self, userkey: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves user details by user key asynchronously.
        """
        url = f"{self.base_url}/rest/api/user?key={userkey}"
        try:
            return await self.https_helper.get(url, headers=self.headers)
        except Exception as e:
            logger.error(f"Failed to get user details for userkey '{userkey}': {e}")
            return None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Recursively finds all descendant page IDs using asynchronous API calls.

        This method builds a complete list of all child pages, and their
        children, down the entire hierarchy from the starting page ID,
        leveraging concurrent fetching.

        Args:
            page_id (str): The starting page ID.

        Returns:
            List[str]: A flat list of all descendant page IDs.
        """
        all_ids = []
        # Use the concurrent method to get all descendants
        descendant_pages_data = await self.get_all_descendants_concurrently(page_id)
        for page_data in descendant_pages_data:
            all_ids.append(page_data["id"])
        return all_ids

    async def get_all_descendants_concurrently(
        self, page_id: str
    ) -> List[Dict[str, Any]]:
        """
        Recursively fetches all descendant pages of a given page concurrently.
        This is an internal helper method for get_all_descendants.
        """
        all_pages = []
        processed_page_ids = set()
        pages_to_process = [page_id]  # Start with the initial page ID

        while pages_to_process:
            current_batch_ids = list(pages_to_process)  # Copy for iteration
            pages_to_process = []  # Reset for next batch of children

            tasks = []
            for p_id in current_batch_ids:
                if p_id not in processed_page_ids:
                    processed_page_ids.add(p_id)
                    tasks.append(
                        self.get_page_child_by_type(p_id)
                    )  # Calls the async method

            if tasks:
                # Run all child page fetches in the current batch concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        logger.error(f"Error fetching a batch of child pages: {res}")
                        continue  # Continue processing other tasks
                    for child_page in res:
                        all_pages.append(child_page)
                        pages_to_process.append(
                            child_page["id"]
                        )  # Add children to next batch

        return all_pages

    async def get_tasks_from_page(
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
            # A task is nested if its immediate parent <ac:task-list> has an <ac:task-body> as its parent.
            parent_task_list = task_element.find_parent("ac:task-list")
            if parent_task_list and parent_task_list.find_parent("ac:task-body"):
                continue  # This task is nested within another task's body.
            # Parse the task element into a structured object
            parsed_task = await self._parse_single_task(
                task_element, page_details
            )  # Await this call
            if parsed_task:
                tasks.append(parsed_task)
        return tasks

    async def _parse_single_task(
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
            else None
        )

        page_version = page_details.get("version", {})
        context = get_task_context(task_element)

        # Create a modifiable copy to avoid altering the main soup object.
        task_body_copy = BeautifulSoup(str(task_body), "html.parser")

        # Remove nested task lists to get only the parent task's summary.
        for nested_task_list in task_body_copy.find_all("ac:task-list"):
            nested_task_list.decompose()

        # Clean the text to get a concise summary.
        task_summary = " ".join(task_body_copy.get_text(separator=" ").split()).strip()

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

    async def _parse_single_task(
        self, task_element: Any, page_details: Dict[str, Any]
    ) -> Optional[ConfluenceTask]:
        """
        Parses a single <ac:task> element into a ConfluenceTask object asynchronously.

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
                # Await the call to get user details
                user_details = await self.get_user_details_by_userkey(user_key)
                if user_details:
                    assignee_name = user_details.get("username")

        due_date_tag = task_element.find("time")
        due_date = (
            due_date_tag["datetime"]
            if due_date_tag and "datetime" in due_date_tag.attrs
            else None
        )

        page_version = page_details.get("version", {})
        context = get_task_context(task_element)

        # Create a modifiable copy to avoid altering the main soup object.
        task_body_copy = BeautifulSoup(str(task_body), "html.parser")

        # Remove nested task lists to get only the parent task's summary.
        for nested_task_list in task_body_copy.find_all("ac:task-list"):
            nested_task_list.decompose()

        # Clean the text to get a concise summary.
        task_summary = " ".join(task_body_copy.get_text(separator=" ").split()).strip()

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

    async def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> None:
        """
        Replaces completed Confluence tasks with Jira issue macros asynchronously.

        This method retrieves a page, finds tasks based on the provided
        mappings, removes the original task element, and inserts a Jira
        macro in its place.

        Args:
            page_id (str): The ID of the Confluence page to update.
            mappings (List[Dict[str, str]]): A list of dictionaries, each
                                             mapping a `confluence_task_id` to a `jira_key`.
        """
        page = await self.get_page_by_id(
            page_id, expand="body.storage,version"
        )  # Await this call
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

            await self.update_page(page_id, page["title"], str(soup))  # Await this call
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
            f'<ac:parameter ac:name="server">{self.jira_macro_server_name}</ac:parameter>'
            f'<ac:parameter ac:name="serverId">{self.jira_macro_server_id}</ac:parameter>'
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f"</ac:structured-macro></p>"
        )

    async def get_all_spaces(self) -> List[Dict[str, Any]]:
        """
        Retrieves a list of all Confluence spaces asynchronously.
        Used for health checks.
        """
        url = f"{self.base_url}/rest/api/space"  # Confluence Server/DC API for spaces
        try:
            response_data = await self.https_helper.get(url, headers=self.headers)
            return response_data.get("results", [])
        except Exception as e:
            logger.error(f"Error getting all Confluence spaces: {e}")
            raise
