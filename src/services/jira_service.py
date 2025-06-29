from typing import Optional, Dict, Any, List
from datetime import datetime

from atlassian import Jira
from src.config import config
from src.interfaces.api_service_interface import ApiServiceInterface
from src.models.data_models import ConfluenceTask
from src.api.safe_jira_api import SafeJiraApi

class JiraService(ApiServiceInterface):
    """Thin service layer for Jira, implementing the unified API interface."""

    def __init__(self, safe_jira_api: SafeJiraApi):
        self._api = safe_jira_api
        self._current_user_name: Optional[str] = None

    def get_issue(self, issue_key: str, fields: str = "*all") -> Optional[Dict[str, Any]]:
        return self._api.get_issue(issue_key, fields)

    def create_issue(self, task: ConfluenceTask, parent_key: str) -> Optional[str]:
        issue_fields = self.prepare_jira_task_fields(task, parent_key)
        new_issue = self._api.create_issue(issue_fields)
        return new_issue if new_issue else None

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        return self._api.transition_issue(issue_key, target_status)

    def get_current_user_display_name(self) -> str:
        """
        Gets the display name of the logged-in user, caches it for efficiency.
        """
        if self._current_user_name is None:
            user_details = self._api.get_myself()
            if user_details and "displayName" in user_details:
                self._current_user_name = user_details["displayName"]
            else:
                self._current_user_name = "Unknown User" # Fallback
        return self._current_user_name
        
    def prepare_jira_task_fields(self, task: ConfluenceTask, parent_key: str) -> Dict[str, Any]:
        """
        Prepares the fields for a new Jira issue, including the detailed description.
        """
        user_name = self.get_current_user_display_name()
        creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Start with the context from the extractor
        description_parts = []
        if task.context:
            description_parts.append(f"Context from Confluence:\n{task.context}")
        
        # Add the creation metadata
        description_parts.append(f"Created by {user_name} on {creation_time}")
        
        # Join all parts for the final description
        final_description = "\n\n".join(description_parts)

        fields = {
            "project": {"key": config.JIRA_PROJECT_KEY},
            "summary": task.task_summary,
            "issuetype": {"id": config.TASK_ISSUE_TYPE_ID},
            "description": final_description, # <-- USE THE NEW DESCRIPTION
            "duedate": task.due_date,
            config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
        }
        if task.assignee_name:
            fields["assignee"] = {"name": task.assignee_name}
        return {"fields": fields}

    # --- Methods from interface not applicable to Jira ---
    def get_page_id_from_url(self, url: str) -> Optional[str]: raise NotImplementedError
    def get_all_descendants(self, page_id: str) -> List[str]: raise NotImplementedError
    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool: raise NotImplementedError
    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]: raise NotImplementedError
    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None: raise NotImplementedError
    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]: raise NotImplementedError