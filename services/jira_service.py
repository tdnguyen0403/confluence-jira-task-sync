from typing import Optional, Dict, Any, List

from atlassian import Jira
import config
from interfaces.api_service_interface import ApiServiceInterface
from models.data_models import ConfluenceTask
from api.safe_jira_api import SafeJiraApi

class JiraService(ApiServiceInterface):
    """Thin service layer for Jira, implementing the unified API interface."""

    def __init__(self, safe_jira_api: SafeJiraApi):
        self._api = safe_jira_api

    def get_issue(self, issue_key: str, fields: str = "*all") -> Optional[Dict[str, Any]]:
        return self._api.get_issue(issue_key, fields)

    def create_issue(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._api.create_issue(fields)

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        return self._api.transition_issue(issue_key, target_status)

    def prepare_jira_task_fields(self, task: ConfluenceTask, parent_key: str) -> Dict[str, Any]:
        description = f"Source Confluence Page: [{task.confluence_page_title}|{task.confluence_page_url}]"
        fields = {
            "project": {"key": config.JIRA_PROJECT_KEY}, "summary": task.task_summary,
            "issuetype": {"id": config.TASK_ISSUE_TYPE_ID}, "description": description,
            "duedate": task.due_date, config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
        }
        if task.assignee_name:
            fields["assignee"] = {"name": task.assignee_name}
        return fields

    # --- Methods from interface not applicable to Jira ---
    def get_page_id_from_url(self, url: str) -> Optional[str]: raise NotImplementedError
    def get_all_descendants(self, page_id: str) -> List[str]: raise NotImplementedError
    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool: raise NotImplementedError
    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]: raise NotImplementedError
    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None: raise NotImplementedError
    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]: raise NotImplementedError