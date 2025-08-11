"""
Defines the abstract interface for Confluence API services.

This module specifies the contract that any Confluence service implementation
must adhere to. By programming to this interface, the application ensures
that different implementations of the Confluence service are interchangeable,
promoting loose coupling and easier testing.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.data_models import ConfluenceTask


class IConfluenceService(ABC):
    """
    An abstract base class for a service that provides an interface to the
    Confluence API. This defines the contract for Confluence-related operations
    that other parts of the application will depend on.
    """

    @abstractmethod
    async def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Retrieves the Confluence page ID from a given URL asynchronously.

        Args:
            url (str): The URL of the Confluence page, which can be a standard
                       long URL or a short link.

        Returns:
            Optional[str]: The page ID if it can be successfully extracted or
                           resolved, otherwise None.
        """
        pass

    @abstractmethod
    async def get_page_by_id(
        self, page_id: str, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves a Confluence page by its ID asynchronously.

        Args:
            page_id (str): The ID of the Confluence page.
            **kwargs: Additional parameters to pass to the Confluence API call,
                      such as 'expand' to include extra details like page
                      content ('body.storage') or version information.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the page details,
                                      or None if the page is not found.
        """
        pass

    @abstractmethod
    async def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Retrieves all descendant page IDs for a given Confluence page ID.

        This method should recursively fetch the IDs of all child pages in the
        hierarchy beneath the specified parent page.

        Args:
            page_id (str): The ID of the parent Confluence page.

        Returns:
            List[str]: A flat list of all descendant page IDs.
        """
        pass

    @abstractmethod
    async def get_tasks_from_page(
        self, page_details: Dict[str, Any]
    ) -> List[ConfluenceTask]:
        """
        Extracts Confluence tasks from the content of a page asynchronously.

        Args:
            page_details (Dict[str, Any]): The full page details dictionary,
                                           which is expected to contain the page's
                                           body content in storage format under
                                           'body.storage.value'.

        Returns:
            List[ConfluenceTask]: A list of structured `ConfluenceTask` objects
                                  found on the page.
        """
        pass

    @abstractmethod
    async def add_jira_links_to_page(
        self, page_id: str, mappings: List[Dict[str, str]]
    ) -> bool:
        """
        Updates a Confluence page by replacing completed tasks with Jira links.

        This method should modify the page content to reflect that tasks have
        been migrated to Jira issues.

        Args:
            page_id (str): The ID of the Confluence page to update.
            mappings (List[Dict[str, str]]): A list of dictionaries,
                where each maps a 'confluence_task_id' to its new 'jira_key'.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def update_page_content(
        self, page_id: str, new_title: str, new_body: str
    ) -> bool:
        """
        Updates the full content of a Confluence page asynchronously.

        Args:
            page_id (str): The ID of the Confluence page to update.
            new_title (str): The new title for the page.
            new_body (str): The new HTML content for the page body in
                                Confluence storage format.

        Returns:
            bool: True if the page was successfully updated, False otherwise.
        """
        pass

    @abstractmethod
    def generate_jira_macro(self, jira_key: str, with_summary: bool = False) -> str:
        """
        Generates the Confluence storage format HTML for a Jira macro.

        Args:
            jira_key (str): The key of the Jira issue.
            with_summary (bool): If True, generates a macro that shows the summary.
                                 Defaults to False.
        Returns:
            str: The HTML string for the Confluence macro.
        """
        pass

    @abstractmethod
    async def health_check(self) -> None:
        """Performs a basic API call to check connectivity and auth."""
        pass
