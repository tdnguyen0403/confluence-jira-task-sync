from typing import Optional, Dict, Any, List

from atlassian import Confluence
from src.interfaces.api_service_interface import ApiServiceInterface
from src.models.data_models import ConfluenceTask
from src.api.safe_confluence_api import SafeConfluenceApi

class ConfluenceService(ApiServiceInterface):
    """Thin service layer for Confluence, implementing the unified API interface."""

    def __init__(self, safe_confluence_api: SafeConfluenceApi):
        self._api = safe_confluence_api

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        return self._api.get_page_id_from_url(url)

    def get_all_descendants(self, page_id: str) -> List[str]:
        return self._api.get_all_descendants(page_id)

    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        return self._api.get_page_by_id(page_id, **kwargs)

    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool:
        return self._api.update_page(page_id, new_title, new_body)
        
    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]:
        return self._api.get_tasks_from_page(page_details)
        
    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None:
        return self._api.update_page_with_jira_links(page_id, mappings)
        
    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self._api.create_page(**kwargs)
        
    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return self._api.get_user_details_by_username(username)

    # --- Methods from interface not applicable to Confluence ---
    def get_issue(self, issue_key: str, fields: str = "*all") -> Optional[Dict[str, Any]]: raise NotImplementedError
    def create_issue(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def transition_issue(self, issue_key: str, target_status: str) -> bool: raise NotImplementedError
    def prepare_jira_task_fields(self, task: ConfluenceTask, parent_key: str) -> Dict[str, Any]: raise NotImplementedError
    def get_current_user_display_name(self) -> str: raise NotImplementedError