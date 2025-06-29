import logging
from typing import Optional, Dict, Any

from bs4 import BeautifulSoup

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.config import config

class IssueFinderService:
    """A dedicated service for finding specific Jira issues on Confluence pages."""

    def __init__(self, safe_confluence_api: SafeConfluenceApi, safe_jira_api: SafeJiraApi):
        self.confluence_api = safe_confluence_api
        self.jira_api = safe_jira_api

    def find_issue_on_page(self, page_id: str, issue_type_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Finds the first Jira macro on a page that matches one of the given issue type IDs from the map.

        Args:
            page_id: The ID of the Confluence page to search.
            issue_type_map: A dictionary where keys are issue type names and values are their IDs
                            (e.g., {"Work Package": "10100", "Risk": "11404"}).

        Returns:
            The full Jira issue dictionary if found, otherwise None.
        """
        page_content = self.confluence_api.get_page_by_id(page_id, expand="body.storage")
        if not page_content or 'body' not in page_content or 'storage' not in page_content['body']:
            return None

        soup = BeautifulSoup(page_content["body"]["storage"]["value"], "html.parser")
        for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            # Corrected logic to ignore macros within other macros
            if macro.find_parent("ac:structured-macro", {"ac:name": lambda x: x in config.AGGREGATION_CONFLUENCE_MACRO and x != 'jira'}):
                continue
            key_param = macro.find("ac:parameter", {"ac:name": "key"})
            if key_param:
                issue_key = key_param.get_text(strip=True)
                # This check should only happen if the macro is not ignored
                if not macro.find_parent("ac:structured-macro", {"ac:name": lambda x: x in config.AGGREGATION_CONFLUENCE_MACRO and x != 'jira'}):
                    jira_issue = self.jira_api.get_issue(issue_key, fields="issuetype")
                    if jira_issue and jira_issue.get("fields", {}).get("issuetype", {}).get("id") in issue_type_map.values():
                        return self.jira_api.get_issue(issue_key, fields="key,issuetype,assignee,reporter")
        return None