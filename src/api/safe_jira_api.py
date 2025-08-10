"""
Provides a resilient, low-level API wrapper for Jira operations.

This module contains the SafeJiraApi class, which is responsible for all
direct communication with the Jira REST API. It is designed for robustness and
high performance by using the asynchronous `HTTPSHelper` for all its network
interactions. This ensures that calls to the Jira API are fault-tolerant,
benefiting from connection pooling and automatic retries on transient errors.

The class provides a clean, asynchronous interface for common Jira actions,
including:
-   Creating and retrieving issues.
-   Searching for issues using JQL.
-   Managing issue workflows by finding and executing transitions.
-   Updating issue details, such as the description.
-   Fetching user and issue type metadata.

This wrapper simplifies interactions with the Jira API, enforces consistent
error handling, and improves the overall reliability of Jira-dependent services.
"""

import logging
from typing import Any, Dict, List, Optional

from src.api.error_handler_api import handle_api_errors
from src.api.https_helper import HTTPSHelper
from src.config import config
from src.exceptions import JiraApiError

logger = logging.getLogger(__name__)


class SafeJiraApi:
    """
    Provides a safe and resilient wrapper for Jira API interactions using an
    asynchronous HTTPS helper. This class abstracts the direct API calls for
    creating, retrieving, and transitioning Jira issues.

    Attributes:
        base_url (str): The base URL of the Jira instance.
        https_helper (HTTPSHelper): An instance of the asynchronous HTTPSHelper for
                                    making HTTP requests.
        headers (Dict[str, str]): A dictionary of default headers, including
                                  authorization, for all API requests.
    """

    def __init__(self, base_url: str, https_helper: HTTPSHelper):
        """
        Initializes the SafeJiraApi.

        Args:
            base_url (str): The base URL of the Jira instance (e.g.,
                            "https://your-domain.atlassian.net").
            https_helper (HTTPSHelper): An initialized instance of the
                                        asynchronous HTTPSHelper.
        """
        self.base_url = config.JIRA_URL.rstrip("/")
        self.JIRA_API_PATH = "/rest/api/2"
        self.https_helper = https_helper
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.JIRA_API_TOKEN}",
        }

    @handle_api_errors(JiraApiError)
    async def get_issue(
        self, issue_key: str, fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Retrieves a single Jira issue by its key asynchronously.

        Args:
            issue_key (str): The key of the issue to retrieve (e.g., "PROJ-123").
            fields (Optional[List[str]]): A list of specific fields to return for
                                          the issue. If None, all fields are
                                          returned. Defaults to None.

        Returns:
            Dict[str, Any]: A dictionary representing the Jira issue.

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper`
            if the request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/issue/{issue_key}"
        params = {"fields": ",".join(fields)} if fields else {}
        return await self.https_helper.get(url, headers=self.headers, params=params)

    @handle_api_errors(JiraApiError)
    async def create_issue(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a new Jira issue asynchronously.

        The `fields` dictionary must contain all required fields for issue
        creation as defined in the target Jira project's configuration.

        Example fields:
        {
            "project": {"key": "PROJ"},
            "issuetype": {"name": "Task"},
            "summary": "A new task created via API",
            "description": "This is the detailed description of the task."
        }

        Args:
            fields (Dict[str, Any]): A dictionary of fields for the new issue.

        Returns:
            Dict[str, Any]: A dictionary representing the newly created Jira issue,
                            including its key and ID.

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper`
            if the request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/issue"
        payload = {"fields": fields}

        return await self.https_helper.post(
            url, headers=self.headers, json_data=payload
        )

    @handle_api_errors(JiraApiError)
    async def assign_issue(
        self, issue_key: str, assignee_name: Optional[str]
    ) -> Dict[str, Any]:
        """
        Assigns a Jira issue to a specified user or unassigns it.

        Args:
            issue_key (str): The key of the issue to assign (e.g., "PROJ-123").
            assignee_name (Optional[str]): The username of the user to assign the
                                           issue to. If None, the issue will be
                                           explicitly unassigned.

        Returns:
            Dict[str, Any]: The response from Jira (often an empty dict on success).

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper`
            if the request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/issue/{issue_key}/assignee"

        payload: Dict[str, Any] = {}
        if assignee_name:
            payload = {"name": assignee_name}
            logger.debug(f"Attempting to assign issue {issue_key} to '{assignee_name}'")
        else:
            # According to Jira API documentation for /assignee endpoint,
            # sending a payload with "name": null (or "accountId": null)
            # is the way to explicitly unassign an issue.
            payload = {"name": None}  # Sending {"name": null}
            logger.debug(f"Attempting to explicitly unassign issue {issue_key}")

        return await self.https_helper.put(url, headers=self.headers, json_data=payload)

    @handle_api_errors(JiraApiError)
    async def get_available_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Retrieves all available workflow transitions for a given Jira issue.

        This method is useful for discovering the possible next steps in an
        issue's lifecycle, which can then be used with `transition_issue`.

        Args:
            issue_key (str): The key of the issue (e.g., "PROJ-123").

        Returns:
            List[Dict[str, Any]]: A list of available transition objects, where
                                  each object contains details like `id` and `name`.

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper`
            if the request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/issue/{issue_key}/transitions"
        response_data = await self.https_helper.get(url, headers=self.headers)
        return response_data.get("transitions", [])

    @handle_api_errors(JiraApiError)
    async def find_transition_id_by_name(
        self, issue_key: str, transition_name: str
    ) -> Optional[str]:
        """
        Finds the ID of a transition by its name for a given Jira issue.

        This is a helper method that fetches all available transitions and
        searches for one with a matching name (case-insensitive).

        Args:
            issue_key (str): The key of the issue (e.g., "PROJ-123").
            transition_name (str): The name of the target transition (e.g.,
                                   "In Progress", "Done").

        Returns:
            Optional[str]: The ID of the found transition, or None if no
                           transition with that name is available.
        """
        transitions = await self.get_available_transitions(issue_key)
        for transition in transitions:
            if transition.get("name", "").lower() == transition_name.lower():
                return transition["id"]

        logger.warning(
            f"Transition '{transition_name}' not found for issue {issue_key}."
        )
        return None

    @handle_api_errors(JiraApiError)
    async def transition_issue(
        self, issue_key: str, transition_name: str
    ) -> Dict[str, Any]:
        """
        Transitions a Jira issue to a new status by its transition name.

        This method first finds the correct transition ID for the given name
        and then executes the transition.

        Args:
            issue_key (str): The key of the issue to transition (e.g., "PROJ-123").
            transition_name (str): The name of the workflow transition to execute
                                   (e.g., "Start Progress").

        Returns:
            Dict[str, Any]: An empty dictionary on success (for a 204 No Content
                            response), or a dictionary with response data if
                            the server provides one.

        Raises:
            ValueError: If a transition with the given name cannot be found for
                        the issue.
            Exception: Propagates exceptions from the `HTTPSHelper` if the API
                       request fails.
        """
        transition_id = await self.find_transition_id_by_name(
            issue_key, transition_name
        )

        if not transition_id:
            raise ValueError(
                f"Transition '{transition_name}' not found for issue {issue_key}"
            )

        url = f"{self.base_url}{self.JIRA_API_PATH}/issue/{issue_key}/transitions"
        payload = {"transition": {"id": transition_id}}

        response = await self.https_helper.post(
            url, headers=self.headers, json_data=payload
        )
        return response

    @handle_api_errors(JiraApiError)
    async def get_current_user(self) -> Dict[str, Any]:
        """
        Retrieves information about the current authenticated Jira user.

        This is often used for health checks to verify API connectivity and
        authentication.

        Returns:
            Dict[str, Any]: A dictionary containing details about the currently
                            authenticated user.

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper`
            if the request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/myself"

        return await self.https_helper.get(url, headers=self.headers)

    @handle_api_errors(JiraApiError)
    async def search_issues(
        self, jql_query: str, fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes a JQL query and returns matching issues asynchronously.

        Args:
            jql_query (str): The JQL (Jira Query Language) string to execute.
            fields (Optional[List[str]]): A list of specific fields to return for
                                          each matching issue. If None, default
                                          fields are returned. Defaults to None.

        Returns:
            Dict[str, Any]: A dictionary containing the search results, including
                            a list of issues.

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper`
            if the request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/search"
        params = {"jql": jql_query}
        if fields:
            params["fields"] = ",".join(fields)

        return await self.https_helper.get(url, headers=self.headers, params=params)

    @handle_api_errors(JiraApiError)
    async def get_issue_type_by_id(
        self, issue_type_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves details for a specific Jira issue type by its ID.

        Args:
            issue_type_id (str): The ID of the issue type to retrieve.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing details of the
                                      issue type, or None if an error occurs.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/issuetype/{issue_type_id}"

        return await self.https_helper.get(url, headers=self.headers)

    @handle_api_errors(JiraApiError)
    async def update_issue_description(
        self, issue_key: str, new_description: str
    ) -> Dict[str, Any]:
        """
        Updates the description of a Jira issue asynchronously.

        This method performs a `PUT` request to modify only the `description`
        field of an existing issue.

        Args:
            issue_key (str): The key of the issue to update (e.g., "PROJ-123").
            new_description (str): The new description text for the issue.

        Returns:
            Dict[str, Any]: An empty dictionary on success (for a 204 No Content
                            response), or a dictionary containing response data.

        Raises:
            Exception: Propagates exceptions from the `HTTPSHelper` if the API
                       request fails.
        """
        url = f"{self.base_url}{self.JIRA_API_PATH}/issue/{issue_key}"
        payload = {"fields": {"description": new_description}}

        response = await self.https_helper.put(
            url, headers=self.headers, json_data=payload
        )
        return response
