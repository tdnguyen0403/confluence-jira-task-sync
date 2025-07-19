import logging
from functools import lru_cache  # Import lru_cache

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import APIKeyHeader

from src.config import config
from src.api.https_helper import HTTPSHelper
from src.api.safe_jira_api import SafeJiraApi
from src.api.safe_confluence_api import SafeConfluenceApi
from src.services.adaptors.jira_service import JiraService
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.services.orchestration.confluence_issue_updater_service import (
    ConfluenceIssueUpdaterService,
)
from src.services.orchestration.sync_task_orchestrator import SyncTaskOrchestrator
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)

logger = logging.getLogger(__name__)

# --- API Key Validation Dependencies ---
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency function to validate the API key."""
    if not config.API_SECRET_KEY:
        logger.error("API_SECRET_KEY environment variable is not set!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key not configured.",
        )
    if api_key == config.API_SECRET_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key",
    )


# --- Core API Client Dependencies ---
# Create a single instance of HTTPSHelper.
# The httpx.AsyncClient within it will be initialized and closed by FastAPI's lifespan.
_http_helper_instance = HTTPSHelper(verify_ssl=config.VERIFY_SSL)


@lru_cache(maxsize=None)  # Add caching here
def get_https_helper() -> HTTPSHelper:
    """Dependency to provide the singleton HTTPSHelper instance."""
    return _http_helper_instance


@lru_cache(maxsize=None)  # Add caching here
def get_safe_jira_api(
    https_helper: HTTPSHelper = Depends(get_https_helper),
) -> SafeJiraApi:
    """Dependency to provide SafeJiraApi instance, injected with HTTPSHelper."""
    return SafeJiraApi(
        base_url=config.JIRA_URL,
        https_helper=https_helper,
    )


@lru_cache(maxsize=None)  # Add caching here
def get_safe_confluence_api(
    https_helper: HTTPSHelper = Depends(get_https_helper),
) -> SafeConfluenceApi:
    """Dependency to provide SafeConfluenceApi instance, injected with HTTPSHelper."""
    return SafeConfluenceApi(
        base_url=config.CONFLUENCE_URL,
        https_helper=https_helper,
        jira_macro_server_name=config.JIRA_MACRO_SERVER_NAME,
        jira_macro_server_id=config.JIRA_MACRO_SERVER_ID,
    )


# --- Service Dependencies ---


@lru_cache(maxsize=None)  # Add caching here
def get_jira_service(
    safe_jira_api: SafeJiraApi = Depends(get_safe_jira_api),
) -> JiraService:
    """Provides JiraService, depending on SafeJiraApi."""
    return JiraService(safe_jira_api)


@lru_cache(maxsize=None)  # Add caching here
def get_confluence_service(
    safe_confluence_api: SafeConfluenceApi = Depends(get_safe_confluence_api),
) -> ConfluenceService:
    """Provides ConfluenceService, depending on SafeConfluenceApi."""
    return ConfluenceService(safe_confluence_api)


@lru_cache(maxsize=None)  # Add caching here
def get_issue_finder_service(
    safe_jira_api: SafeJiraApi = Depends(get_safe_jira_api),
) -> IssueFinderService:
    """Provides IssueFinderService, depending on SafeJiraApi."""
    return IssueFinderService(safe_jira_api)


@lru_cache(maxsize=None)  # Add caching here
def get_confluence_issue_updater_service(
    safe_confluence_api: SafeConfluenceApi = Depends(get_safe_confluence_api),
    safe_jira_api: SafeJiraApi = Depends(get_safe_jira_api),
    issue_finder_service: IssueFinderService = Depends(get_issue_finder_service),
) -> ConfluenceIssueUpdaterService:
    """Provides ConfluenceIssueUpdaterService, depending on SafeConfluenceApi, SafeJiraApi, and IssueFinderService."""
    return ConfluenceIssueUpdaterService(
        safe_confluence_api, safe_jira_api, issue_finder_service
    )


@lru_cache(maxsize=None)  # Add caching here
def get_sync_task_orchestrator(
    confluence_service: ConfluenceService = Depends(get_confluence_service),
    jira_service: JiraService = Depends(get_jira_service),
    issue_finder_service: IssueFinderService = Depends(get_issue_finder_service),
    confluence_issue_updater_service: ConfluenceIssueUpdaterService = Depends(
        get_confluence_issue_updater_service
    ),
) -> SyncTaskOrchestrator:
    """Provides SyncTaskOrchestrator, depending on various services."""
    return SyncTaskOrchestrator(
        confluence_service,
        jira_service,
        issue_finder_service,
        confluence_issue_updater_service,
    )


@lru_cache(maxsize=None)  # Add caching here
def get_undo_sync_task_orchestrator(
    confluence_service: ConfluenceService = Depends(get_confluence_service),
    jira_service: JiraService = Depends(get_jira_service),
    issue_finder_service: IssueFinderService = Depends(get_issue_finder_service),
) -> UndoSyncTaskOrchestrator:
    """Provides UndoSyncTaskOrchestrator, depending on various services."""
    return UndoSyncTaskOrchestrator(
        confluence_service, jira_service, issue_finder_service
    )
