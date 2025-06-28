import logging
import requests
from typing import Optional, Dict, Any, List

from atlassian import Jira
import config

class SafeJiraApi:
    """A resilient, low-level service for all Jira operations."""
    def __init__(self, jira_client: Jira):
        self.client = jira_client
        self.base_url = config.JIRA_URL.rstrip('/')
        self.headers = {"Authorization": f"Bearer {config.JIRA_API_TOKEN}", "Content-Type": "application/json"}

    def get_issue(self, issue_key: str, fields: str = "*all") -> Optional[Dict[str, Any]]:
        try:
            return self.client.get_issue(issue_key, fields=fields)
        except Exception as e:
            logging.warning(f"Library get_issue for '{issue_key}' failed. Falling back. Error: {e}")
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

    def create_issue(self, issue_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return self.client.issue_create(fields=issue_fields["fields"])
        except Exception as e:
            logging.warning(f"Library create_issue failed. Falling back. Error: {e}")
            return self._fallback_create_issue(issue_fields)

    def _fallback_create_issue(self, issue_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/2/issue"
        try:
            response = requests.post(url, headers=self.headers, json=issue_fields, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback create_issue failed. Error: {e}")
            return None
    def get_available_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """Gets all available transitions for a given issue."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json().get("transitions", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"Could not get transitions for '{issue_key}'. Error: {e}")
            return []

    def find_transition_id_by_name(self, issue_key: str, target_status: str) -> Optional[str]:
        """Finds a transition ID by its target status name."""
        transitions = self.get_available_transitions(issue_key)
        for t in transitions:
            if str(t.get("to", {}).get("name", "")).lower() == target_status.lower():
                return t["id"]
        logging.error(f"Transition to status '{target_status}' not available for issue '{issue_key}'.")
        return None
        
    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """Transitions an issue to a target status by dynamically finding the transition ID."""
        transition_id = self.find_transition_id_by_name(issue_key, target_status)
        if not transition_id:
            return False
            
        try:
            # The atlassian-python-api client.issue_transition expect string for transition_status
            self.client.issue_transition(issue_key, target_status)
            logging.info(f"Successfully transitioned '{issue_key}' to '{target_status}' via library call.")
            return True
            
        except Exception as e:
            logging.warning(f"Library transition for '{issue_key}' failed. Falling back. Error: {e}")
            return self._fallback_transition_issue(issue_key, transition_id, target_status) #fallback and pass transition_id to the fallback call


    def _fallback_transition_issue(self, issue_key: str, transition_id: str, target_status: str) -> bool:
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        payload = {"transition": {"id": transition_id}}
        try:
            response = requests.post(url, headers=self.headers, json=payload, verify=False, timeout=15)
            response.raise_for_status()
            logging.info(f"Successfully transitioned '{issue_key}' to '{target_status}' via REST call (ID: {transition_id}).")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback transition for '{issue_key}' failed. Error: {e}")
            return False
            
    def get_myself(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the details of the currently authenticated user.
        """
        url = f"{self.base_url}/rest/api/2/myself"
        try:
            response = requests.get(url, headers=self.headers, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get current user details. Error: {e}")
            return None
