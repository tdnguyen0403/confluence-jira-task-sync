import logging
import warnings
import json
from typing import List, Dict

import requests
from fastapi import FastAPI, HTTPException, status, Depends

from src.utils.logging_config import setup_logging
from src.utils.dir_helpers import (
    generate_timestamped_filename,
    get_input_path,
    get_output_path,
)
from src.exceptions import (
    SyncError,
    MissingRequiredDataError,
    InvalidInputError,
    UndoError,
)
from src.dependencies import get_api_key, container
from src.models.data_models import (
    SyncRequest,
    UndoRequestItem,
    ConfluenceUpdateProjectRequest,
    SyncProjectPageDetail,
)
from src.services.orchestration.sync_task_orchestrator import (
    SyncTaskOrchestrator,
)  # New import
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)  # New import


warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)

app = FastAPI(
    title="Jira-Confluence Automation API",
    description="API for synchronizing tasks from Confluence to Jira and undoing previous runs.",
    version="1.0.0",
)


@app.post(
    "/sync_task",
    summary="Synchronize Confluence tasks to Jira",
    response_model=List[UndoRequestItem],
    dependencies=[Depends(get_api_key)],
)
async def sync_confluence_tasks(
    request: SyncRequest,
    sync_orchestrator: SyncTaskOrchestrator = Depends(
        container.sync_orchestrator
    ),  # Updated type hint
):
    """
    Initiates the synchronization process to extract incomplete tasks from
    specified Confluence pages (and their descendants) and create corresponding
    Jira tasks.
    """
    setup_logging(
        log_level=logging.INFO,
        log_file_prefix="sync_task_run",
        endpoint_name="sync_task",
        user=request.request_user,
    )
    logger = logging.getLogger("")
    logger.info(
        f"Received /sync request for user: {request.request_user} with {len(request.confluence_page_urls)} URLs."
    )

    sync_input = request.model_dump()

    try:
        input_filename = generate_timestamped_filename(
            "sync_task_request", suffix=".json", user=request.request_user
        )
        input_path = get_input_path("sync_task", input_filename)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sync_input, f, ensure_ascii=False, indent=4)
        logger.info(f"Input request saved to '{input_filename}'")
    except Exception as e:
        logger.error(f"Failed to save input request to file: {e}", exc_info=True)

    try:
        sync_orchestrator.run(sync_input)
        response_results = [res.to_dict() for res in sync_orchestrator.results]

        if response_results:
            output_filename = generate_timestamped_filename(
                "sync_task_result", suffix=".json", user=request.request_user
            )
            output_path = get_output_path("sync_task", output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(response_results, f, indent=4)
            logger.info(f"Results have been saved to '{output_path}'")
            logger.info(f"Sync run completed. Processed {len(response_results)} tasks.")
            return response_results
        else:
            logger.info("Sync run completed, but no actionable tasks were processed.")
            return []

    except InvalidInputError as e:
        logger.error(f"Invalid input for sync operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Request: {e}"
        )
    except MissingRequiredDataError as e:
        logger.error(f"Missing required data for sync operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing Data: {e}"
        )
    except SyncError as e:
        logger.error(f"Sync operation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synchronization failed due to an internal error: {e}",
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during sync operation: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e}",
        )


@app.post(
    "/undo_sync_task",
    summary="Undo a previous synchronization run",
    response_model=Dict[str, str],
    dependencies=[Depends(get_api_key)],
)
async def undo_sync_run(
    undo_data: List[UndoRequestItem],
    undo_orchestrator: UndoSyncTaskOrchestrator = Depends(
        container.undo_orchestrator
    ),  # Updated type hint
):
    """
    Reverts actions from a previous synchronization run by transitioning
    created Jira tasks back to 'Backlog' and rolling back modified Confluence pages.
    Requires the full JSON results from a previous /sync run.
    """
    setup_logging(
        log_level=logging.INFO,
        log_file_prefix="undo_sync_task_run",
        endpoint_name="undo_sync_task",
    )
    logger = logging.getLogger("")
    logger.info(f"Received /undo request for {len(undo_data)} entries.")

    try:
        input_filename = generate_timestamped_filename(
            "undo_sync_task_request", suffix=".json"
        )
        input_path = get_input_path("undo_sync_task", input_filename)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(
                [item.model_dump(by_alias=True) for item in undo_data], f, indent=4
            )
        undo_orchestrator.run([item.model_dump(by_alias=True) for item in undo_data])

        logger.info("Undo run completed.")
        return {"message": "Undo operation completed successfully."}
    except InvalidInputError as e:
        logger.error(f"Invalid input for undo operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Request: {e}"
        )
    except MissingRequiredDataError as e:
        logger.error(
            f"Missing required data in results for undo operation: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed Results Data: {e}",
        )
    except UndoError as e:
        logger.error(f"Undo operation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Undo operation failed due to an internal error: {e}",
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during undo operation: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e}",
        )


@app.post(
    "/sync_project",
    summary="Update embedded Jira project/phase/work package issues on Confluence pages",
    response_model=List[SyncProjectPageDetail],
    dependencies=[Depends(get_api_key)],
)
async def update_confluence_project(
    request: ConfluenceUpdateProjectRequest,
    confluence_issue_updater_service=Depends(
        container.confluence_issue_updater_service
    ),
):
    """
    Updates existing Jira issue macros (Project, Phase, Work Package types)
    on a Confluence page hierarchy to link to a new Jira project key.
    """
    setup_logging(
        log_level=logging.INFO,
        log_file_prefix="sync_project_run",
        endpoint_name="sync_project",
        user=request.request_user,
    )
    logger = logging.getLogger("")
    logger.info(
        f"Received /sync_project request for root URL: {request.root_confluence_page_url} to find issues under root project: {request.root_project_issue_key}"
    )

    try:
        input_filename = generate_timestamped_filename(
            "sync_project_request", suffix=".json", user=request.request_user
        )
        input_path = get_input_path("sync_project", input_filename)
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(request.model_dump(), f, indent=4)
        logger.info(f"Undo request saved to '{input_path}'")

        updated_pages_summary = confluence_issue_updater_service.update_confluence_hierarchy_with_new_jira_project(
            root_confluence_page_url=request.root_confluence_page_url,
            root_project_issue_key=request.root_project_issue_key,
            project_issue_type_id=request.project_issue_type_id,
            phase_issue_type_id=request.phase_issue_type_id,
        )
        if updated_pages_summary:
            output_filename = generate_timestamped_filename(
                "sync_project_result", suffix=".json", user=request.request_user
            )
            output_path = get_output_path("sync_project", output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(updated_pages_summary, f, indent=4)
            logger.info(
                f"Update process completed. Modified {len(updated_pages_summary)} pages."
            )
            return updated_pages_summary
        else:
            logger.info("Update process completed, but no pages were modified.")
            return []

    except InvalidInputError as e:
        logger.error(f"Invalid input for update operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Request: {e}"
        )
    except SyncError as e:
        logger.error(f"Confluence update failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confluence update failed due to an internal error: {e}",
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during Confluence update operation: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e}",
        )


@app.get("/", include_in_schema=False)
async def read_root():
    return {
        "message": "Welcome to the Jira-Confluence Automation API. Visit /docs for API documentation."
    }
