import os
import json
import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Directory Configuration ---
INPUT_DIRECTORY = "input"
OUTPUT_DIRECTORY = "output"

# --- Jira & Confluence Server Configuration ---
JIRA_URL = os.getenv("JIRA_URL")
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")

# --- Authentication ---
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")

# --- Confluence Jira Macro Settings ---
JIRA_MACRO_SERVER_NAME = os.getenv("JIRA_MACRO_SERVER_NAME")
JIRA_MACRO_SERVER_ID = os.getenv("JIRA_MACRO_SERVER_ID")

# --- Master Data / Custom IDs --- config.py
JIRA_PROJECT_KEY = "SFSEA"
WORK_PACKAGE_ISSUE_TYPE_ID = "10100"
TASK_ISSUE_TYPE_ID = "10002"
JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"

# --- Automation Settings ---
PRODUCTION_MODE = False
JIRA_TARGET_STATUSES = {
    "new_task_dev": "Backlog",
    "completed_task": "Done",
    "undo": "Backlog"
}

# --- HTML Parsing Settings ---
AGGREGATION_CONFLUENCE_MACRO = [
    "jira", "jiraissues", "excerpt", "excerpt-include", "include", "widget", "html", 
    "content-report-table", "pagetree", "recently-updated", "table-excerpt", 
    "table-excerpt-include", "table-filter", "table-pivot", "table-transformer"
]

#--- Test Data Generation Settings --- config.py
BASE_PARENT_CONFLUENCE_PAGE_ID = "422189655"
CONFLUENCE_SPACE_KEY = "EUDEMHTM0589"
ASSIGNEE_USERNAME_FOR_GENERATED_TASKS = "tdnguyen"
TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE = ["SFSEA-777", "SFSEA-882", "SFSEA-883"]

# --- User Inputs (Loaded from JSON) ---
try:
    with open('user_input.json', 'r') as f:
        user_input_config = json.load(f)
    DEFAULT_DUE_DATE_DAYS = user_input_config.get("DEFAULT_DUE_DATE_DAYS", 14)
except FileNotFoundError:
    DEFAULT_DUE_DATE_DAYS = 14 # Fallback if file doesn't exist

DEFAULT_DUE_DATE = (datetime.date.today() + datetime.timedelta(days=DEFAULT_DUE_DATE_DAYS)).strftime('%Y-%m-%d')