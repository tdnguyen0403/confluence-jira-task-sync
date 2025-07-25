"""
Application-wide configuration settings.

This module centralizes all configuration variables for the application. It
loads sensitive data (like API tokens and URLs) from environment variables
using `dotenv` and defines project-specific constants and settings.
"""

import os
from datetime import date, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

# --- Environment & Paths ---
# Use an environment variable to distinguish environments. Default to true.
DEV_ENVIRONMENT: bool = os.getenv("DEV_ENVIRONMENT", "false").lower() == "true"

# Define root directory for logs
LOG_DIR = os.getenv("LOG_DIR", "./logs")

# Convert string "true" or "false" from env var to boolean
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() == "true"

# --- Jira & Confluence Server Configuration ---
# Loaded from environment variables for security and flexibility.
JIRA_URL: str = os.getenv("JIRA_URL", "https://pfjira.pepperl-fuchs.com/")
CONFLUENCE_URL: str = os.getenv(
    "CONFLUENCE_URL", "https://pfteamspace.pepperl-fuchs.com/"
)

# --- Authentication ---
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN")
CONFLUENCE_API_TOKEN: str = os.getenv("CONFLUENCE_API_TOKEN")
API_SECRET_KEY: str = os.getenv("API_SECRET_KEY")

# --- Confluence Jira Macro Settings ---
JIRA_MACRO_SERVER_NAME: str = os.getenv("JIRA_MACRO_SERVER_NAME", "P+F Jira")
JIRA_MACRO_SERVER_ID: str = os.getenv(
    "JIRA_MACRO_SERVER_ID", "a9986ca6-387c-3b09-9a85-450e12a1cf94"
)

# --- Master Data / Custom IDs (Loaded from Environment) ---
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

# --- Jira Max Character Limits ---
JIRA_SUMMARY_MAX_CHARS: int = int(os.getenv("JIRA_SUMMARY_MAX_CHARS", 255))
JIRA_DESCRIPTION_MAX_CHARS: int = int(os.getenv("JIRA_DESCRIPTION_MAX_CHARS", 32768))

# --- To adjust LOG LEVEL
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ======================================================================
# The constants below are part of the application's core logic or are
# for specific, non-production scripts. They should NOT be externalized.
# ======================================================================

# --- HTML Parsing Settings ---
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

# --- Test Data Generation Settings ---
BASE_PARENT_CONFLUENCE_PAGE_ID: str = "422189655"
CONFLUENCE_SPACE_KEY: str = "EUDEMHTM0589"
ASSIGNEE_USERNAME_FOR_GENERATED_TASKS: str = "tdnguyen"
TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE: List[str] = [
    "SFSEA-1524",
    "SFSEA-1483",
    "SFSEA-1482",
]
DEFAULT_MAX_DEPTH: int = 2
DEFAULT_TASKS_PER_PAGE: int = 1
DEFAULT_NUM_WORK_PACKAGES: int = 3
DEFAULT_DUE_DATE_FOR_TREE_GENERATION: date = date.today() + timedelta(days=14)
