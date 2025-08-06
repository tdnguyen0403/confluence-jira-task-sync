"""
Provides a high-level service for interacting with Confluence.

This module contains the `ConfluenceService`, which acts as a business logic
layer abstracting the low-level API calls. It implements the unified
`ConfluenceApiServiceInterface` to ensure a consistent contract across different
services.

The primary role of this class is to delegate Confluence-specific operations
to the underlying `SafeConfluenceApi`, providing a clean and simple interface
for the rest of the application.
"""

import logging
from typing import Any, Dict, List, Optional

from src.api.safe_confluence_api import SafeConfluenceApi
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.models.data_models import ConfluenceTask

logger = logging.getLogger(__name__)


class ConfluenceService(ConfluenceApiServiceInterface):
    """
    A concrete implementation of the Confluence service interface.

    This class serves as a pass-through layer that delegates all its
    operations to an instance of `SafeConfluenceApi`. It provides a clean
    separation between the business logic and the low-level API interaction
    code.
    """

    def __init__(self, safe_confluence_api: SafeConfluenceApi):
        """
        Initializes the ConfluenceService.

        Args:
            safe_confluence_api (SafeConfluenceApi): An instance of the safe,
                low-level Confluence API wrapper.
        """
        self._api = safe_confluence_api

    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Delegates extracting a page ID from a URL to the API layer.

        Args:
            url (str): The Confluence page URL.

        Returns:
            Optional[str]: The extracted page ID, or None if not found.
        """
        return await self._api.get_page_id_from_url(url)

    async def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Delegates fetching all descendant page IDs to the API layer.

        Args:
            page_id (str): The ID of the parent page.

        Returns:
            List[str]: A list of descendant page IDs.
        """
        return await self._api.get_all_descendants(page_id)

    async def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Delegates fetching a page by its ID to the API layer.

        Args:
            page_id (str): The ID of the page.
            **kwargs: Additional arguments like 'expand'.

        Returns:
            Optional[Dict[str, Any]]: The page data, or None.
        """
        return await self._api.get_page_by_id(page_id, **kwargs)

    async def update_page_content(
        self, page_id: str, new_title: str, new_body: str
    ) -> bool:
        """
        Delegates updating page content to the API layer.

        Args:
            page_id (str): The ID of the page to update.
            new_title (str): The new title for the page.
            new_body (str): The new HTML body for the page.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        return await self._api.update_page(page_id, new_title, new_body)

    async def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]:
        """
        Delegates extracting tasks from a page to the API layer.

        Args:
            page_details (Dict): The full dictionary of page details.

        Returns:
            List[ConfluenceTask]: A list of tasks found on the page.
        """
        return await self._api.get_tasks_from_page(page_details)

    async def update_page_with_jira_links(
        self, page_id: str, mappings: List[Dict]
    ) -> bool:
        """
        Delegates updating a page with Jira links to the API layer.

        Args:
            page_id (str): The ID of the page to update.
            mappings (List[Dict]): A list mapping Confluence task IDs to Jira keys.
        Returns:
            bool: True if the update was successful, False otherwise.
        """
        return await self._api.update_page_with_jira_links(page_id, mappings)

    async def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Delegates creating a page to the API layer.

        Args:
            **kwargs: Arguments required for page creation, such as `space_key`,
                      `title`, `body`, and `parent_id`.

        Returns:
            Optional[Dict[str, Any]]: The created page data, or None on failure.
        """
        return await self._api.create_page(**kwargs)

    async def get_user_details_by_username(
        self, username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Delegates fetching user details by username to the API layer.

        Args:
            username (str): The username to look up.

        Returns:
            Optional[Dict[str, Any]]: The user's details, or None.
        """
        return await self._api.get_user_details_by_username(username)

    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        """
        Delegates generating Jira macro HTML to the API layer.
        """
        if with_summary:
            return self._api._generate_jira_macro_html_with_summary(jira_key)
        return self._api._generate_jira_macro_html(jira_key)

    async def health_check(self) -> None:
        """Delegates health check to the API layer by getting all spaces."""
        await self._api.get_all_spaces()
