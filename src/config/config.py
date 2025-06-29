"""
Application-wide configuration settings.

This module centralizes all configuration variables for the application. It
loads sensitive data (like API tokens and URLs) from environment variables
using `dotenv` and defines project-specific constants and settings.

The configuration is organized into logical sections for clarity:
- Directory and Server Configuration
- Authentication
- Jira and Confluence specific settings
- Automation behavior
- Test data generation settings

"""

import datetime
import json
import logging
import os
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Load environment variables from a .env file if it exists
load_dotenv()

# --- Directory Configuration ---
INPUT_DIRECTORY: str = "input"
OUTPUT_DIRECTORY: str = "output"

# --- Jira & Confluence Server Configuration ---
# Loaded from environment variables for security and flexibility.
JIRA_URL: Optional[str] = os.getenv("JIRA_URL")
CONFLUENCE_URL: Optional[str] = os.getenv("CONFLUENCE_URL")

# --- Authentication ---
JIRA_API_TOKEN: Optional[str] = os.getenv("JIRA_API_TOKEN")
CONFLUENCE_API_TOKEN: Optional[str] = os.getenv("CONFLUENCE_API_TOKEN")
API_SECRET_KEY: Optional[str] = os.getenv("API_SECRET_KEY")

# --- Confluence Jira Macro Settings ---
# These values are specific to your Confluence instance's Jira integration.
JIRA_MACRO_SERVER_NAME: Optional[str] = os.getenv("JIRA_MACRO_SERVER_NAME")
JIRA_MACRO_SERVER_ID: Optional[str] = os.getenv("JIRA_MACRO_SERVER_ID")

# --- Master Data / Custom IDs (Project Specific) ---
# These are hard-coded values specific to the target Jira project setup.
PARENT_ISSUES_TYPE_ID: Dict[str, str] = {
    "Work Package": "10100",
    "Risk": "11404",
    "Deviation": "10103",
}
TASK_ISSUE_TYPE_ID: str = "10002"
# The custom field ID in Jira used to link tasks to a work package.
JIRA_PARENT_WP_CUSTOM_FIELD_ID: str = "customfield_10207"

# --- Automation Settings ---
# Set to True to run in production mode. Should be False for testing.
PRODUCTION_MODE: bool = False
# Defines the target statuses for issue transitions in different scenarios.
JIRA_TARGET_STATUSES: Dict[str, str] = {
    "new_task_dev": "Backlog",
    "completed_task": "Done",
    "undo": "Backlog",
}

# --- HTML Parsing Settings ---
# A list of Confluence macro names whose content should be ignored during
# task extraction to avoid parsing tasks from aggregated content.
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
# These settings are used by the test data generator scripts.
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

# --- Fixed Default Due Date ---
DEFAULT_DUE_DATE_DAYS: int = 14
DEFAULT_DUE_DATE: str = (
    datetime.date.today() + datetime.timedelta(days=DEFAULT_DUE_DATE_DAYS)
).strftime("%Y-%m-%d")
