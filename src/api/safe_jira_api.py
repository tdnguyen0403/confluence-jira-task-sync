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

import requests
from atlassian import Jira

# Local application imports
from src.config import config
from src.api.https_helper import make_request

# Configure logging for this module
logger = logging.getLogger(__name__)


class SafeJiraApi:
    """
    A resilient, low-level service for all Jira operations.

    This class provides a safe wrapper around the Jira client, with built-in
    fallbacks to raw REST API calls for increased reliability.

    Attributes:
        client (Jira): The primary `atlassian-python-api` client.
        base_url (str): The base URL for the Jira instance.
        headers (Dict[str, str]): The authorization headers for direct
                                  REST API calls.
    """

    def __init__(self, jira_client: Jira):
        """
        Initializes the SafeJiraApi.

        Args:
            jira_client (Jira): An authenticated instance of the
                                atlassian-python-api Jira client.
        """
        self.client = jira_client
        self.base_url = config.JIRA_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {config.JIRA_API_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_issue(
        self, issue_key: str, fields: str = "*all"
    ) -> Optional[Dict[str, Any]]:
        """
        Safely retrieves a Jira issue by its key.

        Tries to fetch the issue using the library client and falls back to a
        direct REST API call upon failure.

        Args:
            issue_key (str): The key of the issue to retrieve (e.g., 'PROJ-123').
            fields (str): A comma-separated list of fields to retrieve.
                          Defaults to '*all'.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the issue data,
                                      or None if retrieval fails.
        """
        try:
            return self.client.get_issue(issue_key, fields=fields)   
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while getting issue '{issue_key}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_issue(issue_key, fields)        
        except Exception as e:
            logger.warning(
                f"Library get_issue for '{issue_key}' failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_issue(issue_key, fields)

    def _fallback_get_issue(
        self, issue_key: str, fields: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback method to get an issue by key using a direct REST call."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}?fields={fields}"
        response = make_request("GET", url, headers=self.headers, verify_ssl=False)
        if response:
            return response.json()
        return None

    def create_issue(
        self, issue_fields: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Safely creates a new Jira issue.

        Tries to create the issue using the library client and falls back to a
        direct REST API call upon failure.

        Args:
            issue_fields (Dict[str, Any]): A dictionary representing the
                                           issue's fields, conforming to the
                                           Jira API structure.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing the newly created
                                      issue's data, or None if creation fails.
        """
        try:
            # The library expects the fields directly, not nested.
            # Assuming issue_fields comes with 'fields' key as per prepare_jira_task_fields
            return self.client.issue_create(fields=issue_fields["fields"])
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while creating issue '{issue_key}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_create_issue(issue_key, fields) 
        except Exception as e:
            logger.warning(f"Library create_issue failed. Falling back. Error: {e}")
            return self._fallback_create_issue(issue_fields)

    def _fallback_create_issue(
        self, issue_fields: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Fallback method to create an issue using a direct REST call."""
        url = f"{self.base_url}/rest/api/2/issue"
        response = make_request("POST", url, headers=self.headers, json_data=issue_fields, verify_ssl=False)
        if response:
            return response.json()
        return None

    def get_available_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Gets all available workflow transitions for a given issue.

        Args:
            issue_key (str): The key of the issue.

        Returns:
            List[Dict[str, Any]]: A list of available transition objects, or an
                                  empty list on failure.
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        response = make_request("GET", url, headers=self.headers, verify_ssl=False)
        if response:
            return response.json().get("transitions", [])
        return []

    def find_transition_id_by_name(
        self, issue_key: str, target_status: str
    ) -> Optional[str]:
        """
        Finds a transition ID by its target status name.

        This is necessary because the API requires a transition ID, not the
        name of the status you want to move to.

        Args:
            issue_key (str): The key of the issue.
            target_status (str): The name of the destination status (e.g.,
                                 'Done', 'In Progress').

        Returns:
            Optional[str]: The found transition ID, or None if no matching
                           transition is available.
        """
        transitions = self.get_available_transitions(issue_key)
        for t in transitions:
            # Compare names case-insensitively for robustness.
            if str(t.get("to", {}).get("name", "")).lower() == target_status.lower():
                return t["id"]
        logger.error(
            f"Transition to status '{target_status}' not available for issue "
            f"'{issue_key}'."
        )
        return None

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """
        Transitions an issue to a target status.

        This method first finds the correct transition ID for the target status
        name and then attempts to perform the transition, with a fallback.

        Args:
            issue_key (str): The key of the issue to transition.
            target_status (str): The name of the target status.

        Returns:
            bool: True if the transition was successful, False otherwise.
        """
        transition_id = self.find_transition_id_by_name(issue_key, target_status)
        if not transition_id:
            return False

        try:
            # The library's `issue_transition` method takes the status name.
            self.client.issue_transition(issue_key, target_status)
            logger.info(
                f"Successfully transitioned '{issue_key}' to '{target_status}' "
                "via library call."
            )
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while transitioning issue '{issue_key}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_transition_issue(issue_key, fields) 
        except Exception as e:
            logger.warning(
                f"Library transition for '{issue_key}' failed. Falling back. Error: {e}"
            )
            # Pass the already found transition_id to the fallback.
            return self._fallback_transition_issue(
                issue_key, transition_id, target_status
            )

    def _fallback_transition_issue(
        self, issue_key: str, transition_id: str, target_status: str
    ) -> bool:
        """Fallback method to transition an issue using a direct REST call."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        payload = {"transition": {"id": transition_id}}
        response = make_request("POST", url, headers=self.headers, json_data=payload, verify_ssl=False)
        if response:
            logger.info(
                f"Successfully transitioned '{issue_key}' to '{target_status}' "
                f"via REST call (ID: {transition_id})."
            )
            return True
        return False

    def get_myself(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the details of the currently authenticated user.

        This is useful for verifying credentials or getting the user's account ID.

        Returns:
            Optional[Dict[str, Any]]: A dictionary of the user's details,
                                      or None on failure.
        """
        url = f"{self.base_url}/rest/api/2/myself"
        response = make_request("GET", url, headers=self.headers, verify_ssl=False)
        if response:
            return response.json()
        return None

    def search_issues(self, jql: str, fields: str = "*all") -> List[Dict[str, Any]]:
        """
        Safely searches Jira issues using JQL.

        Tries to search using the library client and falls back to a
        direct REST API call upon failure.

        Args:
            jql (str): The JQL query string.
            fields (str): A comma-separated list of fields to retrieve.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing issue data.
        """
        try:
            # The atlassian-python-api client's jql method returns JiraIssue objects
            # We need to convert them to raw dictionaries.
            issues = self.client.jql(jql, fields=fields)
            return [issue.raw for issue in issues]
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while searching issues with JQL '{jql}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_search_issues(jql, fields)
        except Exception as e:
            logger.warning(
                f"Library search_issues for JQL '{jql}' failed. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_search_issues(jql, fields)

    def _fallback_search_issues(self, jql: str, fields: str) -> List[Dict[str, Any]]:
        """Fallback method to search issues using a direct REST call."""
        # Ensure JQL is properly quoted for URL
        quoted_jql = requests.utils.quote(jql)
        url = f"{self.base_url}/rest/api/2/search?jql={quoted_jql}&fields={fields}"
        response = make_request("GET", url, headers=self.headers, verify_ssl=False)
        if response:
            return response.json().get("issues", [])
        return []

    def get_issue_type_details_by_id(self, type_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves issue type details by its ID.

        Args:
            type_id (str): The ID of the issue type.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing issue type data,
                                      or None if retrieval fails.
        """
        try:
            # The atlassian-python-api client might not have a direct get_issue_type_by_id.
            # We'll use the direct REST API call as the primary and fallback.
            return self._fallback_get_issue_type_details_by_id(type_id)
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"A network error occurred while getting issue type '{type_id}'. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_issue_type_details_by_id(type_id)
        except Exception as e:
            logger.warning(
                f"Library call for issue type '{type_id}' failed or not available. "
                f"Falling back. Error: {e}"
            )
            return self._fallback_get_issue_type_details_by_id(type_id)

    def _fallback_get_issue_type_details_by_id(self, type_id: str) -> Optional[Dict[str, Any]]:
        """Fallback method to get issue type details by ID using a direct REST call."""
        url = f"{self.base_url}/rest/api/2/issuetype/{type_id}"
        response = make_request("GET", url, headers=self.headers, verify_ssl=False)
        if response:
            return response.json()
        return None