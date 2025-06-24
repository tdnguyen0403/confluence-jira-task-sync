# safe_api.py - A resilient service wrapper for all Jira and Confluence API calls.

import logging
import requests
import json
import re
from typing import Optional, Dict, Any, List

from atlassian import Jira, Confluence
from atlassian.errors import ApiError

import config

# A generic exception to raise when a fallback also fails
class FallbackFailedError(Exception):
    pass


class SafeJiraService:
    """
    A resilient wrapper for the Jira client that provides fallback mechanisms
    for all API calls used in the project.
    """

    def __init__(self, jira_client: Jira):
        self.client = jira_client
        self.base_url = config.JIRA_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {config.JIRA_API_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_issue(self, issue_key: str, fields: str = "*all") -> Optional[Dict[str, Any]]:
        """Safely gets issue details with a fallback to requests."""
        try:
            logging.debug(f"Attempting get_issue for '{issue_key}' via library.")
            return self.client.get_issue(issue_key, fields=fields)
        except Exception as e:
            logging.warning(f"Library call get_issue failed for '{issue_key}' ({e}). Falling back.")
            return self._fallback_get_issue(issue_key, fields)

    def _fallback_get_issue(self, issue_key: str, fields: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}?fields={fields}"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_issue for '{issue_key}' failed. Error: {e}")
            return None

    def issue_create(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Safely creates an issue with a fallback to requests."""
        try:
            logging.debug("Attempting issue_create via library.")
            return self.client.issue_create(fields=fields)
        except Exception as e:
            logging.warning(f"Library call issue_create failed ({e}). Falling back.")
            return self._fallback_issue_create(fields)

    def _fallback_issue_create(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/2/issue"
        try:
            response = requests.post(url, headers=self.headers, json=fields, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback issue_create failed. Error: {e}")
            return None

    def get_issue_status(self, issue_key: str) -> Optional[str]:
        """Safely gets an issue's status with a fallback."""
        try:
            logging.debug(f"Attempting get_issue_status for '{issue_key}' via library.")
            return self.client.get_issue_status(issue_key=issue_key)
        except Exception as e:
            logging.warning(f"Library call get_issue_status failed for '{issue_key}' ({e}). Falling back.")
            issue = self.get_issue(issue_key, fields="status")
            return issue.get("fields", {}).get("status", {}).get("name") if issue else None
    
    def transition_issue(self, issue_key: str, target_status: str, transition_id_override: Optional[str] = None) -> bool:
        """
        Safely transitions an issue. It primarily uses the robust `requests`-based
        fallback method as it's more reliable.
        """
        logging.debug(f"Attempting to transition '{issue_key}' to '{target_status}' using SafeJiraService.")
        return self._fallback_transition_issue(issue_key, target_status, transition_id_override)

    def _fallback_transition_issue(self, issue_key: str, target_status: str, transition_id_override: Optional[str] = None) -> bool:
        transitions_url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        try:
            # If an ID is provided (e.g., for 'Backlog'), use it.
            if transition_id_override:
                transition_id = transition_id_override
            else:
                # Otherwise, discover the ID dynamically.
                response_get = requests.get(transitions_url, headers=self.headers, verify=False, timeout=15)
                response_get.raise_for_status()
                available_transitions = response_get.json().get("transitions", [])
                transition_id = next((t["id"] for t in available_transitions if t.get("name", "").lower() == target_status.lower()), None)
            
            if not transition_id:
                current_status = self.get_issue_status(issue_key)
                if current_status and current_status.lower() == target_status.lower():
                    logging.info(f"Issue '{issue_key}' is already in status '{target_status}'.")
                    return True
                logging.error(f"Could not find a transition to '{target_status}' for issue '{issue_key}'.")
                return False

            payload = {"transition": {"id": str(transition_id)}}
            response_post = requests.post(transitions_url, headers=self.headers, json=payload, verify=False, timeout=15)
            response_post.raise_for_status()
            logging.info(f"Successfully transitioned '{issue_key}' to '{target_status}' via REST call (ID: {transition_id}).")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"REST API call failed for issue transition '{issue_key}'. Error: {e}")
            return False


