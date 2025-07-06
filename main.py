import logging
import warnings
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field # Keep for general use if needed elsewhere

# Import existing components
from src.config import config
from src.utils.logging_config import setup_logging
from src.exceptions import SyncError, MissingRequiredDataError, InvalidInputError, UndoError
from src.dependencies import get_api_key, container # Corrected: Import the container and get_api_key
from src.models.data_models import SyncRequest, UndoRequestItem # Corrected: Import both models from data_models

# Suppress insecure request warnings, common in corporate/dev environments.
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)

# Initialize application-wide logging
setup_logging("logs/logs_api", "api_run")
logger = logging.getLogger(__name__)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Jira-Confluence Automation API",
    description="API for synchronizing tasks from Confluence to Jira and undoing previous runs.",
    version="1.0.0",
)

# --- Removed Pydantic Models for Request Bodies - now imported from data_models.py ---
# The actual Pydantic models for request/response bodies are defined in src/models/data_models.py

# --- API Endpoints ---
@app.post("/sync", summary="Synchronize Confluence tasks to Jira", response_model=List[UndoRequestItem], dependencies=[Depends(get_api_key)])
async def sync_confluence_tasks(
    request: SyncRequest,
    sync_orchestrator = Depends(container.sync_orchestrator) # Corrected: Use container
):
    """
    Initiates the synchronization process to extract incomplete tasks from
    specified Confluence pages (and their descendants) and create corresponding
    Jira tasks.
    """
    logger.info(f"Received /sync request for user: {request.request_user} with {len(request.confluence_page_urls)} URLs.")
    
    sync_input = request.model_dump() # Corrected: Use model_dump() for Pydantic V2

    # --- Code to save the input request to a file ---
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_filename = f"sync_request_{timestamp}_{request.request_user}.json"
        input_filepath = os.path.join(config.INPUT_DIRECTORY, input_filename)
        os.makedirs(config.INPUT_DIRECTORY, exist_ok=True)
        with open(input_filepath, "w", encoding="utf-8") as f:
            json.dump(sync_input, f, ensure_ascii=False, indent=4)
        logger.info(f"Input request saved to '{input_filepath}'")
    except Exception as e:
        logger.error(f"Failed to save input request to file: {e}", exc_info=True)
    
    try:
        sync_orchestrator.run(sync_input)
        
        response_results = [res.to_dict() for res in sync_orchestrator.results]
        
        if not response_results:
            logger.info("Sync run completed, but no actionable tasks were processed.")
            return []
        logger.info(f"Sync run completed. Processed {len(response_results)} tasks.")
        return response_results
        
    except InvalidInputError as e:
        logger.error(f"Invalid input for sync operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Request: {e}"
        )
    except MissingRequiredDataError as e:
        logger.error(f"Missing required data for sync operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing Data: {e}"
        )
    except SyncError as e:
        logger.error(f"Sync operation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synchronization failed due to an internal error: {e}"
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred during sync operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e}"
        )

@app.post("/undo", summary="Undo a previous synchronization run", response_model=Dict[str, str], dependencies=[Depends(get_api_key)])
async def undo_sync_run(
    results_data: List[UndoRequestItem],
    undo_orchestrator = Depends(container.undo_orchestrator) # Corrected: Use container
):
    """
    Reverts actions from a previous synchronization run by transitioning
    created Jira tasks back to 'Backlog' and rolling back modified Confluence pages.
    Requires the full JSON results from a previous /sync run.
    """
    logger.info(f"Received /undo request for {len(results_data)} entries.")

    try:
        undo_orchestrator.run([item.model_dump(by_alias=True) for item in results_data]) # Corrected: Use model_dump()
        logger.info("Undo run completed.")
        return {"message": "Undo operation completed successfully. Please check logs for details."}
    except InvalidInputError as e:
        logger.error(f"Invalid input for undo operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Request: {e}"
        )
    except MissingRequiredDataError as e:
        logger.error(f"Missing required data in results for undo operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed Results Data: {e}"
        )
    except UndoError as e:
        logger.error(f"Undo operation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Undo operation failed due to an internal error: {e}"
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred during undo operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred: {e}"
        )

@app.get("/", include_in_schema=False)
async def read_root():
    return {"message": "Welcome to the Jira-Confluence Automation API. Visit /docs for API documentation."}