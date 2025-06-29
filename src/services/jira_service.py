"""
Provides a high-level service for interacting with Jira.

This module contains the `JiraService`, which acts as the business logic
layer for Jira operations. It implements the unified `ApiServiceInterface`
and uses the `SafeJiraApi` for its underlying calls.

The service is responsible for preparing and creating Jira issues based on
Confluence task data, handling issue transitions, and retrieving user
information. It explicitly marks Confluence-related methods from the
interface as not implemented.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.interfaces.api_service_interface import ApiServiceInterface
from src.models.data_models import ConfluenceTask


class JiraService(ApiServiceInterface):
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

    def get_issue(self, issue_key: str,
                  fields: str = "*all") -> Optional[Dict[str, Any]]:
        """Delegates fetching a Jira issue to the API layer."""
        return self._api.get_issue(issue_key, fields)

    def create_issue(self, task: ConfluenceTask,
                     parent_key: str) -> Optional[str]:
        """
        Creates a new Jira issue from a Confluence task.

        Args:
            task (ConfluenceTask): The task data from Confluence.
            parent_key (str): The key of the parent issue (e.g., Work Package).

        Returns:
            Optional[str]: The key of the newly created issue, or None on failure.
        """
        issue_fields = self.prepare_jira_task_fields(task, parent_key)
        new_issue = self._api.create_issue(issue_fields)
        return new_issue if new_issue else None

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """Delegates transitioning a Jira issue to the API layer."""
        return self._api.transition_issue(issue_key, target_status)

    def get_current_user_display_name(self) -> str:
        """
        Gets the display name of the logged-in user, with caching.

        This method retrieves the user's display name on the first call and
        caches it for subsequent requests to improve efficiency.

        Returns:
            str: The user's display name, or a 'Unknown User' as a fallback.
        """
        if self._current_user_name is None:
            user_details = self._api.get_myself()
            if user_details and "displayName" in user_details:
                self._current_user_name = user_details["displayName"]
            else:
                self._current_user_name = "Unknown User"  # Fallback
        return self._current_user_name

    def prepare_jira_task_fields(self, task: ConfluenceTask,
                                 parent_key: str) -> Dict[str, Any]:
        """
        Prepares the field structure for creating a new Jira issue.

        This method constructs the full payload required by the Jira API,
        including a detailed description that combines contextual information
        from Confluence with metadata about the task's creation. The project
        key is dynamically determined from the parent issue's key.

        Args:
            task (ConfluenceTask): The source Confluence task.
            parent_key (str): The key of the parent Jira issue (e.g., 'WP-1').

        Returns:
            Dict[str, Any]: A dictionary of fields ready for the API.
        """
        user_name = self.get_current_user_display_name()
        creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Dynamically determine the project key from the parent issue key.
        # For "WP-1", the project key will be "WP".
        project_key = parent_key.split("-")[0]

        description_parts = []

        if task.context and task.context.startswith("JIRA_KEY_CONTEXT::"):
            context_key = task.context.split("::")[1]
            
            # Fetch the parent issue, requesting both description and summary.
            context_issue = self._api.get_issue(context_key, fields="description,summary")
            
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
        description_parts.append(f"Created by {user_name} on {creation_time}")

        final_description = "\n\n".join(description_parts)

        fields = {
            "project": {"key": project_key},  # Dynamically set project key
            "summary": task.task_summary,
            "issuetype": {"id": config.TASK_ISSUE_TYPE_ID},
            "description": final_description,
            "duedate": task.due_date,
            config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
        }
        if task.assignee_name:
            fields["assignee"] = {"name": task.assignee_name}

        # The final payload must be nested under a "fields" key.
        return {"fields": fields}

    # --- Methods from interface not applicable to a Jira-only service ---

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def get_all_descendants(self, page_id: str) -> List[str]:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def get_page_by_id(self, page_id: str,
                       **kwargs) -> Optional[Dict[str, Any]]:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def update_page_content(self, page_id: str, new_title: str,
                            new_body: str) -> bool:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def get_tasks_from_page(self,
                              page_details: Dict) -> List[ConfluenceTask]:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def update_page_with_jira_links(self, page_id: str,
                                    mappings: List[Dict]) -> None:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Not implemented for JiraService."""
        raise NotImplementedError

    def get_user_details_by_username(self,
                                     username: str) -> Optional[Dict[str, Any]]:
        """Not implemented for JiraService."""
        raise NotImplementedError
