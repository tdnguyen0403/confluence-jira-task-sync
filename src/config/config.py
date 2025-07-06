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

import json
import logging
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Initialize logger for this module
logger = logging.getLogger(__name__)

# Load environment variables from a .env file if it exists
load_dotenv()

# Base directory of the project (adjust if your project structure is different)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define root directories for logs, inputs, and outputs
LOGS_ROOT_DIR = os.path.join(BASE_DIR, 'logs')
INPUT_ROOT_DIR = os.path.join(BASE_DIR, 'input')
OUTPUT_ROOT_DIR = os.path.join(BASE_DIR, 'output')

ENDPOINT_SUBFOLDERS = {
    # Log subfolders (retaining 'logs_' prefix)
    "log_api": "logs_api",
    "log_generate": "logs_generate",
    "log_sync_task": "logs_sync_task",
    "log_undo_sync_task": "logs_undo_sync_task",
    "log_sync_project": "logs_sync_project",

    # Input subfolders (now with 'input_' prefix)
    "input_sync_task": "input_sync_task",
    "input_generate": "input_generate", 
    "input_undo_sync_task": "input_undo_sync_task",
    "input_sync_project": "input_sync_project",

    # Output subfolders (now with 'output_' prefix)
    "output_sync_task": "output_sync_task",
    "output_generate": "output_generate",
    "output_undo_sync_task": "output_undo_sync_task",
    "output_sync_project": "output_sync_project",
}

def get_log_path(endpoint_name: str, filename: str) -> str:
    """
    Constructs the full path for a log file.
    Args:
        endpoint_name: The name of the endpoint (e.g., "api", "sync").
        filename: The base name of the log file (e.g., "api_run_20250706_112455.log").
    Returns:
        The full path to the log file.
    """
    # Look up the specific log subfolder name using "log_" prefix
    subfolder = ENDPOINT_SUBFOLDERS.get(f"log_{endpoint_name}", f"logs_{endpoint_name}")
    folder_path = os.path.join(LOGS_ROOT_DIR, subfolder)
    os.makedirs(folder_path, exist_ok=True)
    return os.path.join(folder_path, filename)

def get_input_path(endpoint_name: str, filename: str) -> str:
    """
    Constructs the full path for an input file.
    Args:
        endpoint_name: The name of the endpoint (e.g., "sync", "generate").
        filename: The base name of the input file (e.g., "sync_request_20250706_115503_tdnguyen.json").
    Returns:
        The full path to the input file.
    """
    # Look up the specific input subfolder name using "input_" prefix
    subfolder = ENDPOINT_SUBFOLDERS.get(f"input_{endpoint_name}", f"input_{endpoint_name}")
    folder_path = os.path.join(INPUT_ROOT_DIR, subfolder)
    os.makedirs(folder_path, exist_ok=True)
    return os.path.join(folder_path, filename)

def get_output_path(endpoint_name: str, filename: str) -> str:
    """
    Constructs the full path for an output file.
    Args:
        endpoint_name: The name of the endpoint (e.g., "sync", "generate").
        filename: The base name of the output file (e.g., "sync_result_20250706_094824_tdnguyen.json").
    Returns:
        The full path to the output file.
    """
    # Look up the specific output subfolder name using "output_" prefix
    subfolder = ENDPOINT_SUBFOLDERS.get(f"output_{endpoint_name}", f"output_{endpoint_name}")
    folder_path = os.path.join(OUTPUT_ROOT_DIR, subfolder)
    os.makedirs(folder_path, exist_ok=True)
    return os.path.join(folder_path, filename)

def generate_timestamped_filename(prefix: str, suffix: str = '.log', user: Optional[str] = None) -> str:
    """
    Generates a timestamped filename.
    Args:
        prefix: The prefix for the filename (e.g., "api_run", "sync_task_run").
        suffix: The file extension (e.g., ".log", ".json").
        request_user: Optional user identifier to append to the filename.
    Returns:
        The generated filename.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if user:
        return f"{prefix}_{timestamp}_{user}{suffix}"
    return f"{prefix}_{timestamp}{suffix}"

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
# Issue type IDs for different parent issues in Jira for task creation.
PARENT_ISSUES_TYPE_ID: Dict[str, str] = {
    "Work Package": "10100",
    "Risk": "11404",
    "Deviation": "10103",
}
TASK_ISSUE_TYPE_ID: str = "10002"
# Specific Issue Type IDs for Project, Phase, and Work Package for new project confluence page sync.
JIRA_PROJECT_ISSUE_TYPE_ID: str = "10200"
JIRA_PHASE_ISSUE_TYPE_ID: str = "11001"
JIRA_WORK_PACKAGE_ISSUE_TYPE_ID: str = "10100"

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
    date.today() + timedelta(days=DEFAULT_DUE_DATE_DAYS)
).strftime("%Y-%m-%d")
