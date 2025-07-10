"""
Provides a high-level service for interacting with Confluence.

This module contains the `ConfluenceService`, which acts as a business logic
layer abstracting the low-level API calls. It implements the unified
`ConfluenceApiServiceInterface` to ensure a consistent contract across different
services.

The primary role of this class is to delegate Confluence-specific operations
to the underlying `SafeConfluenceApi`, providing a clean and simple interface
for the rest of the application.
"""

from typing import Any, Dict, List, Optional

from src.api.safe_confluence_api import SafeConfluenceApi
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.models.data_models import ConfluenceTask


class ConfluenceService(ConfluenceApiServiceInterface):
    """
    A thin service layer for Confluence operations.

    This class implements the `ApiServiceInterface` and serves as a pass-through
    to the `SafeConfluenceApi`, handling all Confluence-related logic.
    """

    def __init__(self, safe_confluence_api: SafeConfluenceApi):
        """
        Initializes the ConfluenceService.

        Args:
            safe_confluence_api (SafeConfluenceApi): An instance of the safe,
                low-level Confluence API wrapper.
        """
        self._api = safe_confluence_api

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """Delegates extracting a page ID from a URL to the API layer."""
        return self._api.get_page_id_from_url(url)

    def get_all_descendants(self, page_id: str) -> List[str]:
        """Delegates fetching all descendant page IDs to the API layer."""
        return self._api.get_all_descendants(page_id)

    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Delegates fetching a page by its ID to the API layer."""
        return self._api.get_page_by_id(page_id, **kwargs)

    def update_page_content(self, page_id: str, new_title: str, new_body: str) -> bool:
        """Delegates updating page content to the API layer."""
        return self._api.update_page(page_id, new_title, new_body)

    def get_tasks_from_page(self, page_details: Dict) -> List[ConfluenceTask]:
        """Delegates extracting tasks from a page to the API layer."""
        return self._api.get_tasks_from_page(page_details)

    def update_page_with_jira_links(self, page_id: str, mappings: List[Dict]) -> None:
        """Delegates updating a page with Jira links to the API layer."""
        return self._api.update_page_with_jira_links(page_id, mappings)

    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Delegates creating a page to the API layer."""
        return self._api.create_page(**kwargs)

    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Delegates fetching user details to the API layer."""
        return self._api.get_user_details_by_username(username)
