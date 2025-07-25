"""
Provides a high-level service for interacting with Jira.

This module contains the `JiraService`, which acts as the business logic
layer for Jira operations. It implements the unified `JiraApiServiceInterface`
and uses the `SafeJiraApi` for its underlying calls.

The service is responsible for preparing and creating Jira issues based on
Confluence task data, handling issue transitions, and retrieving user
information.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.exceptions import JiraApiError
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import (
    ConfluenceTask,
    JiraIssue,
    JiraIssueStatus,
    SyncContext,
)

logger = logging.getLogger(__name__)


class JiraService(JiraApiServiceInterface):
    """
    A concrete implementation of the Jira service interface.

    This class orchestrates Jira-specific business logic, such as constructing
    the necessary fields to create a new Jira issue from a Confluence task. It
    delegates the actual API communication to the `SafeJiraApi` layer.
    """

    def __init__(self, safe_jira_api: SafeJiraApi):
        """
        Initializes the JiraService.

        Args:
            safe_jira_api (SafeJiraApi): An instance of the safe, low-level
                Jira API wrapper.
        """
        self._api = safe_jira_api
        self._current_user_name: Optional[str] = None

    async def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        """
        Delegates fetching a Jira issue to the API layer.

        Args:
            issue_key (str): The key of the issue to fetch.
            fields (str): The fields to retrieve.

        Returns:
            Optional[Dict[str, Any]]: The issue data, or None on failure.
        """
        return await self._api.get_issue(issue_key, fields)

    async def create_issue(
        self,
        task: ConfluenceTask,
        parent_key: str,
        context: SyncContext,
    ) -> Optional[str]:
        """
        Creates a new Jira issue from a Confluence task asynchronously.

        This method prepares the required fields and then calls the underlying
        API to create the issue in Jira.

        Args:
            task (ConfluenceTask): The task data from Confluence.
            parent_key (str): The key of the parent issue (e.g., Work Package).
            context (SyncContext): Contextual information for the sync operation.

        Returns:
            Optional[str]: The key of the newly created issue, or None on failure.
        """
        issue_fields = await self.prepare_jira_task_fields(task, parent_key, context)
        logger.debug(
            "Attempting to create Jira issue with payload: "
            f"{json.dumps(issue_fields, indent=2)}"
        )
        new_issue = await self._api.create_issue(issue_fields)
        return new_issue.get("key") if new_issue else None

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Delegates transitioning a Jira issue to a new status to the API layer.

        Args:
            issue_key (str): The key of the issue to transition.
            target_status (str): The name of the target status.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            await self._api.transition_issue(issue_key, target_status)
            return True
        except JiraApiError as e:
            logger.error(
                f"Failed to transition Jira issue {issue_key} to {target_status}: {e}"
            )
            return False

    async def get_current_user_display_name(self) -> str:
        """
        Gets the display name of the logged-in user, with caching.

        This method retrieves the user's display name on the first call and
        caches it for subsequent requests within the same service instance
        to improve efficiency.

        Returns:
            str: The user's display name, or 'Unknown User' as a fallback.
        """
        if self._current_user_name is None:
            user_details = await self._api.get_current_user()
            if user_details and "displayName" in user_details:
                self._current_user_name = user_details["displayName"]
            else:
                self._current_user_name = "Unknown User"
        return self._current_user_name

    async def prepare_jira_task_fields(
        self,
        task: ConfluenceTask,
        parent_key: str,
        context: SyncContext,
    ) -> Dict[str, Any]:
        """
        Prepares the field structure for creating a new Jira issue.

        This method constructs the full payload required by the Jira API,
        including a detailed description that combines contextual information
        from Confluence with metadata about the task's creation.

        Args:
            task (ConfluenceTask): The source Confluence task.
            parent_key (str): The key of the parent Jira issue (e.g., 'WP-1').
            context (SyncContext): Contextual information for the sync operation.

        Returns:
            Dict[str, Any]: A dictionary of fields ready for the API.
        """
        user_name = await self.get_current_user_display_name()
        creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        project_key = parent_key.split("-")[0]
        description_parts = []

        if task.context and task.context.startswith("JIRA_KEY_CONTEXT::"):
            context_key = task.context.split("::")[1]
            context_issue = await self._api.get_issue(
                context_key,
                fields=["description", "summary"],
            )

            context_found = False
            if context_issue:
                fields = context_issue.get("fields", {})
                description = fields.get("description")
                summary = fields.get("summary")

                if description and description.strip():
                    description_parts.append(
                        f"Context from parent issue {context_key}:"
                        f"\n----\n{description}\n----"
                    )
                    context_found = True
                elif summary:
                    description_parts.append(
                        f"Context from parent issue {context_key}: {summary}"
                    )
                    context_found = True

            if not context_found:
                description_parts.append(
                    f"Context from parent issue: {context_key} "
                    "(Could not retrieve details)."
                )

        elif task.context:
            description_parts.append(f"Context from Confluence:\n{task.context}")

        description_parts.append(
            f"Created by {user_name} on {creation_time} "
            f"requested by {context.request_user}"
        )

        final_description = "\n\n".join(description_parts)

        if task.due_date:
            due_date = task.due_date
            logger.info(f"Using due date from Confluence task: {due_date}")
        else:
            calculated_due_date = date.today() + timedelta(
                days=context.days_to_due_date
            )
            due_date = calculated_due_date.strftime("%Y-%m-%d")
            logger.info(f"Calculating due date: {due_date}")

        summary = task.task_summary or "No Summary Provided"
        if len(summary) > config.JIRA_SUMMARY_MAX_CHARS:
            logger.warning(
                f"Task summary is too long ({len(summary)} > "
                f"{config.JIRA_SUMMARY_MAX_CHARS}). Truncating summary for "
                f"Confluence Task ID: {task.confluence_task_id}."
            )
            summary = summary[: config.JIRA_SUMMARY_MAX_CHARS - 3] + "..."
        description = final_description or "No Description Provided"
        if len(description) > config.JIRA_DESCRIPTION_MAX_CHARS:
            logger.warning(
                f"Task description is too long ({len(description)} > "
                f"{config.JIRA_DESCRIPTION_MAX_CHARS}). Truncating "
                f"description for Confluence Task ID: {task.confluence_task_id}. "
            )
            description = description[: config.JIRA_DESCRIPTION_MAX_CHARS - 3] + "..."
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"id": config.TASK_ISSUE_TYPE_ID},
            "description": description,
            "duedate": due_date,
            config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
        }

        # Conditionally add the assignee field if task.assignee_name is set
        if task.assignee_name:
            fields["assignee"] = {"name": task.assignee_name}
        return fields

    async def search_issues_by_jql(
        self, jql_query: str, fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Delegates JQL search to the API layer asynchronously.

        Args:
            jql_query (str): The JQL query to execute.
            fields (List[str], optional): Specific fields to return. Defaults to None.

        Returns:
            List[Dict[str, Any]]: The list of issues found.
        """
        return await self._api.search_issues(jql_query, fields=fields)

    async def get_issue_type_name_by_id(self, type_id: str) -> Optional[str]:
        """
        Retrieves the name of a Jira issue type by its ID asynchronously.

        Args:
            type_id (str): The ID of the issue type.

        Returns:
            Optional[str]: The name of the issue type, or None if not found.
        """
        issue_type_details = await self._api.get_issue_type_details_by_id(type_id)
        return issue_type_details.get("name") if issue_type_details else None

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        """
        Asynchronously retrieves the status of a Jira issue.

        Args:
            issue_key (str): The key of the Jira issue.

        Returns:
            Optional[JiraIssueStatus]: A structured status object, or None on failure.
        """
        try:
            issue_data = await self._api.get_issue(issue_key, fields=["status"])
            status_info = issue_data.get("fields", {}).get("status", {})
            if status_info:
                return JiraIssueStatus(
                    name=status_info.get("name"),
                    category=status_info.get("statusCategory", {}).get("key"),
                )
        except JiraApiError as e:
            logger.error(f"Could not retrieve status for Jira issue {issue_key}: {e}")
        return None

    async def get_jira_issue(self, issue_key: str) -> Optional[JiraIssue]:
        """
        Asynchronously retrieves a full Jira issue and maps it to a Pydantic model.

        Args:
            issue_key (str): The key of the Jira issue.

        Returns:
            Optional[JiraIssue]: A structured `JiraIssue` object, or None on failure.
        """
        try:
            issue_data = await self._api.get_issue(
                issue_key, fields=["summary", "status", "issuetype"]
            )
            if issue_data:
                status_name = issue_data["fields"]["status"]["name"]
                status_category = issue_data["fields"]["status"]["statusCategory"][
                    "key"
                ]
                issue_status = JiraIssueStatus(
                    name=status_name, category=status_category
                )
                return JiraIssue(
                    key=issue_data["key"],
                    summary=issue_data["fields"]["summary"],
                    status=issue_status,
                    issue_type=issue_data["fields"]["issuetype"]["name"],
                )
        except JiraApiError as e:
            logger.error(f"Could not retrieve full Jira issue {issue_key}: {e}")
        return None

    async def assign_issue(self, issue_key: str, assignee_name: Optional[str]) -> bool:
        """
        Assigns a Jira issue to a specified user or unassigns it.
        Exposes SafeJiraApi's assign_issue method.
        """
        try:
            await self._api.assign_issue(issue_key, assignee_name)
            return True
        except JiraApiError as e:
            logger.error(f"Failed to assign/unassign Jira issue {issue_key}: {e}")
            return False
