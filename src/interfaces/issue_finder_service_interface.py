from abc import ABC, abstractmethod
from typing import (
    Dict,
    Optional,
)  # Added List import for find_issues_and_macros_on_page
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.models.data_models import JiraIssueMacro, JiraIssue  # Added import


class IssueFinderServiceInterface(ABC):
    """
    An abstract base class for a service that finds specific Jira issues
    embedded in Confluence pages.
    """

    @abstractmethod
    async def find_issue_on_page(  # Changed to async
        self,
        page_id: str,
        issue_type_map: Dict[str, str],
        confluence_api_service: ConfluenceApiServiceInterface,  # Added confluence_api_service
    ) -> Optional[Dict[str, JiraIssueMacro]]:
        """
        Finds the first Jira macro on a page matching a specified issue type asynchronously.

        Args:
            page_id (str): The ID of the Confluence page to search.
            issue_type_map (Dict[str, str]): A mapping of issue type names to
                their corresponding IDs (e.g., {"Work Package": "10100"}).
            confluence_api_service (ConfluenceApiServiceInterface): The Confluence service to fetch page content.

        Returns:
            Optional[Dict[str, Any]]: The full Jira issue dictionary if a
                matching issue is found, otherwise None.
        """
        pass

    @abstractmethod
    async def find_issues_and_macros_on_page(
        self, page_html: str
    ) -> Dict[str, JiraIssue]:  # Added async
        """
        Extracts Jira issue macros from HTML and fetches their corresponding Jira issues in bulk asynchronously.
        Returns a dictionary with 'jira_macros' and 'fetched_issues_map'.
        """
        pass
