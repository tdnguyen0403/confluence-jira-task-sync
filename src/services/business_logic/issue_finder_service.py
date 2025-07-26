"""
Provides a service for finding and validating Jira issues within Confluence pages.

This module contains the `IssueFinderService`, which is specialized in parsing
Confluence page content to locate Jira issue macros. It then interacts with the
Jira API to fetch details about these issues in a bulk, efficient manner,
and validates them against specified criteria, such as issue type.
"""

import logging
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from src.api.safe_jira_api import SafeJiraApi
from src.interfaces.confluence_service_interface import (
    ConfluenceApiServiceInterface,
)
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)
from src.models.data_models import (
    JiraIssue,
    JiraIssueMacro,
    JiraIssueStatus,
)

logger = logging.getLogger(__name__)


class IssueFinderService(IssueFinderServiceInterface):
    """
    A dedicated service for finding specific Jira issues on Confluence pages.

    This service uses both Confluence and Jira APIs to first read a page's
    content and then validate the issue types of any found Jira macros. It is
    designed to be efficient by fetching issue details from Jira in bulk.
    """

    def __init__(
        self,
        jira_api: SafeJiraApi,
    ):
        """
        Initializes the IssueFinderService.

        Args:
            jira_api (SafeJiraApi): An instance of the safe Jira API
                wrapper for validating issue details.
        """
        self.jira_api = jira_api

    async def find_issue_on_page(
        self,
        page_id: str,
        issue_type_map: Dict[str, str],
        confluence_api_service: ConfluenceApiServiceInterface,
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the first Jira macro on a page matching a specified issue type.

        This method performs a multi-step process:
        1. Fetches the full content of a Confluence page.
        2. Parses the HTML to find all Jira issue macros.
        3. Fetches details for all found issues in a single bulk request.
        4. Iterates through the fetched issues to find one that matches a
           target issue type.

        Args:
            page_id (str): The ID of the Confluence page to search.
            issue_type_map (Dict[str, str]): A mapping of issue type names to
                their IDs (e.g., {"Work Package": "10100"}).
            confluence_api_service (ConfluenceApiServiceInterface): The service
                used to fetch Confluence page content.

        Returns:
            Optional[Dict[str, Any]]: The full Jira issue dictionary if a
                matching issue is found, otherwise None.
        """
        page_content = await confluence_api_service.get_page_by_id(
            page_id, expand="body.storage"
        )
        if (
            not page_content
            or "body" not in page_content
            or "storage" not in page_content["body"]
        ):
            logger.warning(f"Could not retrieve content for page ID '{page_id}'.")
            return None

        extracted_data = await self.find_issues_and_macros_on_page(
            page_content["body"]["storage"]["value"]
        )
        fetched_issues_map = extracted_data["fetched_issues_map"]

        target_issue_type_names = set(issue_type_map.keys())

        for (
            issue_key,
            jira_issue_obj,
        ) in fetched_issues_map.items():
            if jira_issue_obj.issue_type in target_issue_type_names:
                logger.info(
                    f"Found matching parent issue '{issue_key}' on page '{page_id}'."
                )
                return await self.jira_api.get_issue(
                    issue_key, fields=["key", "issuetype", "assignee", "reporter"]
                )

        logger.info(
            f"No matching parent issue found on page '{page_id}' for the given types."
        )
        return None

    async def find_issues_and_macros_on_page(self, page_html: str) -> Dict[str, Any]:
        """
        Extracts Jira macros from HTML and fetches their issues in bulk.

        This implementation parses the page HTML for Jira macros, collects all
        unique issue keys, and then uses a single JQL query to fetch the details
        for all issues at once, which is highly efficient.

        Args:
            page_html (str): The raw HTML content of a Confluence page.

        Returns:
            Dict[str, Any]: A dictionary containing 'jira_macros' (a list of
                `JiraIssueMacro` objects) and 'fetched_issues_map' (a dict
                mapping issue keys to `JiraIssue` objects).
        """
        soup = BeautifulSoup(page_html, "html.parser")
        jira_macros: List[JiraIssueMacro] = []
        jira_keys_to_fetch = set()

        for macro_tag in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            try:
                issue_key_param = macro_tag.find("ac:parameter", {"ac:name": "key"})
                if issue_key_param and issue_key_param.text:
                    issue_key = issue_key_param.text.strip()
                    jira_macros.append(
                        JiraIssueMacro(issue_key=issue_key, macro_html=str(macro_tag))
                    )
                    jira_keys_to_fetch.add(issue_key)
            except Exception as e:
                logger.warning(f"Failed to parse Jira macro: {e}")
                continue

        fetched_issues_map: Dict[str, JiraIssue] = {}
        if jira_keys_to_fetch:
            jql_query = f"issue in ({','.join(jira_keys_to_fetch)})"
            try:
                search_results = await self.jira_api.search_issues(
                    jql_query, fields=["summary", "status", "issuetype"]
                )
                for issue_data in search_results.get("issues", []):
                    status_name = issue_data["fields"]["status"]["name"]
                    status_category = issue_data["fields"]["status"]["statusCategory"][
                        "key"
                    ]
                    issue_status = JiraIssueStatus(
                        name=status_name, category=status_category
                    )

                    fetched_issues_map[issue_data["key"]] = JiraIssue(
                        key=issue_data["key"],
                        summary=issue_data["fields"]["summary"],
                        status=issue_status,
                        issue_type=issue_data["fields"]["issuetype"]["name"],
                    )
            except Exception as e:
                logger.error(f"Error fetching Jira issues in bulk via JQL: {e}")
                raise

        return {"jira_macros": jira_macros, "fetched_issues_map": fetched_issues_map}
