import logging
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.config import config
from src.interfaces.confluence_service_interface import (
    ConfluenceApiServiceInterface,
)  # New import
from src.interfaces.jira_service_interface import JiraApiServiceInterface  # New import
from src.interfaces.issue_finder_service_interface import (
    IssueFinderServiceInterface,
)  # New import

logger = logging.getLogger(__name__)


class IssueFinderService(IssueFinderServiceInterface):  # Inherit from the new interface
    """
    A dedicated service for finding specific Jira issues on Confluence pages.

    This service uses both the Confluence and Jira APIs to first read a
    page's content and then validate the issue types of any found Jira macros.
    """

    def __init__(
        self,
        confluence_api: ConfluenceApiServiceInterface,  # Changed to interface
        jira_api: JiraApiServiceInterface,  # Changed to interface
    ):
        """
        Initializes the IssueFinderService.

        Args:
            confluence_api (ConfluenceApiServiceInterface): An instance of the safe
                Confluence API wrapper for fetching page content.
            jira_api (JiraApiServiceInterface): An instance of the safe Jira API
                wrapper for validating issue details.
        """
        self.confluence_api = confluence_api
        self.jira_api = jira_api

    def find_issue_on_page(
        self, page_id: str, issue_type_map: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the first Jira macro on a page matching a specified issue type.

        This method performs a multi-step process:
        1. Fetches the full content of a Confluence page.
        2. Parses the HTML content to find all Jira issue macros.
        3. For each macro, it extracts the Jira issue key.
        4. It then calls the Jira API to get the issue's type.
        5. If the issue's type ID is one of the target types (e.g., a Work
           Package or Risk), it fetches the full issue details and returns it.

        Args:
            page_id (str): The ID of the Confluence page to search.
            issue_type_map (Dict[str, str]): A mapping of issue type names to
                their corresponding IDs (e.g., {"Work Package": "10100"}).

        Returns:
            Optional[Dict[str, Any]]: The full Jira issue dictionary if a
                matching issue is found, otherwise None.
        """
        page_content = self.confluence_api.get_page_by_id(
            page_id, expand="body.storage"
        )
        if (
            not page_content
            or "body" not in page_content
            or "storage" not in page_content["body"]
        ):
            logger.warning(f"Could not retrieve content for page ID '{page_id}'.")
            return None

        soup = BeautifulSoup(page_content["body"]["storage"]["value"], "html.parser")

        for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            if macro.find_parent(
                "ac:structured-macro",
                {
                    "ac:name": lambda x: x in config.AGGREGATION_CONFLUENCE_MACRO
                    and x != "jira"
                },
            ):
                continue

            key_param = macro.find("ac:parameter", {"ac:name": "key"})
            if key_param:
                issue_key = key_param.get_text(strip=True)

                jira_issue = self.jira_api.get_issue(issue_key, fields="issuetype")

                if (
                    jira_issue
                    and jira_issue.get("fields", {}).get("issuetype", {}).get("id")
                    in issue_type_map.values()
                ):
                    logger.info(
                        f"Found matching parent issue '{issue_key}' on page "
                        f"'{page_id}'."
                    )
                    return self.jira_api.get_issue(
                        issue_key, fields="key,issuetype,assignee,reporter"
                    )

        logger.info(
            f"No matching parent issue found on page '{page_id}' for the "
            "given types."
        )
        return None
