import logging
import warnings
from typing import List, Dict, Any, Optional

import requests
from fastapi import FastAPI, HTTPException, status, Depends, Security # Corrected: Security imported from fastapi
from pydantic import BaseModel, Field
from atlassian import Confluence, Jira
from fastapi.security import APIKeyHeader # Corrected: APIKeyHeader imported from fastapi.security

# Import existing components
from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.services.confluence_service import ConfluenceService
from src.services.issue_finder_service import IssueFinderService
from src.services.jira_service import JiraService
from src.sync_task import SyncTaskOrchestrator
from src.undo_sync_task import UndoSyncTaskOrchestrator
from src.utils.logging_config import setup_logging
from src.exceptions import SyncError, MissingRequiredDataError, InvalidInputError, UndoError

# Suppress insecure request warnings, common in corporate/dev environments.
warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)

# Initialize application-wide logging
setup_logging("api_logs", "api_run")
logger = logging.getLogger(__name__)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Jira-Confluence Automation API",
    description="API for synchronizing tasks from Confluence to Jira and undoing previous runs.",
    version="1.0.0",
)

# --- API Key Authentication Setup ---
# Define the header name for the API key
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Dependency function to validate the API key
def get_api_key(api_key: str = Security(api_key_header)):
    if not config.API_SECRET_KEY:
        logger.error("API_SECRET_KEY environment variable is not set!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key not configured."
        )
    if api_key == config.API_SECRET_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key",
    )

# --- Initialize Services (Global instances for simplicity) ---
try:
    if not config.JIRA_URL or not config.JIRA_API_TOKEN or \
       not config.CONFLUENCE_URL or not config.CONFLUENCE_API_TOKEN:
        missing_vars = []
        if not config.JIRA_URL: missing_vars.append("JIRA_URL")
        if not config.JIRA_API_TOKEN: missing_vars.append("JIRA_API_TOKEN")
        if not config.CONFLUENCE_URL: missing_vars.append("CONFLUENCE_URL")
        if not config.CONFLUENCE_API_TOKEN: missing_vars.append("CONFLUENCE_API_TOKEN")
        raise ValueError(f"Missing one or more required environment variables for Jira/Confluence API: {', '.join(missing_vars)}")

    if not config.API_SECRET_KEY:
        raise ValueError("API_SECRET_KEY environment variable is not set. API authentication will not work.")


    jira_client = Jira(
        url=config.JIRA_URL,
        token=config.JIRA_API_TOKEN,
        cloud=False,
        verify_ssl=False,
    )
    confluence_client = Confluence(
        url=config.CONFLUENCE_URL,
        token=config.CONFLUENCE_API_TOKEN,
        cloud=False,
        verify_ssl=False,
    )

    safe_jira_api = SafeJiraApi(jira_client)
    safe_confluence_api = SafeConfluenceApi(confluence_client)

    jira_service = JiraService(safe_jira_api)
    confluence_service = ConfluenceService(safe_confluence_api)
    issue_finder = IssueFinderService(safe_confluence_api, safe_jira_api)

    sync_orchestrator = SyncTaskOrchestrator(confluence_service, jira_service, issue_finder)
    undo_orchestrator = UndoSyncTaskOrchestrator(confluence_service, jira_service)

    logger.info("Jira and Confluence services initialized successfully.")

except Exception as e:
    logger.error(f"Failed to initialize API services: {e}", exc_info=True)
    raise RuntimeError(f"Application failed to initialize due to configuration errors: {e}")


# --- Pydantic Models for Request Bodies ---
class SyncRequest(BaseModel):
    confluence_page_urls: List[str] = Field(..., example=["https://your.confluence.com/display/SPACE/PageName"])
    request_user: str = Field(..., example="your.username")

class UndoRequestItem(BaseModel):
    Status: str
    confluence_page_id: str
    original_page_version: int
    
    New_Jira_Task_Key: Optional[str] = Field(None, alias="New Jira Task Key")
    Linked_Work_Package: Optional[str] = Field(None, alias="Linked Work Package")
    Request_User: Optional[str] = Field(None, alias="Request User")
    confluence_page_title: Optional[str] = None
    confluence_page_url: Optional[str] = None
    confluence_task_id: Optional[str] = None
    task_summary: Optional[str] = None
    status: Optional[str] = None
    assignee_name: Optional[str] = None
    due_date: Optional[str] = None
    original_page_version_by: Optional[str] = None
    original_page_version_when: Optional[str] = None
    context: Optional[str] = None


# --- API Endpoints ---
@app.post("/sync", summary="Synchronize Confluence tasks to Jira", response_model=Dict[str, Any], dependencies=[Depends(get_api_key)])
async def sync_confluence_tasks(request: SyncRequest):
    """
    Initiates the synchronization process to extract incomplete tasks from
    specified Confluence pages (and their descendants) and create corresponding
    Jira tasks.
    """
    logger.info(f"Received /sync request for user: {request.request_user} with {len(request.confluence_page_urls)} URLs.")
    
    sync_input = request.dict()
    
    try:
        sync_orchestrator.run(sync_input)
        
        response_results = [res.to_dict() for res in sync_orchestrator.results]
        
        if not response_results:
            logger.info("Sync run completed, but no actionable tasks were processed.")
            return {"message": "Sync run completed. No actionable tasks found or processed.", "details": []}
        
        logger.info(f"Sync run completed. Processed {len(response_results)} tasks.")
        return {"message": "Sync run completed successfully.", "details": response_results}

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
async def undo_sync_run(results_data: List[UndoRequestItem]):
    """
    Reverts actions from a previous synchronization run by transitioning
    created Jira tasks back to 'Backlog' and rolling back modified Confluence pages.
    Requires the full JSON results from a previous /sync run.
    """
    logger.info(f"Received /undo request for {len(results_data)} entries.")

    try:
        undo_orchestrator.run([item.dict(by_alias=True) for item in results_data])
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