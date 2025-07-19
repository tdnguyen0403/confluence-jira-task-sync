"""
Provides a resilient, low-level API wrapper for Jira operations.

This module contains the SafeJiraApi class, which is responsible for all
direct communication with the Jira API. It mirrors the resilience pattern
of the Confluence wrapper by using the `atlassian-python-api` library as its
primary client and implementing fallbacks to direct `requests` calls for key
operations. This ensures robustness against library-specific failures.

The class handles creating and retrieving issues, as well as managing issue
transitions.
"""

import logging
from typing import Any, Dict, List, Optional

# Local application imports
from src.config import config
from src.api.https_helper import HTTPSHelper

# Configure logging for this module
logger = logging.getLogger(__name__)


class SafeJiraApi:
    """
    Safe wrapper for Jira API interactions, using the asynchronous HTTPSHelper.
    """

    def __init__(self, base_url: str, https_helper: HTTPSHelper):
        """
        Initializes the SafeJiraApi.

        Args:
            base_url (str): The base URL of the Jira instance.
            https_helper (HTTPSHelper): An instance of the asynchronous HTTPSHelper.
        """
        self.base_url = config.JIRA_URL.rstrip("/")
        self.https_helper = https_helper  # Correctly initialize https_helper
        # Construct the Authorization header directly using username and PAT
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.JIRA_API_TOKEN}",
        }

    async def get_issue(
        self, issue_key: str, fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Retrieves a single Jira issue asynchronously.
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}"
        params = {"fields": ",".join(fields)} if fields else {}
        try:
            # Pass headers directly to https_helper
            return await self.https_helper.get(url, headers=self.headers, params=params)
        except Exception as e:
            logger.error(f"Failed to get Jira issue {issue_key}: {e}")
            raise

    async def create_issue(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a new Jira issue asynchronously.
        'fields' should contain all necessary fields like project, issuetype, summary, etc.
        Example fields:
        {
            "project": {"key": "YOUR_PROJECT_KEY"},
            "issuetype": {"name": "Task"},
            "summary": "This is a new task created from Python",
            "description": "Details about the task."
        }
        """
        url = f"{self.base_url}/rest/api/2/issue"
        payload = {"fields": fields}
        try:
            return await self.https_helper.post(
                url, headers=self.headers, json_data=payload
            )
        except Exception as e:
            logger.error(f"Failed to create Jira issue with fields {fields}: {e}")
            raise

    async def get_available_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Retrieves all available transitions for a given Jira issue asynchronously.
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        try:
            response_data = await self.https_helper.get(url, headers=self.headers)
            return response_data.get("transitions", [])
        except Exception as e:
            logger.error(
                f"Failed to get available transitions for issue {issue_key}: {e}"
            )
            raise

    async def find_transition_id_by_name(
        self, issue_key: str, transition_name: str
    ) -> Optional[str]:
        """
        Finds the ID of a transition by its name for a given Jira issue asynchronously.
        """
        transitions = await self.get_available_transitions(issue_key)
        for transition in transitions:
            if transition.get("name", "").lower() == transition_name.lower():
                return transition["id"]
        logger.warning(
            f"Transition '{transition_name}' not found for issue {issue_key}."
        )
        return None

    async def transition_issue(
        self, issue_key: str, transition_name: str
    ) -> Dict[str, Any]:
        """
        Transitions a Jira issue to a new status asynchronously.
        """
        # Use the helper method to find the transition ID
        transition_id = await self.find_transition_id_by_name(
            issue_key, transition_name
        )

        if not transition_id:
            # The find_transition_id_by_name method already logs a warning,
            # but we raise a ValueError here to clearly indicate failure to the caller.
            raise ValueError(
                f"Transition '{transition_name}' not found for issue {issue_key}"
            )

        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        payload = {"transition": {"id": transition_id}}
        try:
            # Pass headers directly to https_helper
            response = await self.https_helper.post(
                url, headers=self.headers, json_data=payload
            )
            return response  # May be empty for 204
        except Exception as e:
            logger.error(
                f"Failed to transition Jira issue {issue_key} to '{transition_name}': {e}"
            )
            raise

    async def get_current_user(self) -> Dict[str, Any]:
        """
        Retrieves information about the current authenticated Jira user asynchronously.
        Used for health checks.
        """
        url = f"{self.base_url}/rest/api/2/myself"
        try:
            # Pass headers directly to https_helper
            return await self.https_helper.get(url, headers=self.headers)
        except Exception as e:
            logger.error(f"Error getting current Jira user: {e}")
            raise

    async def search_issues(
        self, jql_query: str, fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes a JQL query and returns matching issues asynchronously.
        """
        url = f"{self.base_url}/rest/api/2/search"
        params = {"jql": jql_query}
        if fields:
            params["fields"] = ",".join(fields)

        try:
            # Pass headers directly to https_helper
            return await self.https_helper.get(url, headers=self.headers, params=params)
        except Exception as e:
            logger.error(f"Error executing JQL search '{jql_query}': {e}")
            raise

    async def get_issue_type_details_by_id(
        self, issue_type_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves details for a specific Jira issue type by its ID asynchronously.
        """
        url = f"{self.base_url}/rest/api/2/issuetype/{issue_type_id}"
        try:
            return await self.https_helper.get(url, headers=self.headers)
        except Exception as e:
            logger.error(
                f"Failed to get Jira issue type details for ID {issue_type_id}: {e}"
            )
            return None

    async def update_issue_description(
        self, issue_key: str, new_description: str
    ) -> Dict[str, Any]:
        """
        Updates the description of a Jira issue asynchronously.
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}"
        payload = {"fields": {"description": new_description}}
        try:
            response = await self.https_helper.put(
                url, headers=self.headers, json_data=payload
            )
            return response
        except Exception as e:
            logger.error(f"Failed to update Jira issue {issue_key} description: {e}")
            raise
