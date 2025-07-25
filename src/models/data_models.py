"""
Defines the Pydantic data models used throughout the application.

This module centralizes all data structures for request and response bodies,
as well as for internal data representation. Using Pydantic models ensures
robust data validation, serialization, and clear, self-documenting code.
The models cover entities from Confluence and Jira, synchronization contexts,
and API request/response schemas.
"""
# jira_confluence_automator_/src/models/data_models.py

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConfluenceTask(BaseModel):
    """
    Represents a single, structured task item extracted from a Confluence page.

    This model is used to standardize the data retrieved from Confluence tasks,
    providing a consistent structure for processing.

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

        This method flattens the nested `ConfluenceTask` data into the main
        dictionary, making it suitable for logging or generating reports.

        Returns:
            Dict[str, Any]: A dictionary representing the flattened result.
        """
        result_dict = {
            "status_text": self.status_text,
            "new_jira_task_key": self.new_jira_task_key,
            "linked_work_package": self.linked_work_package,
            "request_user": self.request_user,
        }

        task_data_dict = self.task_data.model_dump()

        result_dict.update(task_data_dict)

        return result_dict


class SyncContext(BaseModel):
    """

    Holds all contextual information for a single synchronization request.

    This model can be extended with additional parameters without requiring
    changes to the API endpoint signature, providing flexibility for future
    enhancements.

    Attributes:
        request_user (Optional[str]): The user who initiated the request.
        days_to_due_date (Optional[int]): The default number of days to set
                                          for a task's due date if not specified.
    """

    request_user: Optional[str] = "Unknown User"
    days_to_due_date: Optional[int] = 14


class SyncRequest(BaseModel):
    """
    Represents the request body for the /sync endpoint.

    Attributes:
        confluence_page_urls (List[str]): A list of Confluence page URLs to be
                                          processed.
        context (SyncContext): Contextual settings for the synchronization.
    """

    confluence_page_urls: List[str] = Field(
        ...,
        json_schema_extra={
            "example": ["https://your.confluence.com/display/SPACE/PageName"]
        },
    )
    context: SyncContext = Field(default_factory=SyncContext)


class UndoRequestItem(BaseModel):
    """
    Represents an item in the request body for the /undo_sync_task endpoint.

    This model is used to parse the results from a previous sync operation
    to identify Jira tasks that need to be deleted and Confluence pages that
    should be rolled back to a previous version.

    Attributes:
        status_text (str): The status from the original automation result.
        confluence_page_id (str): The ID of the Confluence page to roll back.
        original_page_version (int): The version to which the page should be restored.
        new_jira_task_key (Optional[str]): The key of the Jira task to be deleted.
        linked_work_package (Optional[str]): The parent work package (for logging).
        request_user (Optional[str]): The user who requested the original sync.
        (and other fields from the flattened AutomationResult)
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


class ConfluenceUpdateProjectRequest(BaseModel):
    """
    Represents the request body for the /update-confluence-project endpoint.

    Attributes:
        root_confluence_page_url (str): URL of the root Confluence page for the project.
        root_project_issue_key (str): The key of the top-level Jira project issue.
        project_issue_type_id (Optional[str]): The ID for Jira "Project" issue types.
        phase_issue_type_id (Optional[str]): The ID for Jira "Phase" issue types.
        request_user (Optional[str]): The user initiating the update.
    """

    root_confluence_page_url: str = Field(
        ...,
        json_schema_extra={
            "example": "https://your.confluence.com/display/SPACE/RootPage"
        },
    )
    root_project_issue_key: str = Field(..., json_schema_extra={"example": "PROJ-1"})
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
    """
    Represents the result of updating a single Confluence page during a project sync.

    Attributes:
        page_id (str): The ID of the Confluence page.
        page_title (str): The title of the Confluence page.
        new_jira_keys (List[str]): The Jira issue keys created/updated on this page.
        root_project_linked (str): The main project Jira key linked at the root.
    """

    page_id: str = Field(..., description="The ID of the Confluence page.")
    page_title: str = Field(..., description="The title of the Confluence page.")
    new_jira_keys: List[str] = Field(
        ...,
        description="The Jira issue keys that were created or updated on this page.",
    )
    root_project_linked: str = Field(
        ..., description="The Jira issue key of the main project linked to the root."
    )


class JiraIssueStatus(BaseModel):
    """
    Represents the status of a Jira issue.

    Attributes:
        name (str): The name of the status (e.g., 'To Do', 'In Progress', 'Done').
        category (str): The category of the status (e.g., 'new', 'indeterminate', 'done').
    """

    name: str = Field(
        ..., description="The name of the status (e.g., 'To Do', 'Done')."
    )
    category: str = Field(
        ...,
        description="The category of the status (e.g., 'new', 'indeterminate', 'done').",
    )


class JiraIssue(BaseModel):
    """
    Represents a simplified Jira issue object for internal use.

    Attributes:
        key (str): The issue key (e.g., 'PROJ-123').
        summary (str): The issue summary.
        status (JiraIssueStatus): The issue's current status.
        issue_type (str): The name of the issue type (e.g., 'Task', 'Bug').
    """

    key: str = Field(..., description="The issue key (e.g., 'PROJ-123').")
    summary: str = Field(..., description="The issue summary.")
    status: JiraIssueStatus = Field(..., description="The issue's current status.")
    issue_type: str = Field(
        ..., description="The name of the issue type (e.g., 'Task', 'Bug')."
    )


class JiraIssueMacro(BaseModel):
    """
    Represents a Jira macro found in Confluence page HTML.

    Attributes:
        issue_key (str): The Jira issue key embedded in the macro.
        macro_html (str): The full HTML string of the Confluence Jira macro.
    """

    issue_key: str = Field(..., description="The Jira issue key embedded in the macro.")
    macro_html: str = Field(
        ..., description="The full HTML string of the Confluence Jira macro."
    )


class SyncTaskResponse(BaseModel):
    """
    Defines the response model for the /sync_task endpoint.

    Attributes:
        request_id (str): A unique identifier for the synchronization request.
        results (List[Dict[str, Any]]): A list of dictionaries, each representing
                                        an `AutomationResult`.
    """

    request_id: str
    results: List[Dict[str, Any]]


class UndoSyncTaskResponse(BaseModel):
    """
    Defines the response model for the /undo_sync_task endpoint.

    Attributes:
        request_id (str): A unique identifier for the undo request.
        message (str): A confirmation message indicating the result of the undo operation.
    """

    request_id: str
    message: str


class SyncProjectResponse(BaseModel):
    """
    Defines the response model for the /sync_project endpoint.

    Attributes:
        request_id (str): A unique identifier for the project sync request.
        results (List[SyncProjectPageDetail]): A list of details for each page
                                               that was updated.
    """

    request_id: str
    results: List[SyncProjectPageDetail]
