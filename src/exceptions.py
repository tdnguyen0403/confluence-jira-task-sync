"""
Defines custom exception classes for the application.

This module establishes a hierarchy of custom exceptions that are used to
signal specific error conditions throughout the application. Using custom
exceptions allows for more granular error handling and clearer, more expressive
code in the service and API layers.
"""


class AutomationError(Exception):
    """Base exception for all application-specific errors."""

    pass


class ApiError(AutomationError):
    """Represents a failure in the underlying API communication layer."""

    def __init__(self, message: str, status_code: int = None, details: str = None):
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class JiraApiError(ApiError):
    """Specific exception for Jira API failures."""

    pass


class ConfluenceApiError(ApiError):
    """Specific exception for Confluence API failures."""

    pass


class SetupError(AutomationError):
    """Base exception for errors during the setup or
    precondition phase of an orchestration."""

    pass


class ParentIssueNotFoundError(SetupError):
    """Raised when the primary parent issue (e.g., Work Package) cannot be found."""

    pass


class SyncError(AutomationError):
    """Base exception for errors during the task synchronization process."""

    def __init__(self, message: str, confluence_page_id: str = None):
        self.confluence_page_id = confluence_page_id
        super().__init__(message)


class JiraTicketCreationError(SyncError):
    """Raised specifically when creating a Jira ticket fails."""

    pass


class ConfluencePageUpdateError(SyncError):
    """
    Raised when updating the Confluence page fails *after* a Jira ticket
    has already been successfully created. This indicates a potential
    inconsistent state.
    """

    def __init__(self, message: str, confluence_page_id: str, jira_keys: list[str]):
        self.jira_keys = jira_keys
        super().__init__(message, confluence_page_id)


class UndoError(AutomationError):
    """Exception raised for errors during the undo process."""

    pass


class InvalidInputError(AutomationError):
    """Exception raised for invalid or malformed input data provided to an endpoint."""

    pass


class MissingRequiredDataError(AutomationError):
    """Exception raised when essential data for an operation is missing."""

    pass
