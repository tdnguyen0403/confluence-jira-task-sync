"""
Manages dependency injection for the FastAPI application.

This module is responsible for creating and providing instances of all necessary
services and API clients. It uses a singleton pattern, facilitated by
`functools.lru_cache`, to ensure that only one instance of each service or
client is created per application lifecycle. This approach improves performance
and resource management by reusing connections and objects. Dependencies are
wired together here, promoting loose coupling throughout the application.
"""

import logging
import secrets
from functools import lru_cache

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.api.https_helper import HTTPSHelper
from src.api.safe_confluence_api import SafeConfluenceAPI
from src.api.safe_jira_api import SafeJiraAPI
from src.config import config
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.issue_finder_service_interface import IssueFinderServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business.issue_finder_service import IssueFinderService
from src.services.orchestration.sync_project import (
    SyncProjectService,
)
from src.services.orchestration.sync_task import SyncTaskService
from src.services.orchestration.undo_sync_task import (
    UndoSyncService,
)

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Validates the API key provided in the request header.

    This dependency function checks the 'X-API-Key' header against the
    secret key defined in the application's configuration.

    Args:
        api_key (str): The API key from the request header.

    Raises:
        HTTPException: If the server's API key is not configured or if the
                       provided key is invalid.

    Returns:
        str: The validated API key if successful.
    """
    if not config.API_SECRET_KEY:
        logger.error("API_SECRET_KEY environment variable is not set!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key not configured.",
        )
    if secrets.compare_digest(api_key, config.API_SECRET_KEY):
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key",
    )


_http_helper_instance = HTTPSHelper(verify_ssl=config.VERIFY_SSL)


@lru_cache(maxsize=None)
def get_https_helper() -> HTTPSHelper:
    """
    Provides the singleton instance of the HTTPSHelper.

    The client within this helper is managed by the application's lifespan
    events to ensure proper startup and shutdown of network resources.

    Returns:
        HTTPSHelper: The single, shared instance of the HTTPS helper.
    """
    return _http_helper_instance


@lru_cache(maxsize=None)
def get_safe_jira_api(
    https_helper: HTTPSHelper = Depends(get_https_helper),
) -> SafeJiraAPI:
    """Provides a singleton instance of the SafeJiraAPI client."""
    return SafeJiraAPI(
        base_url=config.JIRA_URL,
        https_helper=https_helper,
    )


@lru_cache(maxsize=None)
def get_safe_confluence_api(
    https_helper: HTTPSHelper = Depends(get_https_helper),
) -> SafeConfluenceAPI:
    """Provides a singleton instance of the SafeConfluenceAPI client."""
    return SafeConfluenceAPI(
        base_url=config.CONFLUENCE_URL,
        https_helper=https_helper,
        jira_macro_server_name=config.JIRA_MACRO_SERVER_NAME,
        jira_macro_server_id=config.JIRA_MACRO_SERVER_ID,
    )


@lru_cache(maxsize=None)
def get_jira_service(
    safe_jira_api: SafeJiraAPI = Depends(get_safe_jira_api),
) -> JiraApiServiceInterface:
    """Provides a singleton instance of the JiraService."""
    return JiraService(safe_jira_api)


@lru_cache(maxsize=None)
def get_confluence_service(
    safe_confluence_api: SafeConfluenceAPI = Depends(get_safe_confluence_api),
) -> ConfluenceApiServiceInterface:
    """Provides a singleton instance of the ConfluenceService."""
    return ConfluenceService(safe_confluence_api)


@lru_cache(maxsize=None)
def get_issue_finder_service(
    jira_service: JiraApiServiceInterface = Depends(get_jira_service),
    confluence_service: ConfluenceApiServiceInterface = Depends(get_confluence_service),
) -> IssueFinderServiceInterface:
    """Provides a singleton instance of the IssueFinderService."""
    return IssueFinderService(jira_service, confluence_service)


@lru_cache(maxsize=None)
def get_sync_project(
    confluence_service: ConfluenceApiServiceInterface = Depends(get_confluence_service),
    jira_service: JiraApiServiceInterface = Depends(get_jira_service),
    issue_finder_service: IssueFinderServiceInterface = Depends(
        get_issue_finder_service
    ),
) -> SyncProjectService:
    """Provides a singleton instance of the SyncProjectService."""
    return SyncProjectService(confluence_service, jira_service, issue_finder_service)


@lru_cache(maxsize=None)
def get_sync_task(
    confluence_service: ConfluenceApiServiceInterface = Depends(get_confluence_service),
    jira_service: JiraApiServiceInterface = Depends(get_jira_service),
    issue_finder_service: IssueFinderServiceInterface = Depends(
        get_issue_finder_service
    ),
) -> SyncTaskService:
    """Provides a singleton instance of the SyncTaskService."""
    return SyncTaskService(
        confluence_service,
        jira_service,
        issue_finder_service,
    )


@lru_cache(maxsize=None)
def get_undo_sync_task(
    confluence_service: ConfluenceApiServiceInterface = Depends(get_confluence_service),
    jira_service: JiraApiServiceInterface = Depends(get_jira_service),
    issue_finder_service: IssueFinderServiceInterface = Depends(
        get_issue_finder_service
    ),
) -> UndoSyncService:
    """Provides a singleton instance of the UndoSyncService."""
    return UndoSyncService(confluence_service, jira_service, issue_finder_service)