class SafeConfluenceService:
    """
    A resilient wrapper for the Confluence client with fallbacks for all used methods.
    """
    def __init__(self, confluence_client: Confluence):
        self.client = confluence_client
        self.base_url = config.CONFLUENCE_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {config.CONFLUENCE_API_TOKEN}",
            "Content-Type": "application/json",
        }

    def get_page_id_from_url(self, url: str) -> Optional[str]:
        """
        Extracts the Confluence page ID from either a standard long URL or a short link.
        """
        # Check for standard long URL first
        long_url_match = re.search(r'/pages/(\d+)', url)
        if long_url_match:
            return long_url_match.group(1)

        # If not, assume it's a short URL and resolve it
        logging.info(f"  Attempting to resolve short URL: {url}")
        try:
            # The 'requests' library follows redirects by default with allow_redirects=True
            response = requests.head(
                url, headers=self.headers, allow_redirects=True, timeout=15, verify=False
            )
            response.raise_for_status()
            final_url = response.url
            logging.info(f"  Short URL resolved to: {final_url}")

            # Now, extract the ID from the final resolved URL
            resolved_match = re.search(r'/pages/(\d+)', final_url)
            if resolved_match:
                return resolved_match.group(1)
            
            logging.error(f"  ERROR: Could not extract page ID from the final resolved URL: {final_url}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"  ERROR: Could not resolve the short URL '{url}'. Details: {e}")
            return None

    def get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Safely gets a page by its ID with a fallback."""
        try:
            return self.client.get_page_by_id(page_id, **kwargs)
        except Exception as e:
            logging.warning(f"Library call get_page_by_id failed for '{page_id}' ({e}). Falling back.")
            return self._fallback_get_page_by_id(page_id, **kwargs)

    def _fallback_get_page_by_id(self, page_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        url = f"{self.base_url}/rest/api/content/{page_id}"
        try:
            response = requests.get(url, headers=self.headers, params=params, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_page_by_id for '{page_id}' failed. Error: {e}")
            return None

    def get_page_child_by_type(self, page_id: str, type: str = "page") -> List[Dict[str, Any]]:
        """Safely gets child pages with a fallback."""
        try:
            return self.client.get_page_child_by_type(page_id, type=type)
        except Exception as e:
            logging.warning(f"Library call get_page_child_by_type for '{page_id}' failed ({e}). Falling back.")
            return self._fallback_get_page_child_by_type(page_id, type)

    def _fallback_get_page_child_by_type(self, page_id: str, type: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/content/{page_id}/child/{type}"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_page_child_by_type for '{page_id}' failed. Error: {e}")
            return []

    def get_user_details_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Safely gets user details by username with a fallback."""
        try:
            return self.client.get_user_details_by_username(username)
        except Exception as e:
            logging.warning(f"Library call get_user_details_by_username for '{username}' failed ({e}). Falling back.")
            return self._fallback_get_user_details("username", username)

    def get_user_details_by_userkey(self, userkey: str) -> Optional[Dict[str, Any]]:
        """Safely gets user details by userkey with a fallback."""
        try:
            return self.client.get_user_details_by_userkey(userkey)
        except Exception as e:
            logging.warning(f"Library call get_user_details_by_userkey for '{userkey}' failed ({e}). Falling back.")
            return self._fallback_get_user_details("key", userkey)

    def _fallback_get_user_details(self, identifier_type: str, identifier_value: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/user?{identifier_type}={identifier_value}"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback get_user_details for '{identifier_value}' failed. Error: {e}")
            return None
    
    def create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Safely creates a page with a fallback."""
        try:
            return self.client.create_page(**kwargs)
        except Exception as e:
            logging.warning(f"Library call create_page failed ({e}). Falling back.")
            return self._fallback_create_page(**kwargs)

    def _fallback_create_page(self, **kwargs) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/content"
        payload = {
            "type": "page",
            "title": kwargs.get("title"),
            "space": {"key": kwargs.get("space")},
            "body": {"storage": {"value": kwargs.get("body"), "representation": kwargs.get("representation", "storage")}},
            "ancestors": [{"id": kwargs.get("parent_id")}] if kwargs.get("parent_id") else []
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload, verify=False, timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback create_page failed for title '{kwargs.get('title')}'. Error: {e}")
            return None

    def update_page(self, page_id: str, title: str, body: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Safely updates a page with a fallback."""
        try:
            return self.client.update_page(page_id=page_id, title=title, body=body, **kwargs)
        except Exception as e:
            logging.warning(f"Library call update_page for '{page_id}' failed ({e}). Falling back.")
            return self._fallback_update_page(page_id, title, body, **kwargs)

    def _fallback_update_page(self, page_id: str, title: str, body: str, **kwargs) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/content/{page_id}"
        try:
            # An update requires the current version number + 1
            current_page = self.get_page_by_id(page_id, expand="version")
            if not current_page:
                raise FallbackFailedError("Could not retrieve current page version for update.")
            
            new_version = current_page["version"]["number"] + 1
            payload = {
                "version": {"number": new_version},
                "type": "page",
                "title": title,
                "body": {"storage": {"value": body, "representation": "storage"}},
            }
            response = requests.put(url, headers=self.headers, json=payload, verify=False, timeout=20)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, FallbackFailedError) as e:
            logging.error(f"Fallback update_page for '{page_id}' failed. Error: {e}")
            return None

