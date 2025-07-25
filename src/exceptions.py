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


class SyncError(AutomationError):
    """Exception raised for errors during the task synchronization process."""

    pass


class UndoError(AutomationError):
    """Exception raised for errors during the undo process."""

    pass


class InvalidInputError(AutomationError):
    """Exception raised for invalid or malformed input data provided to an endpoint."""

    pass


class MissingRequiredDataError(AutomationError):
    """Exception raised when essential data for an operation is missing."""

    pass


class JiraConfluenceError(Exception):
    """Exception raised for low-level API errors from Jira or Confluence."""

    pass
