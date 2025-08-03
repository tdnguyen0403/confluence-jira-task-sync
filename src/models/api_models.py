"""
Defines the Pydantic data models used for API requests and responses.
Using Pydantic models ensures robust data validation, serialization,
and clear, self-documenting code. The models cover synchronization tasks,
project updates, and undo operations for Confluence and Jira integration.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.data_models import ConfluenceTask

# ---API Request Models---#


class SyncTaskContext(BaseModel):
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

    request_user: Optional[str] = "unknown_user"
    days_to_due_date: Optional[int] = 14


class SyncTaskRequest(BaseModel):
    """
    Represents the request body for the /sync endpoint.

    Attributes:
        confluence_page_urls (List[str]): A list of Confluence page URLs to be
            processed.
        context (SyncTaskContext): Contextual settings for the synchronization.
    """

    confluence_page_urls: List[str] = Field(
        ...,
        json_schema_extra={
            "example": ["https://your.confluence.com/display/SPACE/PageName"]
        },
    )
    context: SyncTaskContext = Field(default_factory=SyncTaskContext)


class UndoSyncTaskRequest(BaseModel):
    """
    Represents an item in the request body for the /undo_sync_task endpoint.
    Simplified to contain only information necessary for the undo operation.

    Attributes:
        confluence_page_id (str): The ID of the Confluence page to roll back.
        original_page_version (int): The version to which the page should be
            restored.
        new_jira_task_key (Optional[str]): The key of the Jira task to be deleted.
        request_user (Optional[str]): The user who requested the original sync.
    """

    confluence_page_id: Optional[str] = None
    original_page_version: Optional[int] = None
    new_jira_task_key: Optional[str] = Field(
        None, json_schema_extra={"example": "JIRA-123"}
    )
    request_user: Optional[str] = Field(None, json_schema_extra={"example": "username"})


class SyncProjectRequest(BaseModel):
    """
    Represents the request body for the /update-confluence-project endpoint.

    Attributes:
        project_page_url (str): URL of the root Confluence page for the
            project.
        project_key (str): The key of the top-level Jira project issue.
        request_user (Optional[str]): The user initiating the update.
    """

    project_page_url: str = Field(
        ...,
        json_schema_extra={
            "example": "https://your.confluence.com/display/SPACE/RootPage"
        },
    )
    project_key: str = Field(..., json_schema_extra={"example": "PROJ-1"})
    request_user: Optional[str] = Field(
        ..., json_schema_extra={"example": "your.username"}
    )


# ---Internal Orchestrator Result (not direct API response model for /sync_task)---#


class SingleTaskResult(BaseModel):  # Renamed from SyncTaskResult
    """
    Represents the internal outcome of processing a single Confluence task
    within the orchestrator. This model is primarily used to aggregate data
    before constructing the final JiraTaskCreationResult for the API response.
    """

    task_data: ConfluenceTask
    status_text: str
    new_jira_task_key: Optional[str] = None
    linked_work_package: Optional[str] = None
    request_user: Optional[str] = None


# ---API Response Models---#


class JiraTaskCreationResult(BaseModel):
    """
    Represents the outcome of attempting to create a single Jira task.
    This model will now be the direct response item for the /sync_task endpoint.
    """

    confluence_page_id: str
    confluence_task_id: str
    task_summary: str
    original_page_version: int  # Crucial for page undo
    request_user: Optional[str] = None  # For undo context and audit

    new_jira_task_key: Optional[str] = None
    creation_status_text: str = Field(
        ...,
        description="""The outcome message of the Jira task creation attempt
        (e.g., 'Success', 'Failed - No Work Package found').""",
    )
    success: bool
    error_message: Optional[str] = None


class ConfluencePageUpdateResult(BaseModel):
    """
    Represents the outcome of attempting to update a single Confluence page
    with new Jira links. This is an internal result from the orchestrator
    that is no longer returned directly in
    SyncTaskResponse (which is now List[JiraTaskCreationResult]).
    Its info might be logged or handled separately if needed by client.
    """

    page_id: str
    page_title: str
    updated: bool
    error_message: Optional[str] = None
    jira_keys_replaced: List[str] = Field(default_factory=list)


class SyncTaskResponse(BaseModel):
    """
    Defines the comprehensive response model for the /sync_task endpoint,
    combining Jira task creation and Confluence page update results.
    """

    request_id: str = Field(
        ..., description="A unique identifier for the synchronization request."
    )
    overall_status: str = Field(
        ..., description="Overall status of both Jira & Confluence update"
    )
    overall_jira_task_creation_status: str = Field(
        ...,
        description="""Overall status of Jira task creation
        (Success, Partial Success, Failed, Skipped - No tasks processed).""",
    )
    overall_confluence_page_update_status: str = Field(
        ...,
        description="""Overall status of Confluence page updates
            (Success, Partial Success, Failed, Skipped - No updates needed).""",
    )
    jira_task_creation_results: List[JiraTaskCreationResult] = Field(
        default_factory=list,
        description="Detailed results for each Jira task creation attempt.",
    )
    confluence_page_update_results: List[ConfluencePageUpdateResult] = Field(
        default_factory=list,
        description="Detailed results for each Confluence page update attempt.",
    )


class UndoActionResult(BaseModel):
    """
    Represents the outcome of a single undo action
    (Jira transition or Confluence rollback).
    """

    action_type: str = Field(
        ...,
        description="Type of undo action ('jira_transition', 'confluence_rollback').",
    )
    target_id: str = Field(
        ..., description="ID of item targeted (Jira Key or Confluence Page ID)."
    )
    success: bool
    status_message: str = Field(
        ..., description="A message describing the outcome of the action."
    )
    error_message: Optional[str] = None


class UndoSyncTaskResponse(BaseModel):
    """
    Defines the response model for the /undo_sync_task endpoint,
    containing individual results for each undo action.
    """

    request_id: str
    results: List[UndoActionResult] = Field(default_factory=list)
    overall_status: str = Field(
        ...,
        description="""Overall status of the undo operation
        (Success, Partial Success, Failed).""",
    )


class SinglePageResult(BaseModel):
    """
    Represents the result of updating a single Confluence page during a project sync.

    Attributes:
        page_id (str): The ID of the Confluence page.
        page_title (str): The title of the Confluence page.
        new_jira_keys (List[str]): The Jira issue keys created/updated on this
            page.
        project_linked (str): The main project Jira key linked at the root.
    """

    page_id: str = Field(..., description="The ID of the Confluence page.")
    page_title: str = Field(..., description="The title of the Confluence page.")
    new_jira_keys: List[str] = Field(
        ...,
        description="The Jira issue keys that were created or updated on this page.",
    )
    project_linked: str = Field(
        ..., description="The Jira issue key of the main project linked to the root."
    )


class SyncProjectResponse(BaseModel):
    """
    Defines the response model for the /sync_project endpoint.

    Attributes:
        request_id (str): A unique identifier for the project sync request.
        results (List[SinglePageResult]): A list of details for each page
            that was updated.
    """

    request_id: str
    results: List[SinglePageResult]
