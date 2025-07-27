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
from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.services.orchestration.confluence_issue_updater_service import (
    ConfluenceIssueUpdaterService,
)
from src.services.orchestration.sync_task_orchestrator import SyncTaskOrchestrator
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def get_api_key(api_key: str = Security(api_key_header)):
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
) -> SafeJiraApi:
    """
    Provides a singleton instance of the SafeJiraApi client.

    This dependency is injected with the shared `HTTPSHelper` instance.

    Args:
        https_helper (HTTPSHelper): The shared HTTPSHelper instance.

    Returns:
        SafeJiraApi: The single, shared instance of the Jira API client.
    """
    return SafeJiraApi(
        base_url=config.JIRA_URL,
        https_helper=https_helper,
    )


@lru_cache(maxsize=None)
def get_safe_confluence_api(
    https_helper: HTTPSHelper = Depends(get_https_helper),
) -> SafeConfluenceApi:
    """
    Provides a singleton instance of the SafeConfluenceApi client.

    This dependency is injected with the shared `HTTPSHelper` instance.

    Args:
        https_helper (HTTPSHelper): The shared HTTPSHelper instance.

    Returns:
        SafeConfluenceApi: The single, shared instance of the Confluence API client.
    """
    return SafeConfluenceApi(
        base_url=config.CONFLUENCE_URL,
        https_helper=https_helper,
        jira_macro_server_name=config.JIRA_MACRO_SERVER_NAME,
        jira_macro_server_id=config.JIRA_MACRO_SERVER_ID,
    )


@lru_cache(maxsize=None)
def get_jira_service(
    safe_jira_api: SafeJiraApi = Depends(get_safe_jira_api),
) -> JiraService:
    """
    Provides a singleton instance of the JiraService.

    Args:
        safe_jira_api (SafeJiraApi): The shared Jira API client instance.

    Returns:
        JiraService: The single, shared instance of the Jira service.
    """
    return JiraService(safe_jira_api)


@lru_cache(maxsize=None)
def get_confluence_service(
    safe_confluence_api: SafeConfluenceApi = Depends(get_safe_confluence_api),
) -> ConfluenceService:
    """
    Provides a singleton instance of the ConfluenceService.

    Args:
        safe_confluence_api (SafeConfluenceApi):
            The shared Confluence API client instance.

    Returns:
        ConfluenceService: The single, shared instance of the Confluence service.
    """
    return ConfluenceService(safe_confluence_api)


@lru_cache(maxsize=None)
def get_issue_finder_service(
    safe_jira_api: SafeJiraApi = Depends(get_safe_jira_api),
) -> IssueFinderService:
    """
    Provides a singleton instance of the IssueFinderService.

    Args:
        safe_jira_api (SafeJiraApi): The shared Jira API client instance.

    Returns:
        IssueFinderService: The single, shared instance of the issue finder service.
    """
    return IssueFinderService(safe_jira_api)


@lru_cache(maxsize=None)
def get_confluence_issue_updater_service(
    safe_confluence_api: SafeConfluenceApi = Depends(get_safe_confluence_api),
    safe_jira_api: SafeJiraApi = Depends(get_safe_jira_api),
    issue_finder_service: IssueFinderService = Depends(get_issue_finder_service),
) -> ConfluenceIssueUpdaterService:
    """
    Provides a singleton instance of the ConfluenceIssueUpdaterService.

    Args:
        safe_confluence_api (SafeConfluenceApi): The Confluence API client.
        safe_jira_api (SafeJiraApi): The Jira API client.
        issue_finder_service (IssueFinderService): The issue finder service.

    Returns:
        ConfluenceIssueUpdaterService: The shared instance of the updater service.
    """
    return ConfluenceIssueUpdaterService(
        safe_confluence_api, safe_jira_api, issue_finder_service
    )


@lru_cache(maxsize=None)
def get_sync_task_orchestrator(
    confluence_service: ConfluenceService = Depends(get_confluence_service),
    jira_service: JiraService = Depends(get_jira_service),
    issue_finder_service: IssueFinderService = Depends(get_issue_finder_service),
) -> SyncTaskOrchestrator:
    """
    Provides a singleton instance of the SyncTaskOrchestrator.

    Args:
        confluence_service (ConfluenceService): The Confluence service instance.
        jira_service (JiraService): The Jira service instance.
        issue_finder_service (IssueFinderService): The issue finder service instance.

    Returns:
        SyncTaskOrchestrator: The shared instance of the sync task orchestrator.
    """
    return SyncTaskOrchestrator(
        confluence_service,
        jira_service,
        issue_finder_service,
    )


@lru_cache(maxsize=None)
def get_undo_sync_task_orchestrator(
    confluence_service: ConfluenceService = Depends(get_confluence_service),
    jira_service: JiraService = Depends(get_jira_service),
    issue_finder_service: IssueFinderService = Depends(get_issue_finder_service),
) -> UndoSyncTaskOrchestrator:
    """
    Provides a singleton instance of the UndoSyncTaskOrchestrator.

    Args:
        confluence_service (ConfluenceService): The Confluence service instance.
        jira_service (JiraService): The Jira service instance.
        issue_finder_service (IssueFinderService): The issue finder service instance.

    Returns:
        UndoSyncTaskOrchestrator: The shared instance of the undo orchestrator.
    """
    return UndoSyncTaskOrchestrator(
        confluence_service, jira_service, issue_finder_service
    )
