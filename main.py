from typing import List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import httpx  # Import httpx for lifespan management
import json  # Import json for file operations
import uuid
# import urllib3 # Remove or comment out this line once SSL is properly handled

from src.dependencies import (
    get_sync_task_orchestrator,
    get_undo_sync_task_orchestrator,
    get_https_helper,  # To manage httpx client lifespan
    get_safe_jira_api,  # For readiness probe
    get_safe_confluence_api,  # For readiness probe
    get_api_key,  # For API key validation
    get_confluence_issue_updater_service,  # For /sync_project endpoint
)
from src.models.data_models import (
    SyncRequest,
    UndoRequestItem,
    ConfluenceUpdateProjectRequest,  # Added for /sync_project request
    SyncProjectPageDetail,  # Added for /sync_project response
)
from src.exceptions import (
    SyncError,
    InvalidInputError,
    UndoError,
    MissingRequiredDataError,
)
from src.utils.logging_config import setup_logging  # For logging setup in endpoints
from src.utils.dir_helpers import (  # For file operations
    generate_timestamped_filename,
    get_input_path,
    get_output_path,
)

logger = logging.getLogger(__name__)

# Remove or comment out this line once SSL is properly handled (even in dev)
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Lifespan context manager for managing resources like httpx client
@asynccontextmanager
async def lifespan(app: FastAPI):
    http_helper = None
    try:
        logger.info("Application starting up...")
        http_helper = get_https_helper()
        http_helper.client = httpx.AsyncClient(
            verify=getattr(http_helper, "_verify_ssl", True), cookies=httpx.Cookies()
        )
    except Exception:
        logger.exception("Error during app startup.")
    yield  # Always yield, even if startup fails
    try:
        logger.info("Application shutting down...")
        if (
            http_helper
            and hasattr(http_helper, "client")
            and hasattr(http_helper.client, "aclose")
        ):
            await http_helper.client.aclose()
        logger.info("Application shutdown complete.")
    except Exception:
        logger.exception("Error during app shutdown.")


app = FastAPI(
    title="Jira-Confluence Automation API",
    description="API for synchronizing tasks from Confluence to Jira and undoing previous runs.",
    version="1.0.0",
    lifespan=lifespan,  # Apply lifespan to the app
)


# --- Custom Exception Handlers (from previous recommendations) ---
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
        content={
            "message": "An unexpected internal server error occurred. Please try again later or contact support."
        },
    )


