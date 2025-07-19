from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.data_models import ConfluenceTask  # Added import for ConfluenceTask


class ConfluenceApiServiceInterface(ABC):
    """
    An abstract base class for a service that provides an interface to the
    Confluence API. This defines the contract for Confluence-related operations
    that other parts of the application will depend on, promoting loose coupling.
    """

    @abstractmethod
    async def get_page_id_from_url(self, url: str) -> Optional[str]:  # Changed to async
        """
        Retrieves the Confluence page ID from a given URL asynchronously.

        Args:
            url (str): The URL of the Confluence page.

        Returns:
            Optional[str]: The page ID if found, otherwise None.
        """
        pass

    @abstractmethod
    async def get_page_by_id(
        self, page_id: str, **kwargs
    ) -> Optional[Dict[str, Any]]:  # Changed to async
        """
        Retrieves a Confluence page by its ID asynchronously.

        Args:
            page_id (str): The ID of the Confluence page.
            **kwargs: Additional parameters to pass to the Confluence API call,
                      e.g., 'expand' for including page content or version.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing page details, or None if not found.
        """
        pass

    @abstractmethod
    async def get_all_descendants(self, page_id: str) -> List[str]:  # Changed to async
        """
        Retrieves all descendant page IDs for a given Confluence page ID asynchronously.

        Args:
            page_id (str): The ID of the parent Confluence page.

        Returns:
            List[str]: A list of descendant page IDs.
        """
        pass

    @abstractmethod
    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:  # Changed to async, added ConfluenceTask type hint
        """
        Extracts Confluence tasks from the content of a page asynchronously.

        Args:
            page_details (Dict[str, Any]): The page details dictionary,
                                         expected to contain 'body.storage.value'.

        Returns:
            List[ConfluenceTask]: A list of ConfluenceTask objects.
        """
        pass

    @abstractmethod
    async def update_page_with_jira_links(  # Changed to async
        self, page_id: str, jira_task_mappings: List[Dict[str, str]]
    ) -> None:  # Changed return type to None as it doesn't return bool
        """
        Updates a Confluence page's content by embedding Jira links into existing tasks asynchronously.

        Args:
            page_id (str): The ID of the Confluence page to update.
            jira_task_mappings (List[Dict[str, str]]): A list of dictionaries,
                each containing 'confluence_task_id' and 'jira_key'.

        Returns:
            None: The method performs an action and does not return a value.
        """
        pass

    @abstractmethod
    async def update_page_content(
        self, page_id: str, title: str, html_content: str
    ) -> bool:  # Changed to async
        """
        Updates the content of a Confluence page with new HTML content asynchronously.

        Args:
            page_id (str): The ID of the Confluence page to update.
            title (str): The current title of the page.
            html_content (str): The new HTML content for the page.

        Returns:
            bool: True if the page was successfully updated, False otherwise.
        """
        pass
