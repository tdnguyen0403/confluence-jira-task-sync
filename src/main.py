# File: src/main.py

"""
Main entry point for the Jira-Confluence Automation FastAPI application.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Callable, List

import httpx
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.dependencies import (
    get_api_key,
    get_confluence_issue_updater_service,
    get_https_helper,
    get_safe_confluence_api,
    get_safe_jira_api,
    get_sync_task_orchestrator,
    get_undo_sync_task_orchestrator,
)
from src.exceptions import (
    AutomationError,
    InvalidInputError,
    MissingRequiredDataError,
    ParentIssueNotFoundError,
    SetupError,
    SyncError,
    UndoError,
)
from src.models.api_models import (
    SyncProjectRequest,
    SyncProjectResponse,
    SyncTaskRequest,
    SyncTaskResponse,  # Now the comprehensive response model
    UndoSyncTaskRequest,
    UndoSyncTaskResponse,
)
from src.utils.logging_config import endpoint_var, request_id_var, setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's lifespan events for resource management.
    """
    setup_logging()
    logger.info("Application starting up...")
    http_helper = get_https_helper()
    try:
        http_helper.client = httpx.AsyncClient(
            verify=getattr(http_helper, "_verify_ssl", True), cookies=httpx.Cookies()
        )
    except Exception:
        logger.exception("Error creating httpx client during app startup.")

    yield

    logger.info("Application shutting down...")
    if (
        hasattr(http_helper, "client")
        and http_helper.client
        and hasattr(http_helper.client, "aclose")
    ):
        await http_helper.client.aclose()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Jira-Confluence Automation API",
    description="API for synchronizing tasks from Confluence to Jira",
    version="1.0.0",
    lifespan=lifespan,
)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject a unique request ID and endpoint path into logs.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        """
        Processes each incoming request to add logging context. It also serves
        as a final catch-all for unhandled exceptions due to framework limitations.
        """
        req_id = uuid.uuid4().hex
        request_id_var.set(req_id)
        endpoint_name = request.url.path
        endpoint_var.set(endpoint_name)

        logger.info(
            f"Request started for user: {request.headers.get('user-agent', 'unknown')}"
        )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            logger.info(f"Request finished with status code: {response.status_code}")
            return response
        except Exception:
            logger.critical("Unhandled exception caught in middleware", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "An unexpected internal server error occurred."},
            )


app.add_middleware(LoggingMiddleware)


@app.exception_handler(InvalidInputError)
async def invalid_input_error_handler(request: Request, exc: InvalidInputError):
    """Handles errors from invalid request body format."""
    logger.warning(f"Invalid input provided: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": f"Invalid input: {exc}"},
    )


@app.exception_handler(ParentIssueNotFoundError)
async def parent_issue_not_found_error_handler(
    request: Request, exc: ParentIssueNotFoundError
):
    """Handles failure to find a required parent entity (e.g., Work Package)."""
    logger.error(f"A required parent issue was not found: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


@app.exception_handler(SetupError)
async def setup_error_handler(request: Request, exc: SetupError):
    """Handles generic errors during the pre-processing/setup phase."""
    logger.warning(f"Request setup failed: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": f"Request setup failed: {exc}"},
    )


@app.exception_handler(SyncError)
async def sync_error_handler(request: Request, exc: SyncError):
    """Handles errors during the main synchronization workflow."""
    logger.error(f"Synchronization process error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An error occurred during synchronization: {exc}"},
    )


@app.exception_handler(UndoError)
async def undo_error_handler(request: Request, exc: UndoError):
    """Handles errors specifically from the undo workflow."""
    logger.error(f"Undo process error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An error occurred during the undo process: {exc}"},
    )


