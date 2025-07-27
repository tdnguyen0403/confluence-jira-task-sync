"""
Defines the Pydantic data models used for internal data representation

Using Pydantic models ensures robust data validation, serialization,
and clear, self-documenting code. The models cover entities from Confluence and Jira
"""

from typing import Optional

from pydantic import BaseModel, Field

# ---Confluence related data model--- #


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


# ---Jira related data model--- #


class JiraIssueStatus(BaseModel):
    """
    Represents the status of a Jira issue.

    Attributes:
        name (str): The name of the status (e.g., 'To Do', 'In Progress', 'Done').
        category (str): The category of the status (e.g., 'new', 'indeterminate',
            'done').
    """

    name: str = Field(
        ..., description="The name of the status (e.g., 'To Do', 'Done')."
    )
    category: str = Field(
        ...,
        description="The category of the status (e.g., 'new', 'indeterminate', 'done').",  # noqa: E501
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
