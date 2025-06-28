import datetime

# --- Jira & Confluence Server Configuration --- .evn
JIRA_URL = "https://pfjira.pepperl-fuchs.com/"
CONFLUENCE_URL = "https://pfteamspace.pepperl-fuchs.com/"

# --- Authentication --- .evn
# Personal Access Tokens (PATs)
JIRA_API_TOKEN = "MTA1NDExOTk0ODcxOl2MOjItIzTXbsHItvwOGYLm0Oz8"
CONFLUENCE_API_TOKEN = "OTE4NzEyNDI3MjM5OpT8xf0edPlNYOh8hsHYXPUg3ah8"

# --- Confluence Jira Macro Settings --- .evn
JIRA_MACRO_SERVER_NAME = "P+F Jira"
JIRA_MACRO_SERVER_ID = "a9986ca6-387c-3b09-9a85-450e12a1cf94"

# --- Master Data / Custom IDs --- config.py
JIRA_PROJECT_KEY = "SFSEA"
WORK_PACKAGE_ISSUE_TYPE_ID = "10100"
TASK_ISSUE_TYPE_ID = "10002"
JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"

# --- Automation Settings ---  config.py
JIRA_TARGET_STATUS_NAME = "Backlog"
JIRA_TRANSITION_ID_BACKLOG = "11"


# --- HTML Parsing Settings --- config.py
AGGREGATION_CONFLUENCE_MACRO = [
    "jira", "jiraissues", "excerpt","excerpt-include", "include", "widget", "html", "content-report-table", "pagetree", "recently-updated", "table-excerpt", "table-excerpt-include", "table-filter", "table-pivot", "table-transformer"
]

#--- Test Data Generation Settings --- config.py
BASE_PARENT_CONFLUENCE_PAGE_ID = "422189655"
CONFLUENCE_SPACE_KEY = "EUDEMHTM0589"
ASSIGNEE_USERNAME_FOR_GENERATED_TASKS = "tdnguyen"
TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE = ["SFSEA-777", "SFSEA-882", "SFSEA-883"]

# --- User Inputs --- .json
DEFAULT_DUE_DATE = (datetime.date.today() + datetime.timedelta(days=14)).strftime('%Y-%m-%d')