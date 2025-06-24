<<<<<<< HEAD
import datetime

# --- Jira & Confluence Server Configuration ---
# Your Server URLs
JIRA_URL = "https://pfjira.pepperl-fuchs.com/"
CONFLUENCE_URL = "https://pfteamspace.pepperl-fuchs.com/"
# --- Confluence Jira Macro Settings ---
# These values are required by your Confluence instance to correctly render the Jira macro.
# We discovered these by inspecting the storage format of a working macro.
JIRA_MACRO_SERVER_NAME = "P+F Jira"
JIRA_MACRO_SERVER_ID = "a9986ca6-387c-3b09-9a85-450e12a1cf94"
JIRA_MACRO_COLUMN_IDS = "issuekey,summary,issuetype,created,updated,duedate,assignee,reporter,priority,status,resolution"
JIRA_MACRO_COLUMNS = "key,summary,type,created,updated,due,assignee,reporter,priority,status,resolution"

# --- Authentication ---
# Separate Personal Access Tokens (PATs) for Jira and Confluence
JIRA_API_TOKEN = "MTA1NDExOTk0ODcxOl2MOjItIzTXbsHItvwOGYLm0Oz8"
CONFLUENCE_API_TOKEN = "OTE4NzEyNDI3MjM5OpT8xf0edPlNYOh8hsHYXPUg3ah8"


# --- Master Data / Custom IDs ---
# The issue type ID for the main issue we look for on the parent page.
WORK_PACKAGE_ISSUE_TYPE_ID = "10100"

# The issue type ID for the new tasks we will create.
TASK_ISSUE_TYPE_ID = "10002"

# The custom field ID that should store the key of the parent Work Package.
JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"
JIRA_PROJECT_KEY = "SFSEA" # I noticed this from your logs, added it here for completeness


# --- New Task Creation Settings ---

# The name of the status you want the new task to be in AFTER it is created.
JIRA_TARGET_STATUS_NAME = "Backlog"

# Set a default due date.
DEFAULT_DUE_DATE = (datetime.date.today() + datetime.timedelta(days=14)).strftime('%Y-%m-%d')

# --- HTML Parsing Settings ---
# Define a list of known "aggregate" Confluence macros whose content should be ignored
# These macros often include content from other pages or external sources.
AGGREGATE_MACRO_NAMES = [
    "jira",                 # Jira Issue/Filter macro (shows Jira issues, not Confluence tasks)
    "jiraissues",           # Older Jira macro name
    "confiform-table-view", # Example of a third-party macro that might aggregate data
    "excerpt-include",      # Includes content from an excerpt macro on another page
    "include",              # Includes content from another page directly
    "widget",               # Could embed external content
    "html"                  # Can embed arbitrary HTML, potentially from external sources
=======
import datetime

# --- Jira & Confluence Server Configuration ---
# Your Server URLs
JIRA_URL = "https://pfjira.pepperl-fuchs.com/"
CONFLUENCE_URL = "https://pfteamspace.pepperl-fuchs.com/"
# --- Confluence Jira Macro Settings ---
# These values are required by your Confluence instance to correctly render the Jira macro.
# We discovered these by inspecting the storage format of a working macro.
JIRA_MACRO_SERVER_NAME = "P+F Jira"
JIRA_MACRO_SERVER_ID = "a9986ca6-387c-3b09-9a85-450e12a1cf94"
JIRA_MACRO_COLUMN_IDS = "issuekey,summary,issuetype,created,updated,duedate,assignee,reporter,priority,status,resolution"
JIRA_MACRO_COLUMNS = "key,summary,type,created,updated,due,assignee,reporter,priority,status,resolution"

# --- Authentication ---
# Separate Personal Access Tokens (PATs) for Jira and Confluence
JIRA_API_TOKEN = "MTA1NDExOTk0ODcxOl2MOjItIzTXbsHItvwOGYLm0Oz8"
CONFLUENCE_API_TOKEN = "OTE4NzEyNDI3MjM5OpT8xf0edPlNYOh8hsHYXPUg3ah8"


# --- Master Data / Custom IDs ---
# The issue type ID for the main issue we look for on the parent page.
WORK_PACKAGE_ISSUE_TYPE_ID = "10100"

# The issue type ID for the new tasks we will create.
TASK_ISSUE_TYPE_ID = "10002"

# The custom field ID that should store the key of the parent Work Package.
JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"
JIRA_PROJECT_KEY = "SFSEA" # I noticed this from your logs, added it here for completeness


# --- New Task Creation Settings ---

# The name of the status you want the new task to be in AFTER it is created.
JIRA_TARGET_STATUS_NAME = "Backlog"

# Set a default due date.
DEFAULT_DUE_DATE = (datetime.date.today() + datetime.timedelta(days=14)).strftime('%Y-%m-%d')

# --- HTML Parsing Settings ---
# Define a list of known "aggregate" Confluence macros whose content should be ignored
# These macros often include content from other pages or external sources.
AGGREGATE_MACRO_NAMES = [
    "jira",                 # Jira Issue/Filter macro (shows Jira issues, not Confluence tasks)
    "jiraissues",           # Older Jira macro name
    "confiform-table-view", # Example of a third-party macro that might aggregate data
    "excerpt-include",      # Includes content from an excerpt macro on another page
    "include",              # Includes content from another page directly
    "widget",               # Could embed external content
    "html"                  # Can embed arbitrary HTML, potentially from external sources
>>>>>>> 71bb2c8db17e8064fbb838a4b18220e793cc0372
]