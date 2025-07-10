"""
Custom exception classes for the Jira-Confluence automation application.
"""


class AutomationError(Exception):
    """Base exception for all application-specific errors."""

    pass


class SyncError(AutomationError):
    """Exception raised for errors during the synchronization process."""

    pass


class UndoError(AutomationError):
    """Exception raised for errors during the undo process."""

    pass


class InvalidInputError(AutomationError):
    """Exception raised for invalid or malformed input data."""

    pass


class MissingRequiredDataError(AutomationError):
    """Exception raised when essential data (e.g., Work Package) is missing."""

    pass


class JiraConfluenceError(Exception):
    """Exception raised for all api errors by requests to Jira or Confluence."""

    pass
