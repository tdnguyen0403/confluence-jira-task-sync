"""
Main entry point for the Jira-Confluence Automation FastAPI application.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Dict, List

import httpx
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.dependencies import (
    get_api_key,
    get_confluence_service,
    get_https_helper,
    get_jira_service,
    get_sync_project,
    get_sync_task,
    get_undo_sync_task,
)
from src.error_handler_app import register_exception_handlers
from src.interfaces.confluence_interface import IConfluenceService
from src.interfaces.jira_interface import IJiraService
from src.models.api_models import (
    SyncProjectRequest,
    SyncProjectResponse,
    SyncTaskRequest,
    SyncTaskResponse,
    UndoSyncTaskRequest,
    UndoSyncTaskResponse,
)
from src.services.orchestration.sync_project import SyncProjectService
from src.services.orchestration.sync_task import SyncTaskService
from src.services.orchestration.undo_sync_task import UndoSyncService
from src.utils.logging_config import endpoint_var, request_id_var, setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manages the application's lifespan events for resource management."""
    setup_logging()
    logger.info("Application starting up...")
    http_helper = get_https_helper()
    try:
        http_helper.client = httpx.AsyncClient(
            verify=getattr(http_helper, "_verify_ssl", True),
            cookies=httpx.Cookies(),
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
    """Middleware to inject a unique request ID and endpoint path into logs."""

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """
        Processes each incoming request to add logging context.
        """
        req_id = uuid.uuid4().hex
        request_id_var.set(req_id)
        endpoint_name = request.url.path
        endpoint_var.set(endpoint_name)

        user_agent = request.headers.get("user-agent", "unknown")
        logger.info(f"Request started for user: {user_agent}")

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

# Register all exception handlers
register_exception_handlers(app)


@app.post(
    "/sync_task",
    summary="Synchronize Confluence tasks to Jira",
    response_model=SyncTaskResponse,
    dependencies=[Depends(get_api_key)],
)
async def sync_task(
    request: SyncTaskRequest,
    sync_orchestrator: SyncTaskService = Depends(get_sync_task),
) -> SyncTaskResponse:
    """Initiates the synchronization of tasks from Confluence pages to Jira."""
    logger.info(
        f"Received /sync_task request for user: {request.context.request_user} "
        f"with {len(request.confluence_page_urls)} URLs."
    )

    request_id = request_id_var.get()
    assert request_id is not None
    response = await sync_orchestrator.run(
        request.model_dump(), request.context, request_id=request_id
    )

    logger.info(f"Sync run completed with overall status: {response.overall_status}")
    return response


@app.post(
    "/undo_sync_task",
    summary="Undo a previous synchronization run",
    response_model=UndoSyncTaskResponse,
    dependencies=[Depends(get_api_key)],
)
async def undo_sync_task(
    undo_data: List[UndoSyncTaskRequest],
    undo_orchestrator: UndoSyncService = Depends(get_undo_sync_task),
) -> UndoSyncTaskResponse:
    """Reverts the actions from a previous synchronization run."""
    user = undo_data[0].request_user if undo_data else "unknown"
    logger.info(
        f"Received /undo_sync_task request for user {user} with {len(undo_data)} items."
    )

    request_id = request_id_var.get()
    assert request_id is not None
    response = await undo_orchestrator.run(undo_data, request_id=request_id)

    logger.info(f"Undo run completed with overall status: {response.overall_status}.")
    return response


@app.post(
    "/sync_project",
    summary="Update embedded Jira project issues on Confluence pages",
    response_model=SyncProjectResponse,
    dependencies=[Depends(get_api_key)],
)
async def sync_project(
    request: SyncProjectRequest,
    confluence_updater: SyncProjectService = Depends(get_sync_project),
) -> SyncProjectResponse:
    """
    Updates existing Jira issue macros within a Confluence page hierarchy.
    """
    logger.info(
        f"Received /sync_project request for user {request.request_user} "
        f"on root URL: {request.project_page_url}"
    )

    updated_pages = await confluence_updater.sync_project(
        project_page_url=request.project_page_url,
        project_key=request.project_key,
    )

    if updated_pages:
        logger.info(f"Update process completed. Modified {len(updated_pages)} pages.")
    else:
        logger.info("Update process completed, but no pages were modified.")

    request_id = request_id_var.get()
    assert request_id is not None
    return SyncProjectResponse(request_id=request_id, results=updated_pages)


@app.get("/", include_in_schema=False)
async def read_root() -> Dict[str, str]:
    """Provides a simple welcome message at the root URL."""
    return {
        "message": "Welcome to the Jira-Confluence Automation API. "
        "Visit /docs for API documentation."
    }


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """Provides a liveness probe endpoint."""
    return {"status": "ok", "detail": "Application is alive."}


@app.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    jira_service: IJiraService = Depends(get_jira_service),
    confluence_service: IConfluenceService = Depends(get_confluence_service),
) -> Dict[str, str]:
    """Provides a readiness probe endpoint."""
    logger.info("Performing readiness check...")
    await jira_service.get_user_display_name()
    logger.info("Jira service is reachable and authenticated.")
    await confluence_service.health_check()
    logger.info("Confluence service is reachable and authenticated.")
    return {"status": "ready", "detail": "Application and dependencies are ready."}
