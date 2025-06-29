"""
Defines the data structures used throughout the application.

This module contains dataclasses that represent the core entities of the
automation workflow, such as tasks found in Confluence and the results of
processing those tasks. Using dataclasses provides a clear, concise, and
type-safe way to manage this data.
"""

from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional


@dataclass
class ConfluenceTask:
    """
    Represents a single, structured task item extracted from a Confluence page.

    Attributes:
        confluence_page_id (str): The ID of the page where the task was found.
        confluence_page_title (str): The title of the page.
        confluence_page_url (str): The web URL to the Confluence page.
        confluence_task_id (str): The unique ID of the task within Confluence.
        task_summary (str): The descriptive text of the task.
        status (str): The status of the task (e.g., 'complete', 'incomplete').
        assignee_name (Optional[str]): The username of the person assigned to
                                       the task, if any.
        due_date (str): The due date of the task in 'YYYY-MM-DD' format.
        original_page_version (int): The version number of the page when the
                                     task was extracted.
        original_page_version_by (str): The display name of the user who made
                                        the last version of the page.
        original_page_version_when (str): The timestamp of the last version.
        context (Optional[str]): The surrounding contextual information
                                 (e.g., parent headings) for the task.
    """

    confluence_page_id: str
    confluence_page_title: str
    confluence_page_url: str
    confluence_task_id: str
    task_summary: str
    status: str
    assignee_name: Optional[str]
    due_date: str
    original_page_version: int
    original_page_version_by: str
    original_page_version_when: str
    context: Optional[str] = None


@dataclass
class PageUpdateMapping:
    """
    Maps a Confluence task to the Jira issue key it was replaced with.

    This structure is used to track which tasks have been successfully
    processed and converted into Jira issues, so the Confluence page can be
    updated accordingly.

    Attributes:
        confluence_task_id (str): The unique ID of the task in Confluence.
        jira_key (str): The key of the newly created Jira issue.
    """

    confluence_task_id: str
    jira_key: str


@dataclass
class AutomationResult:
    """
    Represents the final outcome of processing a single Confluence task.

    This class encapsulates the original task data along with the results of
    the automation, such as the status of the operation and the key of any
    newly created Jira issue.

    Attributes:
        task_data (ConfluenceTask): The original task data that was processed.
        status (str): A summary of the outcome (e.g., 'SUCCESS', 'SKIPPED').
        new_jira_key (Optional[str]): The key of the Jira issue created from
                                      this task, if any.
        linked_work_package (Optional[str]): The parent work package the new
                                             Jira issue was linked to.
        request_user (Optional[str]): The name of the user who requested the sync.
    """

    task_data: ConfluenceTask
    status: str
    new_jira_key: Optional[str] = None
    linked_work_package: Optional[str] = None
    request_user: Optional[str] = None # Renamed from requested_by

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the automation result into a dictionary for reporting.

        This method flattens the nested `ConfluenceTask` object to create a
        single-level dictionary, which is ideal for writing to CSV or other
        tabular formats.

        Returns:
            Dict[str, Any]: A dictionary representing the flattened result.
        """
        # Start with the fields from the AutomationResult class itself.
        result_dict = {
            "Status": self.status,
            "New Jira Task Key": self.new_jira_key,
            "Linked Work Package": self.linked_work_package,
            "Request User": self.request_user, # Renamed key for output
        }

        # Iterate over the fields of the nested ConfluenceTask dataclass
        # and add them to the dictionary.
        for f in fields(self.task_data):
            result_dict[f.name] = getattr(self.task_data, f.name)

        # Ensure the context is included.
        result_dict["context"] = self.task_data.context

        return result_dict