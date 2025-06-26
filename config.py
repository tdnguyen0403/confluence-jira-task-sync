import datetime

# --- Jira & Confluence Server Configuration ---
JIRA_URL = "https://pfjira.pepperl-fuchs.com/"
CONFLUENCE_URL = "https://pfteamspace.pepperl-fuchs.com/"

# --- Authentication ---
# Personal Access Tokens (PATs)
JIRA_API_TOKEN = "MTA1NDExOTk0ODcxOl2MOjItIzTXbsHItvwOGYLm0Oz8"
CONFLUENCE_API_TOKEN = "OTE4NzEyNDI3MjM5OpT8xf0edPlNYOh8hsHYXPUg3ah8"

# --- Confluence Jira Macro Settings ---
JIRA_MACRO_SERVER_NAME = "P+F Jira"
JIRA_MACRO_SERVER_ID = "a9986ca6-387c-3b09-9a85-450e12a1cf94"

# --- Master Data / Custom IDs ---
JIRA_PROJECT_KEY = "SFSEA"
WORK_PACKAGE_ISSUE_TYPE_ID = "10100"
TASK_ISSUE_TYPE_ID = "10002"
JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"

# --- Automation Settings ---
JIRA_TARGET_STATUS_NAME = "Backlog"
JIRA_TRANSITION_ID_BACKLOG = "11"
DEFAULT_DUE_DATE = (datetime.date.today() + datetime.timedelta(days=14)).strftime('%Y-%m-%d')

# --- HTML Parsing Settings ---
AGGREGATE_MACRO_NAMES = [
    "jira", "jiraissues", "excerpt-include", "include", "widget", "html"
]

#--- Test Data Generation Settings ---
BASE_PARENT_CONFLUENCE_PAGE_ID = "422189655"
CONFLUENCE_SPACE_KEY = "EUDEMHTM0589"
ASSIGNEE_USERNAME_FOR_GENERATED_TASKS = "tdnguyen"
TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE = ["SFSEA-777", "SFSEA-882", "SFSEA-883"]