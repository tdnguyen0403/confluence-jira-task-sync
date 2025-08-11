"""
Defines the abstract interface for the Issue Finder service.

This module provides the `IFindIssue`, an abstract base class
that outlines the contract for any service responsible for finding and
validating Jira issues embedded within Confluence pages. Adhering to this
interface ensures that different implementations can be used interchangeably,
which is beneficial for testing and modularity.
"""

from abc import ABC, abstractmethod
from typing import (
    Any,
    Dict,
    Optional,
)


class IFindIssue(ABC):
    """
    An abstract base class for a service that finds specific Jira issues
    embedded in Confluence pages. This service acts as a bridge between
    Confluence page content and Jira issue validation.
    """

    @abstractmethod
    async def find_issue_on_page(
        self,
        page_id: str,
        issue_type_map: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the first Jira macro on a page that matches a specified issue type.

        This method should orchestrate fetching the page content, parsing it for
        Jira macros, and then validating the found issues against Jira to check
        if their type matches the desired types.

        Args:
            page_id (str): The ID of the Confluence page to search.
            issue_type_map (Dict[str, str]): A mapping of target issue type names
                to their IDs (e.g., {"Work Package": "10100"}).

        Returns:
            Optional[Dict[str, Any]]: The full Jira issue dictionary from the API
                if a matching issue is found, otherwise None.
        """
        pass

    @abstractmethod
    async def find_issues_and_macros_on_page(self, page_html: str) -> Dict[str, Any]:
        """
        Extracts all Jira macros from HTML and fetches their issues in bulk.

        This method should parse the provided HTML, identify all Jira macros,
        and then perform a single, efficient bulk query to Jira to retrieve
        the details for all found issue keys.

        Args:
            page_html (str): The HTML content of a Confluence page.

        Returns:
            Dict[str, Any]: A dictionary containing two keys:
                - 'jira_macros': A list of `JiraIssueMacro` objects.
                - 'fetched_issues_map': A dictionary mapping issue keys to
                  `JiraIssue` objects.
        """
        pass
