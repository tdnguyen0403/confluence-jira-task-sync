from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.data_models import ConfluenceTask


class ConfluenceApiServiceInterface(ABC):
    """
    An abstract base class for Confluence-specific API service.

    This interface defines all the methods required for interacting with
    Confluence, ensuring a consistent contract for implementing classes.
    """

    @abstractmethod
    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Extracts a Confluence page ID from a URL.

        Args:
            url (str): The Confluence page URL.

        Returns:
            Optional[str]: The extracted page ID, or None on failure.
        """
        pass

    @abstractmethod
    def get_all_descendants(self, page_id: str) -> List[str]:
        """
        Recursively gets all descendant page IDs for a given page.

        Args:
            page_id (str): The ID of the top-level page.

        Returns:
            List[str]: A list of all descendant page IDs.
        """
        pass

    @abstractmethod
    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single Confluence page by its ID.

        Args:
            page_id (str): The ID of the page.
            **kwargs: Additional options like 'expand'.

        Returns:
            Optional[Dict[str, Any]]: The page data, or None on failure.
        """
        pass

    @abstractmethod
    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool:
        """
        Updates the title and body of a Confluence page.

        Args:
            page_id (str): The ID of the page to update.
            new_title (str): The new title for the page.
            new_body (str): The new body content in storage format.

        Returns:
            bool: True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]:
        """
        Extracts all tasks from the content of a Confluence page.

        Args:
            page_details (Dict): The full page object from the Confluence API.

        Returns:
            List[ConfluenceTask]: A list of found Confluence tasks.
        """
        pass

    @abstractmethod
    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None:
        """
        Replaces Confluence tasks on a page with links to Jira issues.

        Args:
            page_id (str): The ID of the page to update.
            mappings (List[Dict]): A list mapping Confluence task IDs to
                                   Jira issue keys.
        """
        pass

    @abstractmethod
    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Creates a new page in Confluence.

        Args:
            **kwargs: Arguments for page creation (e.g., space, title, body).

        Returns:
            Optional[Dict[str, Any]]: The created page data, or None on failure.
        """
        pass

    @abstractmethod
    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves Confluence user details by username.

        Args:
            username (str): The username to look up.

        Returns:
            Optional[Dict[str, Any]]: The user's details, or None on failure.
        """
        pass
