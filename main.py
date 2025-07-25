from typing import List, Dict, Any, Callable
from fastapi import FastAPI, Depends, status, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import httpx
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

from src.dependencies import (
    get_sync_task_orchestrator,
    get_undo_sync_task_orchestrator,
    get_https_helper,
    get_safe_jira_api,
    get_safe_confluence_api,
    get_api_key,
    get_confluence_issue_updater_service,
)
from src.models.data_models import (
    SyncRequest,
    UndoRequestItem,
    ConfluenceUpdateProjectRequest,
    SyncProjectPageDetail,
)
from src.exceptions import (
    SyncError,
    InvalidInputError,
    UndoError,
    MissingRequiredDataError,
)
from src.utils.logging_config import setup_logging, request_id_var, endpoint_var

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging on application startup
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
    description="API for synchronizing tasks from Confluence to Jira and undoing previous runs.",
    version="1.0.0",
    lifespan=lifespan,
)


# Middleware to inject request_id and endpoint into logs
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        # Generate a unique request ID
        req_id = uuid.uuid4().hex
        request_id_var.set(req_id)

        # Get endpoint name from the request path
        endpoint_name = request.url.path
        endpoint_var.set(endpoint_name)

        logger.info(
            f"Request started for user: {request.headers.get('user-agent', 'unknown')}"
        )

        response = await call_next(request)

        # Add request_id to response headers
        response.headers["X-Request-ID"] = req_id
        logger.info(f"Request finished with status code: {response.status_code}")

        return response


app.add_middleware(LoggingMiddleware)


# --- Global Exception Handlers ---
@app.exception_handler(InvalidInputError)
async def invalid_input_exception_handler(request: Request, exc: InvalidInputError):
    logger.warning(f"Invalid input received: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"message": str(exc)},
    )


@app.exception_handler(SyncError)
async def sync_error_exception_handler(request: Request, exc: SyncError):
    logger.error(f"Synchronization error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": f"Synchronization failed: {exc}"},
    )


@app.exception_handler(UndoError)
async def undo_error_exception_handler(request: Request, exc: UndoError):
    logger.error(f"Undo error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": f"Undo operation failed: {exc}"},
    )


@app.exception_handler(MissingRequiredDataError)
async def missing_data_exception_handler(
    request: Request, exc: MissingRequiredDataError
):
    logger.warning(f"Missing required data: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": str(exc)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An unexpected internal server error occurred."},
    )


# --- API Endpoints ---
@app.post(
    "/sync_task",
    summary="Synchronize Confluence tasks to Jira",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(get_api_key)],
)
async def sync_task(
    request: SyncRequest,
    sync_orchestrator=Depends(get_sync_task_orchestrator),
):
    """
    Initiates the synchronization process to extract incomplete tasks from
    specified Confluence pages and create corresponding Jira tasks.
    """
    logger.info(
        f"Received /sync_task request for user: {request.context.request_user} "
        f"with {len(request.confluence_page_urls)} URLs."
    )

    sync_input = request.model_dump()
    response_results_objects = await sync_orchestrator.run(sync_input, request.context)
    response_results = [res.to_dict() for res in response_results_objects]

    if response_results:
        logger.info(f"Sync run completed. Processed {len(response_results)} tasks.")
    else:
        logger.info("Sync run completed, but no actionable tasks were processed.")

    return response_results


@app.post(
    "/undo_sync_task",
    summary="Undo a previous synchronization run",
    response_model=Dict[str, str],
    dependencies=[Depends(get_api_key)],
)
async def undo_sync_task(
    undo_data: List[UndoRequestItem],
    undo_orchestrator=Depends(get_undo_sync_task_orchestrator),
):
    """
    Reverts actions from a previous synchronization run.
    """
    user = undo_data[0].request_user if undo_data else "unknown"
    logger.info(
        f"Received /undo_sync_task request for user {user} with {len(undo_data)} items."
    )

    await undo_orchestrator.run([item.model_dump(by_alias=True) for item in undo_data])

    logger.info("Undo run completed successfully.")
    return {"message": "Undo operation completed successfully."}


@app.post(
    "/sync_project",
    summary="Update embedded Jira project issues on Confluence pages",
    response_model=List[SyncProjectPageDetail],
    dependencies=[Depends(get_api_key)],
)
async def update_confluence_project(
    request: ConfluenceUpdateProjectRequest,
    confluence_issue_updater_service=Depends(get_confluence_issue_updater_service),
):
    """
    Updates existing Jira issue macros on a Confluence page hierarchy.
    """
    logger.info(
        f"Received /sync_project request for user {request.request_user} on root URL: "
        f"{request.root_confluence_page_url}"
    )

    updated_pages_summary = await confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project(
        root_confluence_page_url=request.root_confluence_page_url,
        root_project_issue_key=request.root_project_issue_key,
        project_issue_type_id=request.project_issue_type_id,
        phase_issue_type_id=request.phase_issue_type_id,
    )

    if updated_pages_summary:
        logger.info(
            f"Update process completed. Modified {len(updated_pages_summary)} pages."
        )
    else:
        logger.info("Update process completed, but no pages were modified.")

    return updated_pages_summary


@app.get("/", include_in_schema=False)
async def read_root():
    return {
        "message": "Welcome to the Jira-Confluence Automation API. Visit /docs for API documentation."
    }


# --- Health Checks ---
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Liveness probe: Checks if the application is running."""
    return {"status": "ok", "message": "Application is alive."}


@app.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    jira_api_dep=Depends(get_safe_jira_api),
    confluence_api_dep=Depends(get_safe_confluence_api),
):
    """Readiness probe: Checks connectivity to external dependencies."""
    logger.info("Performing readiness check...")
    await jira_api_dep.get_current_user()
    logger.info("Jira API is reachable and authenticated.")
    await confluence_api_dep.get_all_spaces()
    logger.info("Confluence API is reachable and authenticated.")
    return {"status": "ready", "message": "Application and dependencies are ready."}
