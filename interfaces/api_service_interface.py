from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

from models.data_models import ConfluenceTask

class ApiServiceInterface(ABC):
    """
    A single, consolidated interface for API-related services.
    Note: This design forces implementing classes to have methods they may not use,
    which is a trade-off for having a single interface as requested.
    """

    # Jira Methods
    @abstractmethod
    def get_issue(self, issue_key: str, fields: str = "*all") -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_issue(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        pass

    @abstractmethod
    def prepare_jira_task_fields(self, task: ConfluenceTask, parent_key: str) -> Dict[str, Any]:
        pass
   
    @abstractmethod
    def get_current_user_display_name(self) -> str: # <-- ADD THIS METHOD
        pass

    # Confluence Methods
    @abstractmethod
    def get_page_id_from_url(self, url: str) -> Optional[str]:
        pass

    @abstractmethod
    def get_all_descendants(self, page_id: str) -> List[str]:
        pass
        
    @abstractmethod
    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        pass
        
    @abstractmethod
    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool:
        pass
        
    @abstractmethod
    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]:
        pass
        
    @abstractmethod
    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None:
        pass
        
    @abstractmethod
    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        pass
        
    @abstractmethod
    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        pass