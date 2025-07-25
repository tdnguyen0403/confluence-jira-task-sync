# jira_confluence_automator_/src/models/data_models.py

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# models used for the /sync endpoint
class ConfluenceTask(BaseModel):
    """
    Represents a single, structured task item extracted from a Confluence page.
    Now a Pydantic BaseModel for enhanced validation and serialization.

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
    due_date: Optional[str] = None
    original_page_version: int
    original_page_version_by: str
    original_page_version_when: str
    context: Optional[str] = None


class PageUpdateMapping(BaseModel):
    """
    Maps a Confluence task to the Jira issue key it was replaced with.
    Now a Pydantic BaseModel for consistency.

    This structure is used to track which tasks have been successfully
    processed and converted into Jira issues, so the Confluence page can be
    updated accordingly.

    Attributes:
        confluence_task_id (str): The unique ID of the task in Confluence.
        jira_key (str): The key of the newly created Jira issue.
    """

    confluence_task_id: str
    jira_key: str


class AutomationResult(BaseModel):
    """
    Represents the final outcome of processing a single Confluence task.
    Now a Pydantic BaseModel.

    This class encapsulates the original task data along with the results of
    the automation, such as the status of the operation and the key of any
    newly created Jira issue.

    Attributes:
        task_data (ConfluenceTask): The original task data that was processed.
        status_text (str): A summary of the outcome (e.g., 'SUCCESS', 'SKIPPED').
        new_jira_task_key (Optional[str]): The key of the Jira issue created from
                                      this task, if any.
        linked_work_package (Optional[str]): The parent work package the new
                                             Jira issue was linked to.
        request_user (Optional[str]): The name of the user who requested the sync.
    """

    task_data: ConfluenceTask
    status_text: str
    new_jira_task_key: Optional[str] = None
    linked_work_package: Optional[str] = None
    request_user: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the automation result into a dictionary for reporting.
        Leverages Pydantic's model_dump() for the nested task_data,
        and flattens the structure.

        Returns:
            Dict[str, Any]: A dictionary representing the flattened result.
        """
        # Start with the fields from the AutomationResult class itself.
        result_dict = {
            "status_text": self.status_text,
            "new_jira_task_key": self.new_jira_task_key,
            "linked_work_package": self.linked_work_package,
            "request_user": self.request_user,
        }

        # Use model_dump() on the nested Pydantic model for task_data
        # This will convert all fields of ConfluenceTask into a dictionary.
        task_data_dict = self.task_data.model_dump()

        # Merge task_data fields into the result_dict
        result_dict.update(task_data_dict)

        return result_dict


class SyncContext(BaseModel):
    """
    Holds all context for a single synchronization task request.
    This can be extended without changing the API endpoint.
    """

    request_user: Optional[str] = "Unknown User"
    days_to_due_date: Optional[int] = 14


class SyncRequest(BaseModel):
    """
    Represents the request body for the /sync endpoint.
    """

    confluence_page_urls: List[str] = Field(
        ...,
        json_schema_extra={
            "example": ["https://your.confluence.com/display/SPACE/PageName"]
        },
    )
    context: SyncContext = Field(default_factory=SyncContext)


