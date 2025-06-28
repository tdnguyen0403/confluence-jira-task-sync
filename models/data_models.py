from dataclasses import dataclass, fields # Correctly import 'fields'
from typing import Optional, Dict, Any, List

@dataclass
class ConfluenceTask:
    """Represents a task item found on a Confluence page."""
    confluence_page_id: str
    confluence_page_title: str
    confluence_page_url: str
    confluence_task_id: str
    task_summary: str
    assignee_name: Optional[str]
    due_date: str
    original_page_version: int
    original_page_version_by: str
    original_page_version_when: str

@dataclass
class PageUpdateMapping:
    """Maps a Confluence task to the Jira key it was replaced with."""
    confluence_task_id: str
    jira_key: str

@dataclass
class AutomationResult:
    """Represents the outcome of processing a single Confluence task."""
    task_data: ConfluenceTask
    status: str
    new_jira_key: Optional[str] = None
    linked_work_package: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts the result to a dictionary for reporting."""
        # Start with the fields from this class
        d = {
            "Status": self.status,
            "New Jira Task Key": self.new_jira_key,
            "Linked Work Package": self.linked_work_package
        }
        
        # CORRECTED: Use fields() instead of field() to iterate
        # and correctly unpack the nested ConfluenceTask dataclass
        for f in fields(self.task_data):
            d[f.name] = getattr(self.task_data, f.name)
            
        return d
