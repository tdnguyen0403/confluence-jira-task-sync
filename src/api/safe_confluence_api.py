"""
Provides a resilient, low-level API wrapper for Confluence operations.

This module contains the SafeConfluenceApi class, which is designed to
interact with the Confluence REST API in a fault-tolerant and asynchronous
manner. It leverages the `HTTPSHelper` for all underlying HTTP communications,
ensuring that API calls benefit from features like connection pooling and
automatic retries for transient network issues.

The class abstracts the complexities of the Confluence API, offering
simplified methods for common operations such as:
-   Fetching and updating pages.
-   Resolving page IDs from various URL formats.
-   Finding and parsing tasks within page content.
-   Creating new pages and traversing page hierarchies.
-   Updating pages with links to Jira issues.

By centralizing Confluence interactions, this class promotes consistency,
improves reliability, and simplifies maintenance.
"""

import asyncio
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from src.api.error_handler import handle_api_errors
from src.api.https_helper import HTTPSHelper
from src.config import config
from src.exceptions import ConfluenceApiError
from src.models.data_models import ConfluenceTask
from src.utils.context_extractor import get_task_context

logger = logging.getLogger(__name__)


class SafeConfluenceApi:
    """
    A resilient, low-level service for all Confluence operations.

    This class provides a safe wrapper around the Confluence API, using
    HTTPSHelper for all network interactions to ensure asynchronous operation,
    connection pooling, and retry logic.

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
        base_url: str,
        https_helper: HTTPSHelper,
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
                                          Defaults to a value from config.
            jira_macro_server_id (str): The ID of the Jira server for macros.
                                        Defaults to a value from config.
        """
        self.base_url = config.CONFLUENCE_URL.rstrip("/")
        self.https_helper = https_helper
        self.headers = {
            "Authorization": f"Bearer {config.CONFLUENCE_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.jira_macro_server_name = jira_macro_server_name
        self.jira_macro_server_id = jira_macro_server_id

    @handle_api_errors(ConfluenceApiError)
    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Extracts the Confluence page ID from a standard or short URL asynchronously.

        This utility method first attempts to parse the ID from a standard
        long-form URL (e.g., with a `pageId` query parameter or a `/pages/<id>`
        path). If that fails, it resolves the URL by making a `HEAD` request
        to handle redirects (common for short links) and then parses the ID
        from the final resolved URL.

        Args:
            url (str): The Confluence page URL (long or short form).

        Returns:
            Optional[str]: The extracted page ID, or None if it cannot be
                           resolved or found.
        """
        page_id_query_match = re.search(r"pageId=(\d+)", url)
        if page_id_query_match:
            return page_id_query_match.group(1)

        long_url_path_match = re.search(r"/pages/(\d+)", url)
        if long_url_path_match:
            return long_url_path_match.group(1)

        logger.info(f"Attempting to resolve short URL: {url}")
        try:
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
                    f"Received redirect status {response.status_code}. "
                    f"Following redirect to: {redirect_url}"
                )
                return await self.get_page_id_from_url(redirect_url)
            elif response.status_code == 200:
                final_url = str(response.url)
                logger.info(f"Short URL resolved to: {final_url}")
            else:
                logger.error(
                    f"Unexpected status code {response.status_code} "
                    f"when resolving short URL '{url}'."
                )
                return None

            resolved_page_id_query_match = re.search(r"pageId=(\d+)", final_url)
            if resolved_page_id_query_match:
                return resolved_page_id_query_match.group(1)

            resolved_long_url_path_match = re.search(r"/pages/(\d+)", final_url)
            if resolved_long_url_path_match:
                return resolved_long_url_path_match.group(1)

            logger.error(
                f"Could not extract page ID from the final resolved URL: {final_url}"
            )
            return None
        except Exception as e:
            logger.error(f"Could not resolve the short URL '{url}'. Details: {e}")
            return None

    @handle_api_errors(ConfluenceApiError)
    async def get_page_by_id(
        self, page_id: str, expand: Optional[str] = None, version: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves a Confluence page by its ID asynchronously.

        This method can fetch either the latest version of a page or a specific
        historical version. It allows for the expansion of page properties
        (like `version` or `body.storage`) in the response.

        Args:
            page_id (str): The ID of the Confluence page to retrieve.
            expand (Optional[str]): A comma-separated list of properties to expand
                                    (e.g., 'version,body.storage'). Defaults to None.
            version (Optional[int]): The specific version number of the page to
                                     retrieve. If None, retrieves the latest version.
                                     Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the page data,
                                      or None if retrieval fails.
        """
        if version is not None:
            url = f"{self.base_url}/rest/api/content/{page_id}"
            params = {"version": version}
            if expand:
                params["expand"] = expand
        else:
            url = f"{self.base_url}/rest/api/content/{page_id}"
            params = {"expand": expand} if expand else {}

        try:
            return await self.https_helper.get(url, headers=self.headers, params=params)
        except Exception as e:
            logger.error(
                f"Failed to get Confluence page {page_id} "
                f"(version {version if version else 'latest'}): {e}"
            )
            return None

    @handle_api_errors(ConfluenceApiError)
    async def get_page_child_by_type(
        self, page_id: str, page_type: str = "page"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves child items of a specific type for a given page asynchronously.

        This method handles pagination automatically, fetching all child items
        (e.g., pages or attachments) of a specified type that belong to a
        parent page.

        Args:
            page_id (str): The ID of the parent page.
            page_type (str): The type of child to retrieve (e.g., 'page',
                             'comment', 'attachment'). Defaults to 'page'.

        Returns:
            List[Dict[str, Any]]: A list of child item objects. Returns an empty
                                  list if no children are found or an error occurs.
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
                break

            current_results = response_data.get("results", [])
            all_results.extend(current_results)

            if not current_results or len(current_results) < limit:
                break

            start += len(current_results)

        return all_results

    @handle_api_errors(ConfluenceApiError)
    async def update_page(self, page_id: str, title: str, body: str) -> bool:
        """
        Updates the content and title of a Confluence page asynchronously.

        This method fetches the current version of the page to ensure the
        update is not based on stale data, increments the version number,
        and then sends the new title and body content.

        Args:
            page_id (str): The ID of the page to update.
            title (str): The new title for the page.
            body (str): The new body content in Confluence storage format (HTML).

        Returns:
            bool: True if the page was updated successfully, False otherwise.
        """
        url = f"{self.base_url}/rest/api/content/{page_id}"
        current_page = await self.get_page_by_id(page_id, expand="version")
        if not current_page:
            logger.error(f"Could not retrieve page '{page_id}' for update.")
            return False

        try:
            new_version = current_page["version"]["number"] + 1
        except KeyError:
            logger.error(
                f"Could not determine next version for page '{page_id}'. "
                f"'version' key missing."
            )
            return False

        payload = {
            "version": {"number": new_version},
            "type": "page",
            "title": title,
            "body": {"storage": {"value": body, "representation": "storage"}},
        }

        await self.https_helper.put(
            url,
            headers=self.headers,
            json_data=payload,
        )

        # If we reach here, the update was successful
        logger.info(f"Successfully updated page {page_id} via REST call.")
        return True  # Only reached if no exception was raised (i.e., 2xx status)

    @handle_api_errors(ConfluenceApiError)
    async def create_page(
        self, space_key: str, title: str, body: str, parent_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a new Confluence page asynchronously.

        The new page can be created at the root of a space or as a child of an
        existing page.

        Args:
            space_key (str): The key of the space where the page will be created.
            title (str): The title of the new page.
            body (str): The body content in Confluence storage format (HTML).
            parent_id (Optional[str]): The ID of the parent page. If None, the
                                       page is created at the top level of the space.
                                       Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: The created page object as a dictionary,
                                      or None if creation fails.
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
                return response
        except Exception as e:
            logger.error(f"Failed to create Confluence page '{title}': {e}")
        return None

    @handle_api_errors(ConfluenceApiError)
    async def get_user_details_by_username(
        self, username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves Confluence user details by username asynchronously.

        Args:
            username (str): The username of the user to retrieve.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the user's
                                      details, or None if the user is not found
                                      or an error occurs.
        """
        url = f"{self.base_url}/rest/api/user?username={username}"
        try:
            return await self.https_helper.get(url, headers=self.headers)
        except Exception as e:
            logger.error(f"Failed to get user details for username '{username}': {e}")
            return None

    @handle_api_errors(ConfluenceApiError)
    async def get_user_details_by_userkey(
        self, userkey: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves Confluence user details by user key asynchronously.

        Args:
            userkey (str): The user key (a unique identifier) of the user.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the user's
                                      details, or None if the user is not found
                                      or an error occurs.
        """
        url = f"{self.base_url}/rest/api/user?key={userkey}"
        try:
            return await self.https_helper.get(url, headers=self.headers)
        except Exception as e:
            logger.error(f"Failed to get user details for userkey '{userkey}': {e}")
            return None

    async def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Recursively finds all descendant page IDs using concurrent API calls.

        This method builds a complete, flat list of all child pages, their
        children, and so on, down the entire hierarchy from the starting page ID.
        It uses `get_all_descendants_concurrently` to perform the fetch operations
        in parallel for greater efficiency.

        Args:
            page_id (str): The ID of the starting parent page.

        Returns:
            List[str]: A flat list of all descendant page IDs.
        """
        all_ids = []
        descendant_pages_data = await self.get_all_descendants_concurrently(page_id)
        for page_data in descendant_pages_data:
            all_ids.append(page_data["id"])
        return all_ids

    async def get_all_descendants_concurrently(
        self, page_id: str
    ) -> List[Dict[str, Any]]:
        """
        Recursively fetches all descendant pages of a given page concurrently.

        This is an internal helper method that performs a breadth-first traversal
        of the page tree. It fetches all direct children for a level of the
        hierarchy in parallel, significantly speeding up the discovery of all
        descendants compared to a sequential approach.

        Args:
            page_id (str): The ID of the root page for the traversal.

        Returns:
            List[Dict[str, Any]]: A list of page objects representing all
                                  descendants.
        """
        all_pages = []
        processed_page_ids = set()
        queue = asyncio.Queue()
        await queue.put(page_id)

        async def worker():
            while True:
                p_id = await queue.get()
                if p_id in processed_page_ids:
                    queue.task_done()
                    continue

                processed_page_ids.add(p_id)
                try:
                    children = await self.get_page_child_by_type(p_id)
                    for child in children:
                        all_pages.append(child)
                        await queue.put(child["id"])
                except Exception as e:
                    logger.error(f"Error fetching children for page {p_id}: {e}")
                finally:
                    queue.task_done()

        # Create a pool of workers to process pages from the queue concurrently
        tasks = [
            asyncio.create_task(worker()) for _ in range(10)
        ]  # 10 concurrent workers

        await queue.join()  # Wait for the queue to be fully processed

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        return all_pages

    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        """
        Extracts all top-level Confluence tasks from a page's HTML content.

        This method parses the 'storage' format of the page body to find all
        task list items (`<ac:task>`). It specifically ignores tasks that are
        nested inside other tasks or located within certain macros (defined in
        the application config) used for aggregation.

        Args:
            page_details (Dict[str, Any]): The dictionary containing the full
                                           details of a Confluence page,
                                           including the body content.

        Returns:
            List[ConfluenceTask]: A list of `ConfluenceTask` data models found
                                  on the page.
        """
        tasks: List[ConfluenceTask] = []
        html_content = page_details.get("body", {}).get("storage", {}).get("value", "")
        if not html_content:
            return tasks

        soup = BeautifulSoup(html_content, "html.parser")

        for task_element in soup.find_all("ac:task"):
            if task_element.find_parent(
                "ac:structured-macro",
                {"ac:name": lambda x: x in config.AGGREGATION_CONFLUENCE_MACRO},
            ):
                continue
            parent_task_list = task_element.find_parent("ac:task-list")
            if parent_task_list and parent_task_list.find_parent("ac:task-body"):
                continue
            parsed_task = await self._parse_single_task(task_element, page_details)
            if parsed_task:
                tasks.append(parsed_task)
        return tasks

    async def _parse_single_task(
        self, task_element: Any, page_details: Dict[str, Any]
    ) -> Optional[ConfluenceTask]:
        """
        Parses a single <ac:task> element into a ConfluenceTask object asynchronously.

        This helper method extracts all relevant details from a task element,
        including its content (summary), status, assignee (by fetching user
        details if necessary), and due date. It also captures contextual
        information and cleans the task summary by removing any nested tasks.

        Args:
            task_element (Any): The BeautifulSoup tag for an `<ac:task>`.
            page_details (Dict[str, Any]): The details of the parent page, used
                                           for context.

        Returns:
            Optional[ConfluenceTask]: A populated `ConfluenceTask` data model, or
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

        task_body_copy = BeautifulSoup(str(task_body), "html.parser")

        for nested_task_list in task_body_copy.find_all("ac:task-list"):
            nested_task_list.decompose()

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

    @handle_api_errors(ConfluenceApiError)
    async def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> bool:
        """
        Updates a Confluence page by replacing completed tasks with Jira links.
        This method scans the page for tasks that have been completed and
        replaces them with links to their corresponding Jira issues.
        Args:
            page_id (str): The ID of the Confluence page to update.
            mappings (List[Dict[str, str]]): A list of dictionaries, each mapping
                                             a 'confluence_task_id' to its new
                                             'jira_key'.
        Returns:
            bool: True if the page was successfully updated, False otherwise.
        """
        page = await self.get_page_by_id(page_id, expand="body.storage,version")
        if not page:
            logger.error(
                f"Could not retrieve page {page_id} to update with Jira links."
            )
            return False

        soup = BeautifulSoup(page["body"]["storage"]["value"], "html.parser")
        modified = False
        mapping_dict = {m["confluence_task_id"]: m["jira_key"] for m in mappings}

        for task in soup.find_all("ac:task"):
            task_id_tag = task.find("ac:task-id")

            if task_id_tag and task_id_tag.string in mapping_dict:
                if task.find_parent(
                    "ac:structured-macro",
                    {"ac:name": lambda x: x in config.AGGREGATION_CONFLUENCE_MACRO},
                ):
                    continue

                parent_task_list = task.find_parent("ac:task-list")
                if not parent_task_list:
                    continue

                jira_key = mapping_dict[task_id_tag.string]
                task_body = task.find("ac:task-body")
                if not task_body:
                    continue

                task_body_copy = BeautifulSoup(str(task_body), "html.parser")
                for nested_list in task_body_copy.find_all("ac:task-list"):
                    nested_list.decompose()
                task_summary = " ".join(
                    task_body_copy.get_text(separator=" ").split()
                ).strip()

                jira_macro_html = self._generate_jira_macro_html(jira_key)
                new_content_html = f"<p>{jira_macro_html} {task_summary}</p>"
                new_content_soup = BeautifulSoup(new_content_html, "html.parser")

                parent_task_list.insert_after(new_content_soup)

                task.decompose()
                modified = True
                logger.info(
                    f"Prepared task '{task_id_tag.string}' "
                    f"for replacement with text and "
                    f"Jira macro for '{jira_key}'."
                )

        if modified:
            for tl in soup.find_all("ac:task-list"):
                if not tl.find("ac:task"):
                    tl.decompose()
            return await self.update_page(page_id, page["title"], str(soup))
        else:
            logger.warning(
                f"No tasks were replaced on page {page_id}. Skipping update."
            )
            return False  # Indicate no update was performed

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        """
        Generates the Confluence storage format for a Jira issue macro.

        This helper method creates the raw HTML (storage format) for a Jira
        macro that displays a single Jira issue key as a link, without showing
        the issue summary.

        Args:
            jira_key (str): The key of the Jira issue (e.g., 'PROJ-123').

        Returns:
            str: A string containing the HTML for the Confluence macro.
        """
        macro_id = str(uuid.uuid4())
        return (
            f'<ac:structured-macro ac:name="jira" ac:schema-version="1" '
            f'ac:macro-id="{macro_id}">'
            f'<ac:parameter ac:name="showSummary">false</ac:parameter>'
            f'<ac:parameter ac:name="server">{self.jira_macro_server_name}'
            f"</ac:parameter>"
            f'<ac:parameter ac:name="serverId">{self.jira_macro_server_id}'
            f"</ac:parameter>"
            f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
            f"</ac:structured-macro>"
        )

    @handle_api_errors(ConfluenceApiError)
    async def get_all_spaces(self) -> List[Dict[str, Any]]:
        """
        Retrieves a list of all Confluence spaces asynchronously.

        This method is primarily intended for health checks to verify that the
        API connection to Confluence is active and properly authenticated.

        Returns:
            List[Dict[str, Any]]: A list of space objects.

        Raises:
            Exception: Propagates exceptions from the underlying `HTTPSHelper` call
                       if the API request fails.
        """
        url = f"{self.base_url}/rest/api/space"
        response_data = await self.https_helper.get(url, headers=self.headers)
        return response_data.get("results", [])
