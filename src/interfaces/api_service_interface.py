"""
Defines the abstract interface for API services.

This module contains the `ApiServiceInterface`, an Abstract Base Class (ABC)
that establishes a common contract for all high-level API service
implementations. By defining a standard set of methods, it ensures that
different service implementations are interchangeable, which is beneficial for
dependency injection, testing, and future extensibility.

Note: This consolidated interface design means that a concrete class
implementing it (like a combined Jira/Confluence service) will need to
provide an implementation for every method, even if it only uses a subset.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.data_models import ConfluenceTask


class ApiServiceInterface(ABC):
    """
    An abstract base class for a consolidated API service.

    This interface defines all the methods required for interacting with both
    Jira and Confluence, ensuring a consistent contract for implementing
    classes.
    """

    # --- Jira Methods ---

    @abstractmethod
    def get_issue(self, issue_key: str,
                  fields: str = "*all") -> Optional[Dict[str, Any]]:
        """
        Retrieves a single Jira issue by its key.

        Args:
            issue_key (str): The key of the issue (e.g., 'PROJ-123').
            fields (str): A comma-separated list of fields to return.

        Returns:
            Optional[Dict[str, Any]]: The issue data, or None on failure.
        """
        pass

    @abstractmethod
    def create_issue(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Creates a new Jira issue.

        Args:
            fields (Dict[str, Any]): The fields for the new issue.

        Returns:
            Optional[Dict[str, Any]]: The created issue data, or None on failure.
        """
        pass

    @abstractmethod
    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transitions a Jira issue to a new status.

        Args:
            issue_key (str): The key of the issue to transition.
            target_status (str): The name of the target status.

        Returns:
            bool: True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def prepare_jira_task_fields(self, task: ConfluenceTask,
                                 parent_key: str) -> Dict[str, Any]:
        """
        Prepares the field structure for creating a Jira task from a
        Confluence task.

        Args:
            task (ConfluenceTask): The source Confluence task object.
            parent_key (str): The key of the parent Jira issue.

        Returns:
            Dict[str, Any]: A dictionary of fields ready for the Jira API.
        """
        pass

    @abstractmethod
    def get_current_user_display_name(self) -> str:
        """
        Retrieves the display name of the currently authenticated user.

        Returns:
            str: The user's display name, or a default string on failure.
        """
        pass

    # --- Confluence Methods ---

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
    def get_page_by_id(self, page_id: str,
                       **kwargs) -> Optional[Dict[str, Any]]:
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
    def update_page_content(self, page_id: str, new_title: str,
                            new_body: str) -> bool:
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
    def get_tasks_from_page(self,
                              page_details: Dict) -> List[ConfluenceTask]:
        """
        Extracts all tasks from the content of a Confluence page.

        Args:
            page_details (Dict): The full page object from the Confluence API.

        Returns:
            List[ConfluenceTask]: A list of found Confluence tasks.
        """
        pass

    @abstractmethod
    def update_page_with_jira_links(self, page_id: str,
                                    mappings: List[Dict]) -> None:
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
    def get_user_details_by_username(self,
                                     username: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves Confluence user details by username.

        Args:
            username (str): The username to look up.

        Returns:
            Optional[Dict[str, Any]]: The user's details, or None on failure.
        """
        pass
