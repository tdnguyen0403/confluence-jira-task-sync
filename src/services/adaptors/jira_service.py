"""
Provides a high-level service for interacting with Jira.

This module contains the `JiraService`, which acts as the business logic
layer for Jira operations. It implements the unified `JiraApiServiceInterface`
and uses the `SafeJiraApi` for its underlying calls.

The service is responsible for preparing and creating Jira issues based on
Confluence task data, handling issue transitions, and retrieving user
information.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

# only for debug
import json

from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import (
    ConfluenceTask,
    SyncContext,
    JiraIssueStatus,
    JiraIssue,
)

logger = logging.getLogger(__name__)


class JiraService(JiraApiServiceInterface):
    """
    A thin service layer for Jira, implementing the unified API interface.

    This class handles Jira-specific business logic, such as constructing
    issue fields from Confluence tasks and delegating API calls to the
    resilient `SafeJiraApi` layer.
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
        """Delegates fetching a Jira issue to the API layer asynchronously."""
        return await self._api.get_issue(issue_key, fields)

    async def create_issue(
        self,
        task: ConfluenceTask,
        parent_key: str,
        context: SyncContext,
    ) -> Optional[str]:
        """
        Creates a new Jira issue from a Confluence task asynchronously.

        Args:
            task (ConfluenceTask): The task data from Confluence.
            parent_key (str): The key of the parent issue (e.g., Work Package).
            sync_context (SyncContext): Contextual information for the sync operation.

        Returns:
            Optional[str]: The key of the newly created issue, or None on failure.
        """
        issue_fields = await self.prepare_jira_task_fields(
            task, parent_key, context
        )  # Await prepare_jira_task_fields
        new_issue = await self._api.create_issue(issue_fields)  # Await API call
        logger.debug(
            f"Attempting to create Jira issue with payload: {json.dumps(issue_fields, indent=2)}"
        )  # Add this line
        return (
            new_issue.get("key") if new_issue else None
        )  # Access 'key' from the returned dict

    async def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """Delegates transitioning a Jira issue to the API layer asynchronously."""
        try:
            await self._api.transition_issue(issue_key, target_status)  # Await API call
            return True
        except Exception as e:
            logger.error(
                f"Failed to transition Jira issue {issue_key} to {target_status}: {e}"
            )
            return False

    async def get_current_user_display_name(self) -> str:
        """
        Gets the display name of the logged-in user asynchronously, with caching.

        This method retrieves the user's display name on the first call and
        caches it for subsequent requests to improve efficiency.

        Returns:
            str: The user's display name, or a 'Unknown User' as a fallback.
        """
        if self._current_user_name is None:
            user_details = await self._api.get_current_user()  # Await API call
            if user_details and "displayName" in user_details:
                self._current_user_name = user_details["displayName"]
            else:
                self._current_user_name = "Unknown User"  # Fallback
        return self._current_user_name

    async def prepare_jira_task_fields(
        self,
        task: ConfluenceTask,
        parent_key: str,
        context: SyncContext,
    ) -> Dict[str, Any]:
        """
        Prepares the field structure for creating a new Jira issue asynchronously.

        This method constructs the full payload required by the Jira API,
        including a detailed description that combines contextual information
        from Confluence with metadata about the task's creation. The project
        key is dynamically determined from the parent issue's key.

        Args:
            task (ConfluenceTask): The source Confluence task.
            parent_key (str): The key of the parent Jira issue (e.g., 'WP-1').
            sync_context (SyncContext): Contextual information for the sync operation.

        Returns:
            Dict[str, Any]: A dictionary of fields ready for the API.
        """
        user_name = await self.get_current_user_display_name()  # Await this call
        creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Dynamically determine the project key from the parent issue key.
        # For "WP-1", the project key will be "WP".
        project_key = parent_key.split("-")[0]
        description_parts = []

        if task.context and task.context.startswith("JIRA_KEY_CONTEXT::"):
            context_key = task.context.split("::")[1]

            # Fetch the parent issue, requesting both description and summary.
            context_issue = await self._api.get_issue(  # Await API call
                context_key,
                fields=["description", "summary"],  # Use list for fields
            )

            context_found = False
            if context_issue:
                fields = context_issue.get("fields", {})
                description = fields.get("description")
                summary = fields.get("summary")

                # Priority 1: Use the full description if it exists.
                if description and description.strip():
                    description_parts.append(
                        f"Context from parent issue {context_key}:\n----\n{description}\n----"
                    )
                    context_found = True
                # Fallback: Use the summary if the description is missing.
                elif summary:
                    description_parts.append(
                        f"Context from parent issue {context_key}: {summary}"
                    )
                    context_found = True

            # Final Fallback: If the issue or context could not be found.
            if not context_found:
                description_parts.append(
                    f"Context from parent issue: {context_key} (Could not retrieve details)."
                )

        elif task.context:
            # Original logic for plain text context from Confluence.
            description_parts.append(f"Context from Confluence:\n{task.context}")

        # Add metadata about the task creation for traceability.
        description_parts.append(
            f"Created by {user_name} on {creation_time} requested by {context.request_user}"
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

        # Ensure the summary does not exceed Jira's maximum character limit.
        summary = task.task_summary or "No Summary Provided"
        if len(summary) > config.JIRA_SUMMARY_MAX_CHARS:
            logger.warning(
                f"Task summary is too long ({len(summary)} > {config.JIRA_SUMMARY_MAX_CHARS}). "
                f"Truncating summary for Confluence Task ID: {task.confluence_task_id}."
            )
            summary = summary[: config.JIRA_SUMMARY_MAX_CHARS - 3] + "..."
        # Ensure the description does not exceed Jira's maximum character limit.
        description = final_description or "No Description Provided"
        if len(description) > config.JIRA_DESCRIPTION_MAX_CHARS:
            logger.warning(
                f"Task description is too long ({len(description)} > {config.JIRA_DESCRIPTION_MAX_CHARS}). "
                f"Truncating description for Confluence Task ID: {task.confluence_task_id}. "
            )
            description = description[: config.JIRA_DESCRIPTION_MAX_CHARS - 3] + "..."
        # Prepare the fields for the Jira issue creation.
        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"id": config.TASK_ISSUE_TYPE_ID},
            "description": description,
            "duedate": due_date,
            "assignee": {"name": task.assignee_name},
            config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
        }

        # The final payload MUST be a simple fields
        return fields

    async def search_issues_by_jql(
        self, jql_query: str, fields: str = "*all"
    ) -> List[Dict[str, Any]]:
        """Delegates JQL search to the API layer asynchronously."""
        return await self._api.search_issues(jql_query, fields=fields)  # Await API call

    async def get_issue_type_name_by_id(self, type_id: str) -> Optional[str]:
        """
        Retrieves the name of a Jira issue type by its ID asynchronously.
        Delegates to the API layer.
        """
        issue_type_details = await self._api.get_issue_type_details_by_id(
            type_id
        )  # Await API call
        return issue_type_details.get("name") if issue_type_details else None

    async def get_issue_status(self, issue_key: str) -> Optional[JiraIssueStatus]:
        """
        Asynchronously retrieves the status of a Jira issue.
        """
        try:
            issue_data = await self._api.get_issue(issue_key, fields=["status"])
            status_info = issue_data.get("fields", {}).get("status", {})
            if status_info:
                return JiraIssueStatus(
                    name=status_info.get("name"),
                    category=status_info.get("statusCategory", {}).get("key"),
                )
        except Exception as e:
            logger.error(f"Could not retrieve status for Jira issue {issue_key}: {e}")
        return None

    async def get_jira_issue(self, issue_key: str) -> Optional[JiraIssue]:
        """
        Asynchronously retrieves a full Jira issue.
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
        except Exception as e:
            logger.error(f"Could not retrieve full Jira issue {issue_key}: {e}")
        return None
