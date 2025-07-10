from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ConfluenceApiServiceInterface(ABC):
    """
    An abstract base class for a service that provides an interface to the
    Confluence API. This defines the contract for Confluence-related operations
    that other parts of the application will depend on, promoting loose coupling.
    """

    @abstractmethod
    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Retrieves the Confluence page ID from a given URL.

        Args:
            url (str): The URL of the Confluence page.

        Returns:
            Optional[str]: The page ID if found, otherwise None.
        """
        pass

    @abstractmethod
    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Retrieves a Confluence page by its ID.

        Args:
            page_id (str): The ID of the Confluence page.
            **kwargs: Additional parameters to pass to the Confluence API call,
                      e.g., 'expand' for including page content or version.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing page details, or None if not found.
        """
        pass

    @abstractmethod
    def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Retrieves all descendant page IDs for a given Confluence page ID.

        Args:
            page_id (str): The ID of the parent Confluence page.

        Returns:
            List[str]: A list of descendant page IDs.
        """
        pass

    @abstractmethod
    def get_tasks_from_page(self, page_details: Dict[str, Any]) -> List[Any]:
        """
        Extracts Confluence tasks from the content of a page.

        Args:
            page_details (Dict[str, Any]): The page details dictionary,
                                         expected to contain 'body.storage.value'.

        Returns:
            List[Any]: A list of ConfluenceTask objects.
        """
        pass

    @abstractmethod
    def update_page_with_jira_links(
        self, page_id: str, jira_task_mappings: List[Dict[str, str]]
    ) -> bool:
        """
        Updates a Confluence page's content by embedding Jira links into existing tasks.

        Args:
            page_id (str): The ID of the Confluence page to update.
            jira_task_mappings (List[Dict[str, str]]): A list of dictionaries,
                each containing 'confluence_task_id' and 'jira_key'.

        Returns:
            bool: True if the page was successfully updated, False otherwise.
        """
        pass

    @abstractmethod
    def update_page_content(self, page_id: str, title: str, html_content: str) -> bool:
        """
        Updates the content of a Confluence page with new HTML content.

        Args:
            page_id (str): The ID of the Confluence page to update.
            title (str): The current title of the page.
            html_content (str): The new HTML content for the page.

        Returns:
            bool: True if the page was successfully updated, False otherwise.
        """
        pass
