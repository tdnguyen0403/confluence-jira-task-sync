import logging
import requests
from typing import Optional, Dict, Any

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

    def create_issue(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return self.client.issue_create(fields=fields)
        except Exception as e:
            logging.warning(f"Library create_issue failed. Falling back. Error: {e}")
            return self._fallback_create_issue(fields)

    def _fallback_create_issue(self, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/2/issue"
        try:
            response = requests.post(url, headers=self.headers, json=fields, verify=False, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Fallback create_issue failed. Error: {e}")
            return None

    def transition_issue(self, issue_key: str, target_status: str, transition_id: str) -> bool:
        try:
            self.client.transition_issue(issue_key, transition_id)
            logging.info(f"Successfully transitioned '{issue_key}' to '{target_status}' via library call.")
            return True
        except Exception as e:
            logging.warning(f"Library transition for '{issue_key}' failed. Falling back. Error: {e}")
            return self._fallback_transition_issue(issue_key, transition_id, target_status)

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