# --- API Endpoints ---
@app.post(
    "/sync_task",
    summary="Synchronize Confluence tasks to Jira",
    response_model=List[
        Dict[str, Any]
    ],  # Changed to List[Dict[str, Any]] to match the output
    dependencies=[Depends(get_api_key)],
)
async def sync_task(
    request: SyncRequest,
    sync_orchestrator=Depends(get_sync_task_orchestrator),
):
    """
    Initiates the synchronization process to extract incomplete tasks from
    specified Confluence pages (and their descendants) and create corresponding
    Jira tasks.
    """
    # Setup logging for this specific request
    setup_logging(
        log_file_prefix="sync_task_run",
        endpoint_name="sync_task",
        user=request.context.request_user,
    )
    request_id = uuid.uuid4().hex
    # Get a logger instance for this request context
    current_request_logger = logging.getLogger("")
    current_request_logger.info(
        f"Received /sync_task request for user: {request.context.request_user} with {len(request.confluence_page_urls)} URLs for request id {request_id}"
    )

    sync_input = request.model_dump()  # Use model_dump for Pydantic model to dict
    try:
        input_filename = generate_timestamped_filename(
            "sync_task_request", suffix=".json", user=request.context.request_user
        )
        input_path = get_input_path("sync_task", input_filename)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sync_input, f, ensure_ascii=False, indent=4)
        current_request_logger.info(f"Input request saved to '{input_filename}'")
    except Exception as e:
        current_request_logger.error(
            f"Failed to save input request to file: {e} for request id {request_id}",
            exc_info=True,
        )

    try:
        # The orchestrator's run method populates its internal self.results
        await sync_orchestrator.run(
            sync_input, request.context
        )  # Await the orchestrator run
        response_results = [
            res.to_dict() for res in sync_orchestrator.results
        ]  # Convert AutomationResult to dict

        if response_results:
            output_filename = generate_timestamped_filename(
                "sync_task_result", suffix=".json", user=request.context.request_user
            )
            output_path = get_output_path("sync_task", output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(response_results, f, indent=4)
            current_request_logger.info(f"Results have been saved to '{output_path}'")
            current_request_logger.info(
                f"Sync run completed. Processed {len(response_results)} tasks for request id {request_id}"
            )
            return response_results
        else:
            current_request_logger.info(
                f"Sync run completed, but no actionable tasks were processed for request id {request_id}"
            )
            return []

    except InvalidInputError as e:
        current_request_logger.error(
            f"Invalid input for sync operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Request: {e} for request id {request_id}",
        )
    except MissingRequiredDataError as e:
        current_request_logger.error(
            f"Missing required data for sync operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing Data: {e} for request id {request_id}",
        )
    except SyncError as e:
        current_request_logger.error(
            f"Sync operation failed: {e} for request id {request_id}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synchronization failed due to an internal error: {e} for request id {request_id}",
        )
    except Exception as e:
        current_request_logger.error(
            f"An unexpected error occurred during sync operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e} for request id {request_id}",
        )


@app.post(
    "/undo_sync_task",
    summary="Undo a previous synchronization run",
    response_model=Dict[str, str],  # Original response model was Dict[str, str]
    dependencies=[Depends(get_api_key)],
)
async def undo_sync_task(  # Original function name: undo_sync_run (renamed to undo_sync_task for consistency)
    undo_data: List[UndoRequestItem],  # Original parameter name: undo_data
    undo_orchestrator=Depends(get_undo_sync_task_orchestrator),
):
    """
    Reverts actions from a previous synchronization run by transitioning
    created Jira tasks back to 'Backlog' and rolling back modified Confluence pages.
    Requires the full JSON results from a previous /sync_task run.
    """
    setup_logging(
        log_file_prefix="undo_sync_task_run",
        endpoint_name="undo_sync_task",
        user=undo_data[0].request_user
        if undo_data and undo_data[0].request_user
        else "unknown",  # Use request_user from first item
    )
    request_id = uuid.uuid4().hex
    current_request_logger = logging.getLogger("")
    current_request_logger.info(
        f"Received /undo_sync_task request for {len(undo_data)} entries for request id {request_id}"
    )

    try:
        input_filename = generate_timestamped_filename(
            "undo_sync_task_request",
            suffix=".json",
            user=undo_data[0].request_user
            if undo_data and undo_data[0].request_user
            else "unknown",
        )
        input_path = get_input_path("undo_sync_task", input_filename)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(
                [item.model_dump(by_alias=True) for item in undo_data], f, indent=4
            )
        current_request_logger.info(
            f"Input request saved to '{input_path}' for request id {request_id}"
        )

        await undo_orchestrator.run(
            [item.model_dump(by_alias=True) for item in undo_data]
        )  # Await orchestrator run

        current_request_logger.info("Undo run completed.")
        return {
            "message": f"Undo operation completed successfully for request id {request_id}"
        }
    except InvalidInputError as e:
        current_request_logger.error(
            f"Invalid input for undo operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Request: {e} for request id {request_id}",
        )
    except MissingRequiredDataError as e:
        current_request_logger.error(
            f"Missing required data in results for undo operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed Results Data: {e} for request id {request_id}",
        )
    except UndoError as e:
        current_request_logger.error(
            f"Undo operation failed: {e} for request id {request_id}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Undo operation failed due to an internal error: {e} for request id {request_id}",
        )
    except Exception as e:
        current_request_logger.error(
            f"An unexpected error occurred during undo operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e} for request id {request_id}",
        )


@app.post(
    "/sync_project",  # Restored /sync_project endpoint
    summary="Update embedded Jira project/phase/work package issues on Confluence pages",
    response_model=List[SyncProjectPageDetail],
    dependencies=[Depends(get_api_key)],
)
async def update_confluence_project(
    request: ConfluenceUpdateProjectRequest,
    confluence_issue_updater_service=Depends(
        get_confluence_issue_updater_service
    ),  # Use Depends with get_confluence_issue_updater_service
):
    """
    Updates existing Jira issue macros (Project, Phase, Work Package types)
    on a Confluence page hierarchy to link to a new Jira project key.
    """
    setup_logging(
        log_file_prefix="sync_project_run",
        endpoint_name="sync_project",
        user=request.request_user,
    )
    request_id = uuid.uuid4().hex
    current_request_logger = logging.getLogger("")
    current_request_logger.info(
        f"Received /sync_project request for root URL: {request.root_confluence_page_url} to find issues under root project: {request.root_project_issue_key} for request id {request_id}"
    )

    try:
        input_filename = generate_timestamped_filename(
            "sync_project_request", suffix=".json", user=request.request_user
        )
        input_path = get_input_path("sync_project", input_filename)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(request.model_dump(), f, indent=4)
        current_request_logger.info(
            f"Input request saved to '{input_path}' for request id {request_id}"
        )

        # Await the asynchronous service call
        updated_pages_summary = await confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project(
            root_confluence_page_url=request.root_confluence_page_url,
            root_project_issue_key=request.root_project_issue_key,
            project_issue_type_id=request.project_issue_type_id,
            phase_issue_type_id=request.phase_issue_type_id,
        )
        if updated_pages_summary:
            # Convert SyncProjectPageDetail objects to dictionaries for JSON serialization
            serializable_summary = [item.model_dump() for item in updated_pages_summary]
            output_filename = generate_timestamped_filename(
                "sync_project_result", suffix=".json", user=request.request_user
            )
            output_path = get_output_path("sync_project", output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(serializable_summary, f, indent=4)
            current_request_logger.info(
                f"Update process completed. Modified {len(updated_pages_summary)} pages for request id {request_id}."
            )
            return updated_pages_summary
        else:
            current_request_logger.info(
                f"Update process completed, but no pages were modified for request id {request_id}."
            )
            return []

    except InvalidInputError as e:
        current_request_logger.error(
            f"Invalid input for update operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Request: {e} for request id {request_id}",
        )
    except SyncError as e:
        current_request_logger.error(
            f"Confluence update failed: {e} for request id {request_id}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confluence update failed due to an internal error: {e} for request id {request_id}",
        )
    except Exception as e:
        current_request_logger.error(
            f"An unexpected error occurred during Confluence update operation: {e} for request id {request_id}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e} for request id {request_id}",
        )


@app.get("/", include_in_schema=False)
async def read_root():
    return {
        "message": "Welcome to the Jira-Confluence Automation API. Visit /docs for API documentation."
    }


# --- Health Checks (from previous recommendations) ---
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Liveness probe: Checks if the application is running."""
    return {"status": "ok", "message": "Application is alive."}


@app.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    jira_api_dep=Depends(get_safe_jira_api),
    confluence_api_dep=Depends(get_safe_confluence_api),
):
    """
    Readiness probe: Checks if the application is ready to serve requests,
    including connectivity to external dependencies.
    """
    setup_logging(log_file_prefix="api_readiness_check", endpoint_name="api")
    try:
        await jira_api_dep.get_current_user()
        logger.info("Jira API is reachable and authenticated.")

        await confluence_api_dep.get_all_spaces()
        logger.info("Confluence API is reachable and authenticated.")

        return {"status": "ready", "message": "Application and dependencies are ready."}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Dependencies not ready: {e}",
        )
