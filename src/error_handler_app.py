# File: src/error_handler_app.py

"""
Centralized exception handlers for the FastAPI application.

This module contains all the custom exception handler functions that are
registered with the FastAPI application instance in main.py. Centralizing
them here makes the main application file cleaner and easier to maintain.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.exceptions import (
    AutomationError,
    InvalidInputError,
    MissingRequiredDataError,
    ParentIssueNotFoundError,
    SetupError,
    SyncError,
    UndoError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI):
    """
    Registers all custom exception handlers with the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(InvalidInputError, invalid_input_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        ParentIssueNotFoundError,
        parent_issue_not_found_error_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(SetupError, setup_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SyncError, sync_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(UndoError, undo_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(MissingRequiredDataError, missing_data_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AutomationError, general_automation_error_handler)  # type: ignore[arg-type]


async def invalid_input_error_handler(request: Request, exc: InvalidInputError):
    """Handles errors from invalid request body format."""
    logger.warning(f"Invalid input provided: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": f"Invalid input: {exc}"},
    )


async def parent_issue_not_found_error_handler(
    request: Request, exc: ParentIssueNotFoundError
):
    """Handles failure to find a required parent entity (e.g., Work Package)."""
    logger.error(f"A required parent issue was not found: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def setup_error_handler(request: Request, exc: SetupError):
    """Handles generic errors during the pre-processing/setup phase."""
    logger.warning(f"Request setup failed: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": f"Request setup failed: {exc}"},
    )


async def sync_error_handler(request: Request, exc: SyncError):
    """Handles errors during the main synchronization workflow."""
    logger.error(f"Synchronization process error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An error occurred during synchronization: {exc}"},
    )


async def undo_error_handler(request: Request, exc: UndoError):
    """Handles errors specifically from the undo workflow."""
    logger.error(f"Undo process error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An error occurred during the undo process: {exc}"},
    )


async def missing_data_exception_handler(
    request: Request, exc: MissingRequiredDataError
):
    """Handles `MissingRequiredDataError` exceptions globally."""
    logger.warning(f"Missing required data: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def general_automation_error_handler(request: Request, exc: AutomationError):
    """A final catch-all for any other application-specific errors."""
    logger.critical(f"An unexpected automation error occurred: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An unexpected internal error occurred: {exc}"},
    )