@app.exception_handler(MissingRequiredDataError)
async def missing_data_exception_handler(
    request: Request, exc: MissingRequiredDataError
):
    """Handles `MissingRequiredDataError` exceptions globally."""
    logger.warning(f"Missing required data: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


@app.exception_handler(AutomationError)
async def general_automation_error_handler(request: Request, exc: AutomationError):
    """A final catch-all for any other application-specific errors."""
    logger.critical(f"An unexpected automation error occurred: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"An unexpected internal error occurred: {exc}"},
    )


@app.post(
    "/sync_task",
    summary="Synchronize Confluence tasks to Jira",
    response_model=SyncTaskResponse,
    dependencies=[Depends(get_api_key)],
)
async def sync_task(
    request: SyncTaskRequest,
    sync_orchestrator=Depends(get_sync_task_orchestrator),
):
    """
    Initiates the synchronization of tasks from Confluence pages to Jira.
    """
    logger.info(
        f"Received /sync_task request for user: {request.context.request_user} "
        f"with {len(request.confluence_page_urls)} URLs."
    )

    # Orchestrator now returns a dictionary containing all parts for SyncTaskResponse
    orchestrator_results = await sync_orchestrator.run(
        request.model_dump(), request.context
    )  # noqa: E501

    # Extract results from the dictionary returned by the orchestrator
    overall_jira_status = orchestrator_results["overall_jira_task_creation_status"]
    overall_confluence_status = orchestrator_results[
        "overall_confluence_page_update_status"
    ]  # noqa: E501
    jira_creation_results = orchestrator_results["jira_task_creation_results"]
    confluence_page_update_results = orchestrator_results[
        "confluence_page_update_results"
    ]  # noqa: E501

    logger.info(
        f"Sync run completed. Jira Status: {overall_jira_status},"
        f"Confluence Status: {overall_confluence_status}"
    )
    logger.debug(f"Jira Task Creation Results: {len(jira_creation_results)} items")
    logger.debug(
        f"Confluence Page Update Results: {len(confluence_page_update_results)} items"
    )

    return SyncTaskResponse(  # Construct the comprehensive SyncTaskResponse
        request_id=request_id_var.get(),
        overall_jira_task_creation_status=overall_jira_status,
        overall_confluence_page_update_status=overall_confluence_status,
        jira_task_creation_results=jira_creation_results,
        confluence_page_update_results=confluence_page_update_results,
    )


@app.post(
    "/undo_sync_task",
    summary="Undo a previous synchronization run",
    response_model=UndoSyncTaskResponse,
    dependencies=[Depends(get_api_key)],
)
async def undo_sync_task(
    undo_data: List[UndoSyncTaskRequest],
    undo_orchestrator=Depends(get_undo_sync_task_orchestrator),
):
    """
    Reverts the actions from a previous synchronization run.
    """
    user = (
        undo_data[0].request_user
        if undo_data and undo_data[0].request_user
        else "unknown"
    )  # noqa: E501
    logger.info(
        f"Received /undo_sync_task request for user {user} with {len(undo_data)} items."
    )

    undo_action_results = await undo_orchestrator.run(undo_data)

    overall_status = undo_orchestrator._determine_overall_status(
        undo_action_results, lambda r: r.success
    )

    logger.info(f"Undo run completed with overall status: {overall_status}.")
    return UndoSyncTaskResponse(
        request_id=request_id_var.get(),
        results=undo_action_results,
        overall_status=overall_status,
    )


@app.post(
    "/sync_project",
    summary="Update embedded Jira project issues on Confluence pages",
    response_model=SyncProjectResponse,
    dependencies=[Depends(get_api_key)],
)
async def update_confluence_project(
    request: SyncProjectRequest,
    confluence_issue_updater_service=Depends(get_confluence_issue_updater_service),
):
    """
    Updates existing Jira issue macros within a Confluence page hierarchy.
    """
    logger.info(
        f"Received /sync_project request for user {request.request_user} on root URL: "
        f"{request.project_page_url}"
    )

    updated_pages_summary = await confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project(  # noqa: E501
        project_page_url=request.project_page_url,
        project_key=request.project_key,
    )

    if updated_pages_summary:
        logger.info(
            f"Update process completed. Modified {len(updated_pages_summary)} pages."
        )
    else:
        logger.info("Update process completed, but no pages were modified.")

    return SyncProjectResponse(
        request_id=request_id_var.get(), results=updated_pages_summary
    )


@app.get("/", include_in_schema=False)
async def read_root():
    """Provides a simple welcome message at the root URL."""
    return {
        """message": "Welcome to the Jira-Confluence Automation API.
        Visit /docs for API documentation."""
    }


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Provides a liveness probe endpoint.
    """
    return {"status": "ok", "detail": "Application is alive."}


@app.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    jira_api_dep=Depends(get_safe_jira_api),
    confluence_api_dep=Depends(get_safe_confluence_api),
):
    """
    Provides a readiness probe endpoint.
    """
    logger.info("Performing readiness check...")
    await jira_api_dep.get_current_user()
    logger.info("Jira API is reachable and authenticated.")
    await confluence_api_dep.get_all_spaces()
    logger.info("Confluence API is reachable and authenticated.")
    return {"status": "ready", "detail": "Application and dependencies are ready."}