# models used for the /undo endpoint
class UndoRequestItem(BaseModel):
    """
    Represents an item in the request body for the /undo_sync_task endpoint.
    This model is used to parse the results from a previous sync operation
    to identify Jira tasks to undo and Confluence pages to rollback.
    """

    status_text: str
    confluence_page_id: str
    original_page_version: int
    new_jira_task_key: Optional[str] = Field(
        None, json_schema_extra={"example": "JIRA-123"}
    )
    linked_work_package: Optional[str] = Field(
        None, json_schema_extra={"example": "WP-456"}
    )
    request_user: Optional[str] = Field(None, json_schema_extra={"example": "username"})
    confluence_page_title: Optional[str] = Field(
        None, json_schema_extra={"example": "My Confluence Page"}
    )
    confluence_page_url: Optional[str] = Field(
        None, json_schema_extra={"example": "https://confluence.example.com/page/123"}
    )
    confluence_task_id: Optional[str] = Field(
        None, json_schema_extra={"example": "task-abc"}
    )
    task_summary: Optional[str] = Field(
        None, json_schema_extra={"example": "Complete this task"}
    )
    status: Optional[str] = Field(None, json_schema_extra={"example": "Success"})
    assignee_name: Optional[str] = Field(None, json_schema_extra={"example": "jdoe"})
    due_date: Optional[str] = Field(None, json_schema_extra={"example": "2025-12-31"})
    original_page_version_by: Optional[str] = Field(
        None, json_schema_extra={"example": "jdoe"}
    )
    original_page_version_when: Optional[str] = Field(
        None, json_schema_extra={"example": "2024-07-05T10:00:00.000Z"}
    )
    context: Optional[str] = Field(
        None, json_schema_extra={"example": "Task within Section A"}
    )


# model used for the /update-confluence-project endpoint
class ConfluenceUpdateProjectRequest(BaseModel):
    """
    Represents the request body for the /update-confluence-project endpoint.
    """

    root_confluence_page_url: str = Field(
        ...,
        json_schema_extra={
            "example": "https://your.confluence.com/display/SPACE/RootPage"
        },
    )
    root_project_issue_key: str = Field(
        ..., json_schema_extra={"example": "PROJ-1"}
    )  # CHANGED
    project_issue_type_id: Optional[str] = Field(
        None, json_schema_extra={"example": "10000"}
    )
    phase_issue_type_id: Optional[str] = Field(
        None, json_schema_extra={"example": "10001"}
    )
    request_user: Optional[str] = Field(
        ..., json_schema_extra={"example": "your.username"}
    )


class SyncProjectPageDetail(BaseModel):
    """Represents the result of updating a single Confluence page during a project sync."""

    page_id: str = Field(..., description="The ID of the Confluence page.")
    page_title: str = Field(..., description="The title of the Confluence page.")
    new_jira_keys: List[str] = Field(
        ...,
        description="The Jira issue keys that were created or updated on this page.",
    )
    root_project_linked: str = Field(
        ..., description="The Jira issue key of the main project linked to the root."
    )


# New models for Jira API responses and internal representation
class JiraIssueStatus(BaseModel):
    """Represents the status of a Jira issue."""

    name: str = Field(
        ..., description="The name of the status (e.g., 'To Do', 'Done')."
    )
    category: str = Field(
        ...,
        description="The category of the status (e.g., 'new', 'indeterminate', 'done').",
    )


class JiraIssue(BaseModel):
    """Represents a simplified Jira issue object."""

    key: str = Field(..., description="The issue key (e.g., 'PROJ-123').")
    summary: str = Field(..., description="The issue summary.")
    status: JiraIssueStatus = Field(..., description="The issue's current status.")
    issue_type: str = Field(
        ..., description="The name of the issue type (e.g., 'Task', 'Bug')."
    )


class JiraIssueMacro(BaseModel):
    """Represents a Jira macro found in Confluence page HTML."""

    issue_key: str = Field(..., description="The Jira issue key embedded in the macro.")
    macro_html: str = Field(
        ..., description="The full HTML string of the Confluence Jira macro."
    )


class SyncTaskResponse(BaseModel):
    """Response model for the /sync_task endpoint, including a request ID."""

    request_id: str
    results: List[
        Dict[str, Any]
    ]  # List of dictionaries representing AutomationResult items


class UndoSyncTaskResponse(BaseModel):
    """Response model for the /undo_sync_task endpoint, including a request ID."""

    request_id: str
    message: str


class SyncProjectResponse(BaseModel):
    """Response model for the /sync_project endpoint, including a request ID."""

    request_id: str
    results: List[SyncProjectPageDetail]
