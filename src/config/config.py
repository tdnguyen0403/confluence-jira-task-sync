"""
Application-wide configuration settings.

This module centralizes all configuration variables for the application. It
loads sensitive data (like API tokens and URLs) from environment variables
using `dotenv`, making the application portable and secure. It also defines
project-specific constants and settings that are core to the business logic.
"""

import os
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Only load the .env file if we're NOT running in Docker.
if not os.getenv("RUNNING_IN_CONTAINER"):
    print("--- Running locally: loading .env.dev file ---", file=sys.stderr)
    load_dotenv(dotenv_path=".env.dev")

DEV_ENVIRONMENT: bool = os.getenv("DEV_ENVIRONMENT", "false").lower() == "true"

LOG_DIR = os.getenv("LOG_DIR", "./logs")

VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() == "true"

JIRA_URL: str = os.getenv("JIRA_URL", "https://pfjira.pepperl-fuchs.com/")
CONFLUENCE_URL: str = os.getenv(
    "CONFLUENCE_URL", "https://pfteamspace.pepperl-fuchs.com/"
)

# Check for required environment variables and raise an error if they are missing.
_jira_api_token = os.getenv("JIRA_API_TOKEN")
if not _jira_api_token:
    raise ValueError("Missing required environment variable: JIRA_API_TOKEN")
JIRA_API_TOKEN: str = _jira_api_token

_confluence_api_token = os.getenv("CONFLUENCE_API_TOKEN")
if not _confluence_api_token:
    raise ValueError("Missing required environment variable: CONFLUENCE_API_TOKEN")
CONFLUENCE_API_TOKEN: str = _confluence_api_token

_api_secret_key = os.getenv("API_SECRET_KEY")
if not _api_secret_key:
    raise ValueError("Missing required environment variable: API_SECRET_KEY")
API_SECRET_KEY: str = _api_secret_key

JIRA_MACRO_SERVER_NAME: str = os.getenv("JIRA_MACRO_SERVER_NAME", "P+F Jira")
JIRA_MACRO_SERVER_ID: str = os.getenv(
    "JIRA_MACRO_SERVER_ID", "a9986ca6-387c-3b09-9a85-450e12a1cf94"
)

PARENT_ISSUES_TYPE_ID: Dict[str, str] = {
    "Work Package": os.getenv("JIRA_PARENT_ID_WORK_PACKAGE", "10100"),
    "Risk": os.getenv("JIRA_PARENT_ID_RISK", "11404"),
    "Deviation": os.getenv("JIRA_PARENT_ID_DEVIATION", "10103"),
}
TASK_ISSUE_TYPE_ID: Optional[str] = os.getenv("JIRA_TASK_ISSUE_TYPE_ID", "10002")
JIRA_PROJECT_ISSUE_TYPE_ID: Optional[str] = os.getenv(
    "JIRA_PROJECT_ISSUE_TYPE_ID", "10200"
)
JIRA_PHASE_ISSUE_TYPE_ID: Optional[str] = os.getenv("JIRA_PHASE_ISSUE_TYPE_ID", "11001")
JIRA_WORK_CONTAINER_ISSUE_TYPE_ID: Optional[str] = os.getenv(
    "JIRA_WORK_CONTAINER_ISSUE_TYPE_ID", "11000"
)
JIRA_WORK_PACKAGE_ISSUE_TYPE_ID: Optional[str] = os.getenv(
    "JIRA_WORK_PACKAGE_ISSUE_TYPE_ID", "10100"
)
JIRA_PARENT_WP_CUSTOM_FIELD_ID: Optional[str] = os.getenv(
    "JIRA_PARENT_WP_CUSTOM_FIELD_ID", "customfield_10207"
)

JIRA_TARGET_STATUSES: Dict[str, str] = {
    "new_task_dev": os.getenv("JIRA_STATUS_NEW", "Backlog"),
    "completed_task": os.getenv("JIRA_STATUS_DONE", "Done"),
    "undo": os.getenv("JIRA_STATUS_UNDO", "Backlog"),
}

FUZZY_MATCH_THRESHOLD: float = float(os.getenv("FUZZY_MATCH_THRESHOLD", 0.7))
MAX_CONCURRENT_API_CALLS: int = int(os.getenv("MAX_CONCURRENT_API_CALLS", 50))
API_REQUEST_TIMEOUT: int = int(os.getenv("API_REQUEST_TIMEOUT", 60))

JIRA_SUMMARY_MAX_CHARS: int = int(os.getenv("JIRA_SUMMARY_MAX_CHARS", 255))
JIRA_DESCRIPTION_MAX_CHARS: int = int(os.getenv("JIRA_DESCRIPTION_MAX_CHARS", 2000))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

AGGREGATION_CONFLUENCE_MACRO: List[str] = [
    "jira",
    "jiraissues",
    "excerpt",
    "excerpt-include",
    "include",
    "widget",
    "html",
    "content-report-table",
    "pagetree",
    "recently-updated",
    "table-excerpt",
    "table-excerpt-include",
    "table-filter",
    "table-pivot",
    "table-transformer",
]

BASE_PARENT_CONFLUENCE_PAGE_ID: str = "422189655"
CONFLUENCE_SPACE_KEY: str = "EUDEMHTM0589"
ASSIGNEE_USERNAME_FOR_GENERATED_TASKS: str = "tdnguyen"
TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE: List[str] = [
    "SFSEA-1524",
    "SFSEA-1483",
    "SFSEA-1482",
]
DEFAULT_MAX_DEPTH: int = 10
DEFAULT_TASKS_PER_PAGE: int = 10
DEFAULT_NUM_WORK_PACKAGES: int = 1
DEFAULT_DUE_DATE_FOR_TREE_GENERATION: date = date.today() + timedelta(days=14)

# --- Cache Configuration ---
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
UNDO_EXPIRATION_SECONDS: int = int(os.getenv("UNDO_EXPIRATION_SECONDS", 86400))
