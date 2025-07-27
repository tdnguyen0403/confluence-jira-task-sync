"""
Defines the Pydantic data models used for API requests and responses.
Using Pydantic models ensures robust data validation, serialization,
and clear, self-documenting code. The models cover synchronization tasks,
project updates, and undo operations for Confluence and Jira integration.
"""

from typing import Any, Dict, List, Optional

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

    This model is used to parse the results from a previous sync operation
    to identify Jira tasks that need to be deleted and Confluence pages that
    should be rolled back to a previous version.

    Attributes:
        status_text (str): The status from the original automation result.
        confluence_page_id (str): The ID of the Confluence page to roll back.
        original_page_version (int): The version to which the page should be
            restored.
        new_jira_task_key (Optional[str]): The key of the Jira task to be deleted.
        linked_work_package (Optional[str]): The parent work package (for logging).
        request_user (Optional[str]): The user who requested the original sync.
        (and other fields from the flattened SingleTaskResult)
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


# ---API Response Models---#


class SingleTaskResult(BaseModel):
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


class SyncTaskResponse(BaseModel):
    """
    Defines the response model for the /sync_task endpoint.

    Attributes:
        request_id (str): A unique identifier for the synchronization request.
        results (List[Dict[str, Any]]): A list of dictionaries, each representing
            an `SingleTaskResult`.
    """

    request_id: str
    results: List[SingleTaskResult]


class UndoSyncTaskResponse(BaseModel):
    """
    Defines the response model for the /undo_sync_task endpoint.

    Attributes:
        request_id (str): A unique identifier for the undo request.
        detail (str): A confirmation detail indicating the result of the undo
            operation.
    """

    request_id: str
    detail: str


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
