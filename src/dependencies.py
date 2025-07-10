import logging
from typing import Optional

from fastapi import HTTPException, status, Security
from fastapi.security import APIKeyHeader
from atlassian import Confluence, Jira

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.services.orchestration.sync_task_orchestrator import (
    SyncTaskOrchestrator,
)  # New import path
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)  # New import path
from src.services.orchestration.confluence_issue_updater_service import (
    ConfluenceIssueUpdaterService,
)
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)  # New import


logger = logging.getLogger(__name__)

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


class DependencyContainer:
    """
    A container for managing and providing application dependencies.
    This uses a simple singleton pattern for client instances and
    lazy initialization for other services.
    """

    _jira_client_instance: Optional[Jira] = None
    _confluence_client_instance: Optional[Confluence] = None

    @property
    def jira_client(self) -> Jira:
        """Provides a singleton Jira client instance."""
        if self._jira_client_instance is None:
            if not config.JIRA_URL or not config.JIRA_API_TOKEN:
                raise RuntimeError(
                    "Missing JIRA_URL or JIRA_API_TOKEN environment variables."
                )
            try:
                self._jira_client_instance = Jira(
                    url=config.JIRA_URL,
                    token=config.JIRA_API_TOKEN,
                    cloud=False,
                    verify_ssl=False,
                )
                logger.info("Jira client initialized.")
            except Exception as e:
                logger.critical(f"Failed to initialize Jira client: {e}", exc_info=True)
                raise RuntimeError("Jira client initialization failed.")
        return self._jira_client_instance

    @property
    def confluence_client(self) -> Confluence:
        """Provides a singleton Confluence client instance."""
        if self._confluence_client_instance is None:
            if not config.CONFLUENCE_URL or not config.CONFLUENCE_API_TOKEN:
                raise RuntimeError(
                    "Missing CONFLUENCE_URL or CONFLUENCE_API_TOKEN environment variables."
                )
            try:
                self._confluence_client_instance = Confluence(
                    url=config.CONFLUENCE_URL,
                    token=config.CONFLUENCE_API_TOKEN,
                    cloud=False,
                    verify_ssl=False,
                )
                logger.info("Confluence client initialized.")
            except Exception as e:
                logger.critical(
                    f"Failed to initialize Confluence client: {e}", exc_info=True
                )
                raise RuntimeError("Confluence client initialization failed.")
        return self._confluence_client_instance

    @property
    def safe_jira_api(self) -> SafeJiraApi:
        """Provides a SafeJiraApi instance."""
        return SafeJiraApi(self.jira_client)

    @property
    def safe_confluence_api(self) -> SafeConfluenceApi:
        """Provides a SafeConfluenceApi instance."""
        return SafeConfluenceApi(self.confluence_client)

    @property
    def jira_service(self) -> JiraService:
        """Provides a JiraService instance."""
        return JiraService(self.safe_jira_api)

    @property
    def confluence_service(self) -> ConfluenceService:
        """Provides a ConfluenceService instance."""
        return ConfluenceService(self.safe_confluence_api)

    @property
    def issue_finder_service(
        self,
    ) -> IssueFinderServiceInterface:  # Changed return type to interface
        """Provides an IssueFinderService instance."""
        # Instantiate with interface types if IssueFinderService is updated to accept them
        return IssueFinderService(self.confluence_service, self.jira_service)

    def confluence_issue_updater_service(self) -> ConfluenceIssueUpdaterService:
        """Provides a ConfluenceIssueUpdaterService instance."""
        return ConfluenceIssueUpdaterService(self.confluence_service, self.jira_service)

    def sync_orchestrator(self) -> SyncTaskOrchestrator:
        """Provides a SyncTaskOrchestrator instance."""
        return SyncTaskOrchestrator(
            self.confluence_service, self.jira_service, self.issue_finder_service
        )

    def undo_orchestrator(self) -> UndoSyncTaskOrchestrator:
        """Provides an UndoSyncTaskOrchestrator instance."""
        return UndoSyncTaskOrchestrator(self.confluence_service, self.jira_service)


# Instantiate the container once globally
container = DependencyContainer()
