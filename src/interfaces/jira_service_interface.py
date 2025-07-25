"""
Defines the abstract interface for Jira API services.

This module provides the `JiraApiServiceInterface`, an abstract base class
that establishes a contract for all Jira-related operations. Any class that
interacts with the Jira API for business logic purposes should implement this
interface. This ensures consistency and allows for dependency injection, making
the application more modular and testable.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.data_models import (
    ConfluenceTask,
    SyncContext,
    JiraIssueStatus,
    JiraIssue,
)


class JiraApiServiceInterface(ABC):
    """
    An abstract base class for a Jira-specific API service.

    This interface defines all the methods required for interacting with
    Jira, ensuring a consistent contract for implementing classes.
    """

    @abstractmethod
    async def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single Jira issue by its key asynchronously.

        Args:
            issue_key (str): The key of the issue (e.g., 'PROJ-123').
            fields (str): A comma-separated list of fields to return. Defaults
                          to '*all' to retrieve all fields.

        Returns:
            Optional[Dict[str, Any]]: The issue data as a dictionary, or None
                                      if the issue is not found or an error occurs.
        """
        pass

    @abstractmethod
    async def create_issue(
        self,
        task: ConfluenceTask,
        parent_key: str,
        context: SyncContext,
    ) -> Optional[str]:
        """
        Creates a new Jira issue from a Confluence task asynchronously.

        Args:
            task (ConfluenceTask): The structured task data from Confluence.
            parent_key (str): The key of the parent issue (e.g., a Work Package).
            context (SyncContext): Contextual information for the sync operation,
                                   such as the requesting user.

        Returns:
            Optional[str]: The key of the newly created issue, or None on failure.
        """
        pass

    @abstractmethod
    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transitions a Jira issue to a new status asynchronously.

        Args:
            issue_key (str): The key of the issue to transition.
            target_status (str): The name of the target status in the workflow
                                 (e.g., 'Done', 'In Progress').

        Returns:
            bool: True if the transition was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def prepare_jira_task_fields(
        self,
        task: ConfluenceTask,
        parent_key: str,
        context: SyncContext,
    ) -> Dict[str, Any]:
        """
        Prepares the field structure for creating a Jira task.

        This method should construct the JSON payload required by the Jira API
        to create a new issue, based on the provided Confluence task and
        contextual information.

        Args:
            task (ConfluenceTask): The source Confluence task object.
            parent_key (str): The key of the parent Jira issue.
            context (SyncContext): The context for the synchronization operation.

        Returns:
            Dict[str, Any]: A dictionary of fields ready to be sent to the Jira API.
        """
        pass

    @abstractmethod
    async def get_current_user_display_name(self) -> str:
        """
        Retrieves the display name of the currently authenticated user.

        Returns:
            str: The user's display name, or a default string on failure.
        """
        pass

    @abstractmethod
    async def search_issues_by_jql(
        self, jql_query: str, fields: str = "*all"
    ) -> List[Dict[str, Any]]:
        """
        Executes a JQL search and returns the results asynchronously.

        Args:
            jql_query (str): The JQL query string.
            fields (str): A comma-separated list of fields to return for each issue.

        Returns:
            List[Dict[str, Any]]: A list of issues matching the query.
        """
        pass

    @abstractmethod
    async def get_issue_type_name_by_id(self, type_id: str) -> Optional[str]:
        """
        Retrieves the name of a Jira issue type by its ID asynchronously.

        Args:
            type_id (str): The ID of the issue type.

        Returns:
            Optional[str]: The name of the issue type, or None if not found.
        """
        pass

    @abstractmethod
    async def get_issue_status(
        self,
        issue_key: str,
    ) -> Optional[JiraIssueStatus]:
        """
        Retrieves the status of a single Jira issue asynchronously.

        Args:
            issue_key (str): The key of the issue.

        Returns:
            Optional[JiraIssueStatus]: A `JiraIssueStatus` object containing
                                       the status name and category, or None
                                       on failure.
        """
        pass

    @abstractmethod
    async def get_jira_issue(
        self,
        issue_key: str,
    ) -> Optional[JiraIssue]:
        """
        Retrieves a full Jira issue and returns it as a structured object.

        Args:
            issue_key (str): The key of the issue.

        Returns:
            Optional[JiraIssue]: A `JiraIssue` object with key details, or None
                                 on failure.
        """
        pass
