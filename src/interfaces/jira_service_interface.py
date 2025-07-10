from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.data_models import ConfluenceTask


class JiraApiServiceInterface(ABC):
    """
    An abstract base class for Jira-specific API service.

    This interface defines all the methods required for interacting with
    Jira, ensuring a consistent contract for implementing classes.
    """

    @abstractmethod
    def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
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
    def create_issue(
        self,
        task: ConfluenceTask,
        parent_key: str,
        request_user: Optional[str] = "jira-user",
    ) -> Optional[str]:
        """
        Creates a new Jira issue.

        Args:
            task (ConfluenceTask): The task data from Confluence.
            parent_key (str): The key of the parent issue (e.g., Work Package).
            request_user (Optional[str]): The user who initiated the sync request

        Returns:
            Optional[str]: The key of the newly created issue, or None on failure.
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
    def prepare_jira_task_fields(
        self, task: ConfluenceTask, parent_key: str, request_user: str
    ) -> Dict[str, Any]:
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

    @abstractmethod
    def search_issues_by_jql(
        self, jql_query: str, fields: str = "*all"
    ) -> List[Dict[str, Any]]:
        """Delegates JQL search to the API layer."""
        pass

    @abstractmethod
    def get_issue_type_name_by_id(self, type_id: str) -> Optional[str]:
        """
        Retrieves the name of a Jira issue type by its ID.
        Delegates to the API layer.
        """
        pass
