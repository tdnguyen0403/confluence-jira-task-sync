<<<<<<< HEAD
# main.py - Standard standalone file format with __main__ block (Corrected KeyError and Uncommented Transition)

import pandas as pd
import re
import datetime
import uuid
import requests
import os
import logging
import sys

import config

from atlassian import Confluence, Jira
from atlassian.errors import ApiError
from bs4 import BeautifulSoup


# --- Suppress SSL Warnings ---
import warnings
import urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
# -----------------------------

# Global logger instance (will be configured in run_automation_script)
logger = logging.getLogger(__name__)

# Global API client instances (will be initialized in run_automation_script)
confluence = None
jira = None

# --- Helper Function for Logging Setup ---
def _setup_logging(timestamp):
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file_name = os.path.join(log_dir, f'automation_run_{timestamp}.log')

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

       # FileHandler with UTF-8 encoding
        file_handler = logging.FileHandler(log_file_name, encoding='utf-8') # <--- Added encoding='utf-8'
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging initialized. Output will be saved to '{log_file_name}'")

# --- Helper Function for API Client Initialization ---
def _initialize_api_clients():
    global confluence, jira
    logger.info("Initializing API clients for Server instances...")
    confluence = Confluence(
        url=config.CONFLUENCE_URL,
        token=config.CONFLUENCE_API_TOKEN,
        cloud=False,
        verify_ssl=False
    )
    jira = Jira(
        url=config.JIRA_URL,
        token=config.JIRA_API_TOKEN,
        cloud=False,
        verify_ssl=False
    )


# --- 2. HELPER AND LOGIC FUNCTIONS (Refactored) ---

def get_all_child_pages_recursive(start_page_id):
    """
    Recursively finds all descendant pages (children, grandchildren, etc.) of a given page.
    """
    all_child_ids = []
    try:
        children = confluence.get_page_child_by_type(start_page_id, type='page')
        for child in children:
            child_id = child['id']
            all_child_ids.append(child_id)
            all_child_ids.extend(get_all_child_pages_recursive(child_id))
    except ApiError as e:
        logger.error(f"  ERROR: Confluence API error getting children for page {start_page_id}. Details: {e}")
    except Exception as e:
        logger.error(f"  ERROR: Unexpected error getting children for page {start_page_id}. Details: {repr(e)}")
    return all_child_ids


def _extract_page_id_from_long_url(url):
    """Pure function to extract page ID from a standard Confluence long URL."""
    long_url_match = re.search(r'/pages/(\d+)', url)
    if long_url_match:
        return long_url_match.group(1)
    return None

def _resolve_short_url_to_long_url(short_url, token):
    """Performs an authenticated HEAD request to resolve a short Confluence URL."""
    logger.info(f"  Attempting to resolve short URL: {short_url}")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.head(
            short_url, headers=headers, allow_redirects=True, timeout=15, verify=False
        )
        response.raise_for_status()
        final_url = response.url
        logger.info(f"  Short URL resolved to: {final_url}")
        return final_url
    except requests.exceptions.RequestException as e:
        logger.error(f"  ERROR: Could not resolve the short URL '{short_url}'. Details: {e}")
        return None

def get_page_id_from_any_url(url, token):
    """Extracts the Confluence page ID from either a standard long URL or a short link."""
    page_id = _extract_page_id_from_long_url(url)
    if page_id:
        return page_id

    resolved_url = _resolve_short_url_to_long_url(url, token)
    if resolved_url:
        page_id = _extract_page_id_from_long_url(resolved_url)
        if page_id:
            return page_id
        else:
            logger.error(f"  ERROR: Resolved URL '{resolved_url}' did not contain a page ID.")
            return None
    return None

def _parse_jira_macros_from_html(html_content):
    """Extracts non-aggregate Jira macro elements from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    jira_macros = soup.find_all('ac:structured-macro', {'ac:name': 'jira'})

    clean_macros = []
    for macro in jira_macros:
        is_within_aggregate_macro = False
        for parent_macro_name in config.AGGREGATE_MACRO_NAMES:
            if (parent_macro_name != 'jira' and
                macro.find_parent('ac:structured-macro', {'ac:name': parent_macro_name})):
                is_within_aggregate_macro = True
                break
        if not is_within_aggregate_macro:
            clean_macros.append(macro)
    return clean_macros

def _get_jira_issue_details(issue_key):
    """Fetches specific Jira issue fields (issuetype, assignee, reporter)."""
    try:
        return jira.get_issue(issue_key, fields="issuetype,assignee,reporter")
    except ApiError as e:
        if e.response.status_code == 404:
            logger.warning(f"  WARNING: Jira issue '{issue_key}' not found or not accessible.")
        else:
            logger.error(f"  ERROR: Jira API error fetching issue '{issue_key}'. Details: {e}")
    except Exception as e:
        logger.error(f"  ERROR: Unexpected error fetching Jira issue '{issue_key}'. Details: {repr(e)}")
    return None

def _is_work_package(jira_issue_details):
    """Checks if a Jira issue dictionary represents a Work Package."""
    if jira_issue_details:
        issue_type_id = jira_issue_details.get('fields', {}).get('issuetype', {}).get('id')
        return issue_type_id == config.WORK_PACKAGE_ISSUE_TYPE_ID
    return False

def find_work_package_on_page_content(page_id):
    """
    Checks a Confluence page's *own content* for a linked Jira issue by parsing the page HTML.
    Returns the Jira issue object of the Work Package if found, otherwise None.
    """
    logger.info(f"  Searching for Work Package on page ID: {page_id}...")
    try:
        page_content_data = confluence.get_page_by_id(page_id, expand='body.storage')
        html_body = page_content_data['body']['storage']['value']

        jira_macros = _parse_jira_macros_from_html(html_body)

        if not jira_macros:
            logger.info(f"  INFO: No Jira macros (non-aggregate) found on page {page_id}.")
            return None

        for macro in jira_macros:
            key_param = macro.find('ac:parameter', {'ac:name': 'key'})
            if not key_param:
                continue
            issue_key = key_param.get_text()

            jira_issue = _get_jira_issue_details(issue_key)
            if _is_work_package(jira_issue):
                logger.info(f"  SUCCESS: Found Work Package '{issue_key}' on page {page_id}.")
                return jira_issue
    except Exception as e:
        logger.error(f"  ERROR: Failed to process page {page_id} for Work Package. Details: {repr(e)}")

    logger.info(f"  INFO: No Work Package found on page {page_id}.")
    return None


def _get_page_ancestors_info(page_id):
    """Gets the list of ancestor page IDs and titles, from furthest to closest."""
    ancestors = []
    try:
        page_info = confluence.get_page_by_id(page_id, expand='ancestors')
        if 'ancestors' in page_info and page_info['ancestors']:
            for ancestor in page_info['ancestors']:
                ancestors.append({'id': ancestor['id'], 'title': ancestor['title']})
        # Add the current page itself as the closest "ancestor" for WP check
        ancestors.append({'id': page_info['id'], 'title': page_info['title']})
    except ApiError as e:
        logger.error(f"  ERROR: Confluence API error getting ancestors for page {page_id}. Details: {e}")
    except Exception as e:
        logger.error(f"  ERROR: Unexpected error getting ancestors for page {page_id}. Details: {repr(e)}")
    return ancestors


def get_closest_ancestor_work_package(current_page_id):
    """
    Traverses up the Confluence page hierarchy to find the closest ancestor (including the current page)
    that contains a Work Package Jira issue.
    Returns the Jira issue object of the Work Package if found, otherwise None.
    """
    logger.info(f"  Searching for closest Work Package ancestor for page ID: {current_page_id}")
    ancestor_chain = _get_page_ancestors_info(current_page_id)

    for page_info in reversed(ancestor_chain):
        wp_issue = find_work_package_on_page_content(page_info['id'])
        if wp_issue:
            logger.info(f"  -> Found Work Package '{wp_issue['key']}' on closest relevant page: '{page_info['title']}' (ID: {page_info['id']})")
            return wp_issue

    logger.info(f"  -> No Work Package found on page {current_page_id} or any of its ancestors.")
    return None

def _get_confluence_page_details(page_id):
    """
    Fetches full page content, title, web URL, and version details.
    Handles potential missing 'version' key by providing defaults.
    """
    try:
        # Ensure 'version' is expanded
        page = confluence.get_page_by_id(page_id, expand='body.storage,links.webui,version')
        
        page_title = page['title']
        page_content = page['body']['storage']['value']
        links_dict = page.get('links', {})
        page_url = links_dict.get('webui', f"URL-Not-Found-For-Page-ID-{page_id}")

        # Safely get version details using .get() to avoid KeyError if 'version' or sub-keys are missing
        version_info = page.get('version', {})
        version_number = version_info.get('number', 0)
        version_by = version_info.get('by', {}).get('displayName', 'Unknown')
        version_when = version_info.get('when', 'N/A')

        return {
            'id': page_id,
            'title': page_title,
            'url': page_url,
            'content': page_content,
            'version_number': version_number,
            'version_by': version_by,
            'version_when': version_when
        }
    except ApiError as e:
        logger.error(f"  ERROR: Confluence API error fetching page {page_id} details. Details: {e}")
    except Exception as e:
        # Log the full page object if 'version' key is unexpectedly missing from the response
        logger.error(f"  ERROR: Unexpected error fetching page {page_id} details. Details: {repr(e)}")
        # Attempt to re-fetch with minimal expand to see the basic structure if version fails
        try:
            basic_page_info = confluence.get_page_by_id(page_id)
            logger.error(f"  Basic page info without version expand: {basic_page_info}")
        except Exception as inner_e:
            logger.error(f"  Failed to get basic page info too: {repr(inner_e)}")
    return None

def _extract_confluence_tasks_from_html(html_content):
    """Extracts ac:task elements, filtering out those within aggregate macros."""
    soup = BeautifulSoup(html_content, 'html.parser')
    confluence_tasks = soup.find_all('ac:task')
    clean_tasks = []
    for task_element in confluence_tasks:
        is_within_aggregate_macro = False
        current_tag = task_element.parent
        while current_tag:
            if (current_tag.name == 'ac:structured-macro' and
                current_tag.get('ac:name') in config.AGGREGATE_MACRO_NAMES):
                is_within_aggregate_macro = True
                logger.debug(f"    Skipping potential task within aggregate macro: {task_element.get_text().strip()}")
                break
            current_tag = current_tag.parent
        if not is_within_aggregate_macro:
            clean_tasks.append(task_element)
    return clean_tasks

def _get_assignee_from_confluence_userkey(user_key):
    """Looks up assignee username from Confluence userkey."""
    try:
        user_details = confluence.get_user_details_by_userkey(user_key)
        return user_details['username']
    except Exception as e:
        logger.warning(f"      WARNING: Could not look up user with key '{user_key}'. Details: {repr(e)}")
    return None

def _parse_single_confluence_task(task_html_element, page_info, default_wp_assignee_name):
    """
    Parses a single 'ac:task' BeautifulSoup element and returns extracted data.
    Returns None if the task is complete or invalid.
    """
    task_body_tag = task_html_element.find('ac:task-body')
    status_tag = task_html_element.find('ac:task-status')
    task_id_tag = task_html_element.find('ac:task-id')

    if not task_body_tag or not task_id_tag:
        logger.debug("    Skipping task element due to missing body or ID tag.")
        return None

    task_summary = task_body_tag.get_text().strip()
    task_status = status_tag.get_text() if status_tag else 'incomplete'
    confluence_task_id = task_id_tag.get_text()

    if task_status != 'incomplete':
        logger.info(f"    - Task '{task_summary}' (ID: {confluence_task_id}) is COMPLETE. Skipping.")
        return None

    task_assignee_name = None
    user_mention_tag = task_html_element.find('ri:user')
    if user_mention_tag and user_mention_tag.has_attr('ri:userkey'):
        user_key_from_confluence = user_mention_tag['ri:userkey']
        task_assignee_name = _get_assignee_from_confluence_userkey(user_key_from_confluence)

    assignee_to_use = task_assignee_name if task_assignee_name else default_wp_assignee_name

    date_tag = task_html_element.find('time')
    due_date_to_use = date_tag['datetime'] if date_tag and date_tag.has_attr('datetime') else config.DEFAULT_DUE_DATE

    logger.info(
        f"    - Found INCOMPLETE Task | ID: {confluence_task_id} | Due: {due_date_to_use} | Assignee: {assignee_to_use or '(none)'} | Summary: '{task_summary}'"
    )

    return {
        'confluence_page_id': page_info['id'],
        'confluence_page_title': page_info['title'],
        'confluence_page_url': page_info['url'],
        'confluence_task_id': confluence_task_id, # Log the explicit Confluence Task ID
        'task_summary': task_summary,
        'assignee_name': assignee_to_use,
        'due_date': due_date_to_use,
        'original_page_version': page_info['version_number'], # ADDED: Original page version
        'original_page_version_by': page_info['version_by'], # ADDED: Original version author
        'original_page_version_when': page_info['version_when'] # ADDED: Original version timestamp
    }


def process_confluence_page_for_tasks(page_id, default_wp_assignee_name):
    """
    Reads a Confluence page, finds incomplete tasks (excluding aggregate macros),
    and returns their parsed data. This function does NOT create Jira tasks.
    """
    page_tasks_data = []
    page_info = _get_confluence_page_details(page_id)
    if not page_info:
        return []

    logger.info(f"  Scanning page '{page_info['title']}' (ID: {page_info['id']}) for tasks...")

    clean_tasks = _extract_confluence_tasks_from_html(page_info['content'])

    if not clean_tasks:
        logger.info(f"  No valid tasks found on page '{page_info['title']}' (ID: {page_info['id']}).")
        return []

    for task_element in clean_tasks:
        parsed_task = _parse_single_confluence_task(task_element, page_info, default_wp_assignee_name)
        if parsed_task:
            page_tasks_data.append(parsed_task)

    return page_tasks_data


def _prepare_jira_task_fields(task_data, parent_key, assignee_name):
    """Prepares the fields dictionary for Jira issue creation."""
    description_string = (
        f"This task was automatically generated from a Confluence checklist.\n\n"
        f"*Original Task:*\n{task_data['task_summary']}\n\n"
        f"*Source Page:*\n[{task_data['confluence_page_title']}|{task_data['confluence_page_url']}]"
    )
    issue_fields = {
        "project": {"key": config.JIRA_PROJECT_KEY},
        "summary": task_data['task_summary'],
        "issuetype": {"id": config.TASK_ISSUE_TYPE_ID},
        "description": description_string,
        "duedate": task_data['due_date'],
        config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
    }
    if assignee_name:
        issue_fields["assignee"] = {"name": assignee_name}
    return issue_fields

def _perform_jira_issue_creation(issue_fields):
    """Performs the actual Jira issue creation API call."""
    try:
        new_issue = jira.issue_create(fields=issue_fields)
        return new_issue['key']
    except Exception as e:
        logger.error(
            f"    -> ERROR: Failed to create Jira task for summary '{issue_fields.get('summary', 'N/A')}'."
            f" Details: {repr(e)}"
        )
    return None

def _perform_jira_transition_direct(issue_key, target_status_name, jira_url, jira_api_token):
    """
    Attempts to transition a Jira issue to a target status using direct requests.
    """
    # Uncommented as per request.
    if not target_status_name or target_status_name.lower() != 'backlog':
        logger.warning(
            f"    -> WARNING: Transition to '{target_status_name}' is not supported via hardcoded ID for {issue_key}."
            " Manual transition may be needed."
        )
        return

    transition_id = 11 # Hardcoded for 'Backlog'

    transition_url = f"{jira_url}/rest/api/2/issue/{issue_key}/transitions"
    headers = {
        "Authorization": f"Bearer {jira_api_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "transition": {
            "id": str(transition_id) # ID must be a string in the payload
        }
    }

    try:
        response = requests.post(transition_url, headers=headers, json=payload, verify=False)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        logger.info(f"    -> Successfully transitioned Jira issue {issue_key} to '{target_status_name}' (ID: {transition_id}).")
    except requests.exceptions.HTTPError as e:
        logger.warning(
            f"    -> WARNING: HTTPError during transition for {issue_key} to '{target_status_name}'. Status:"
            f" {e.response.status_code}, Response: {e.response.text}. Details: {e}"
        )
    except requests.exceptions.RequestException as e:
        logger.warning(
            f"    -> WARNING: Request error during transition for {issue_key} to '{target_status_name}'. Details: {e}"
        )
    except Exception as e:
        logger.warning(
            f"    -> WARNING: Unexpected error during transition for {issue_key} to '{target_status_name}'. Details: {repr(e)}"
        )


def create_jira_task(task_data, parent_key, final_assignee_name):
    """
    Orchestrates the creation of a Jira task, preparing fields, creating the issue,
    and attempting a transition.
    """
    logger.info(f"      -> Status is INCOMPLETE. Creating Jira task for '{task_data['task_summary']}'...")
    issue_fields = _prepare_jira_task_fields(task_data, parent_key, final_assignee_name)
    new_jira_key = _perform_jira_issue_creation(issue_fields)

    if new_jira_key:
        _perform_jira_transition_direct(new_jira_key, config.JIRA_TARGET_STATUS_NAME, config.JIRA_URL, config.JIRA_API_TOKEN)

    return new_jira_key


def _generate_jira_macro_xml(jira_key):
    """Generates the Confluence storage format XML for a Jira macro."""
    return (
        f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1"'
        f' ac:macro-id="{str(uuid.uuid4())}"><ac:parameter'
        f' ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter><ac:parameter'
        f' ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter><ac:parameter'
        f' ac:name="key">{jira_key}</ac:parameter></ac:structured-macro></p>'
    )

def _insert_jira_macro_and_remove_task(soup, confluence_task_id, new_jira_key):
    """Inserts a Jira macro into the BeautifulSoup tree and removes the original task element."""
    task_id_tag = soup.find('ac:task-id', string=confluence_task_id)
    if not task_id_tag:
        logger.warning(f"    Task ID {confluence_task_id} not found in HTML for update. Skipping.")
        return False

    task_tag = task_id_tag.find_parent('ac:task')
    if not task_tag:
        logger.warning(f"    Parent <ac:task> tag not found for task ID {confluence_task_id}. Skipping.")
        return False

    # Check if this task is within an aggregate macro, do not modify if it is
    current_tag = task_tag.parent
    while current_tag:
        if (current_tag.name == 'ac:structured-macro' and
            current_tag.get('ac:name') in config.AGGREGATE_MACRO_NAMES):
            logger.info(f"    INFO: Not updating task ID {confluence_task_id} as it's part of an aggregate macro. ")
            return False
        current_tag = current_tag.parent

    task_list_tag = task_tag.find_parent('ac:task-list')
    if not task_list_tag:
        logger.warning(f"    <ac:task-list> parent not found for task ID {confluence_task_id}. Inserting after task tag.")

    logger.info(f"    -> Found task ID {confluence_task_id}. Inserting Jira macro and removing Confluence task.")
    jira_macro_xml = _generate_jira_macro_xml(new_jira_key)
    new_macro_element = BeautifulSoup(jira_macro_xml, 'html.parser').find('p')

    if task_list_tag:
        task_list_tag.insert_after(new_macro_element)
    else:
        task_tag.insert_after(new_macro_element) # Fallback if task-list isn't direct parent

    task_tag.decompose() # Remove the original Confluence task
    return True

def _clean_empty_task_lists(soup):
    """Removes any ac:task-list elements that no longer contain tasks."""
    for tl in soup.find_all('ac:task-list'):
        if not tl.find('ac:task'):
            tl.decompose()
            logger.debug(f"    Removed empty ac:task-list tag.")

def _update_confluence_page_content(page_id, page_title, new_content, parent_id):
    """Performs the actual Confluence page update API call."""
    try:
        update_response = confluence.update_page(
            page_id=page_id, title=page_title, body=new_content, parent_id=parent_id, minor_edit=True
        )
        if update_response:
            logger.info(f"  SUCCESS: Confluence API confirmed page {page_id} was updated.")
            return True
        else:
            logger.warning(f"  WARNING: Confluence API did not confirm the page update for {page_id}.")
            return False
    except Exception as e:
        logger.error(f"  ERROR: Failed to update Confluence page {page_id}. Details: {repr(e)}")
        return False

def update_confluence_page_with_jira_links(page_id, task_mappings):
    """
    Orchestrates the update of a Confluence page: fetches content, inserts Jira macros,
    removes original tasks, cleans up, and updates the page via API.
    """
    if not task_mappings:
        logger.info(f"  No task mappings to update for page {page_id}. Skipping page update.")
        return None

    logger.info(f"  Updating Confluence page {page_id} with {len(task_mappings)} Jira link(s)...")
    try:
        page = confluence.get_page_by_id(page_id, expand='body.storage,version,ancestors')
        original_page_title = page['title']
        original_page_content_string = page['body']['storage']['value']
        parent_id = page['ancestors'][-1]['id'] if page.get('ancestors') else None
        
        # Capture previous version details safely
        version_info = page.get('version', {}) # Use .get() to avoid KeyError
        previous_version_number = version_info.get('number', 0)
        previous_version_by = version_info.get('by', {}).get('displayName', 'Unknown')
        previous_version_when = version_info.get('when', 'N/A')

        soup = BeautifulSoup(original_page_content_string, 'html.parser')
        
        modified_count = 0
        for mapping in task_mappings:
            success = _insert_jira_macro_and_remove_task(soup, mapping['confluence_task_id'], mapping['jira_key'])
            if success:
                modified_count += 1

        if modified_count == 0:
            logger.info(f"  No valid tasks were modified on page {page_id}. Skipping page update.")
            return None

        _clean_empty_task_lists(soup)

        new_content = str(soup)
        
        if new_content.strip() == original_page_content_string.strip():
            logger.info(f"  Page {page_id} content effectively unchanged after macro insertion/removal. Skipping API update.")
            return None

        update_success = _update_confluence_page_content(page_id, original_page_title, new_content, parent_id)

        if update_success:
            return {
                'page_id': page_id,
                'original_version_number': previous_version_number,
                'original_version_by': previous_version_by,
                'original_version_when': previous_version_when
            }
        return None

    except Exception as e:
        logger.error(f"  ERROR: A critical exception occurred during the page update process for {page_id}. Details: {repr(e)}")
        return None


# --- Main Execution Function ---
def run_automation_script():
    """
    This function contains the main execution logic of the automation script.
    It's designed to be called when the script is run directly.
    """
    current_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    _setup_logging(current_timestamp)
    _initialize_api_clients()

    logger.info("--- Starting Jira/Confluence Automation Script ---")

    try:
        input_df = pd.read_excel('input.xlsx')
    except FileNotFoundError:
        logger.error("ERROR: 'input.xlsx' not found. Please create it and run again.")
        return
    except Exception as e:
        logger.error(f"ERROR: Failed to read 'input.xlsx'. Details: {repr(e)}")
        return

    output_excel_file = os.path.join('output', f'automation_results_{current_timestamp}.xlsx')

    all_results = []
    
    pages_updated_version_info = {} 

    if not input_df.empty:
        for index, row in input_df.iterrows():
            main_page_url = row['ConfluencePageURL']
            logger.info(f"\nProcessing Main Page and its descendants starting from: {main_page_url}")

            main_page_id = get_page_id_from_any_url(main_page_url, config.CONFLUENCE_API_TOKEN)
            if not main_page_id:
                all_results.append(
                    {"Confluence Page ID": None, "Confluence Page Title": None, "Status": "Skipped - Could not get Main Page ID",
                     "Original Task Summary": None, "New Jira Task Key": None, "Linked Work Package": None,
                     "Confluence Task ID (for undo)": None, # Ensure column exists
                     "Original Page Version": None, "Original Page Version By": None, "Original Page Version When": None}
                )
                continue

            main_page_wp = find_work_package_on_page_content(main_page_id)
            default_wp_assignee_name = None
            if main_page_wp:
                if main_page_wp['fields'].get('assignee'):
                    default_wp_assignee_name = main_page_wp['fields']['assignee']['name']
                    logger.info(f"  Main Page Work Package assignee: {default_wp_assignee_name} (will be fallback)")
                elif main_page_wp['fields'].get('reporter'):
                    default_wp_assignee_name = main_page_wp['fields']['reporter']['name']
                    logger.info(f"  Main Page Work Package reporter: {default_wp_assignee_name} (will be fallback)")
                else:
                    logger.warning("  WARNING: Main Work Package has no assignee or reporter. No fallback assignee set from main WP.")
            else:
                logger.info("  No Work Package found on the main input page. No default fallback assignee determined from main WP.")

            all_pages_to_scan_ids = [main_page_id] + get_all_child_pages_recursive(main_page_id)
            logger.info(f"  Found {len(all_pages_to_scan_ids)} total page(s) to scan for tasks.")

            all_found_tasks = []
            for current_page_id in all_pages_to_scan_ids:
                tasks_on_current_page = process_confluence_page_for_tasks(current_page_id, default_wp_assignee_name)
                all_found_tasks.extend(tasks_on_current_page)

            logger.info(f"\nDiscovered {len(all_found_tasks)} incomplete tasks across all scanned pages. Now processing each task...")

            tasks_by_page_for_update = {}
            
            for task_data in all_found_tasks:
                current_page_id = task_data['confluence_page_id']
                task_summary = task_data['task_summary']
                assignee_from_task = task_data['assignee_name']
                due_date = task_data['due_date']
                confluence_task_id = task_data['confluence_task_id']
                confluence_page_title = task_data['confluence_page_title']
                confluence_page_url = task_data['confluence_page_url']

                logger.info(f"\nProcessing task: '{task_summary}' from page ID: {current_page_id}")

                closest_wp_issue = get_closest_ancestor_work_package(current_page_id)

                if not closest_wp_issue:
                    logger.warning(f"  -> WARNING: No closest ancestor Work Package found for task: '{task_summary}'. Skipping Jira creation for this task.")
                    all_results.append({
                        "Confluence Page ID": current_page_id,
                        "Confluence Page Title": confluence_page_title,
                        "Status": "Skipped - No closest Work Package found",
                        "Original Task Summary": task_summary,
                        "Confluence Task ID (for undo)": confluence_task_id, # Log the Confluence Task ID
                        "New Jira Task Key": None,
                        "Linked Work Package": None,
                        "Original Page Version": task_data['original_page_version'],
                        "Original Page Version By": task_data['original_page_version_by'],
                        "Original Page Version When": task_data['original_page_version_when']
                    })
                    continue

                closest_wp_key = closest_wp_issue['key']
                closest_wp_assignee = closest_wp_issue['fields'].get('assignee', {}).get('name')
                closest_wp_reporter = closest_wp_issue['fields'].get('reporter', {}).get('name')

                final_assignee_name = assignee_from_task

                if not final_assignee_name:
                    if closest_wp_assignee:
                        final_assignee_name = closest_wp_assignee
                        logger.info(f"    Assigning task to closest WP assignee: {final_assignee_name}")
                    elif closest_wp_reporter:
                        final_assignee_name = closest_wp_reporter
                        logger.info(f"    Assigning task to closest WP reporter: {final_assignee_name}")
                    else:
                        logger.warning(f"    WARNING: No assignee found for task '{task_summary}' from task mention, main WP, or closest WP. Task will be unassigned in Jira.")

                new_jira_key = create_jira_task(task_data, closest_wp_key, final_assignee_name)

                if new_jira_key:
                    if current_page_id not in tasks_by_page_for_update:
                        tasks_by_page_for_update[current_page_id] = []
                    tasks_by_page_for_update[current_page_id].append({
                        'confluence_task_id': confluence_task_id, # Use the correctly extracted ID
                        'jira_key': new_jira_key
                    })
                    
                    if current_page_id not in pages_updated_version_info:
                        pages_updated_version_info[current_page_id] = {
                            "original_version_number": task_data['original_page_version'],
                            "original_version_by": task_data['original_page_version_by'],
                            "original_version_when": task_data['original_page_version_when']
                        }

                    all_results.append({
                        "Confluence Page ID": current_page_id,
                        "Confluence Page Title": confluence_page_title,
                        "Status": "Success",
                        "Original Task Summary": task_summary,
                        "Confluence Task ID (for undo)": confluence_task_id, # Log the Confluence Task ID
                        "New Jira Task Key": new_jira_key,
                        "Linked Work Package": closest_wp_key,
                        "Original Page Version": task_data['original_page_version'],
                        "Original Page Version By": task_data['original_page_version_by'],
                        "Original Page Version When": task_data['original_page_version_when']
                    })
                else:
                    all_results.append({
                        "Confluence Page ID": current_page_id,
                        "Confluence Page Title": confluence_page_title,
                        "Status": "Failed - Jira task creation",
                        "Original Task Summary": task_summary,
                        "Confluence Task ID (for undo)": confluence_task_id, # Log the Confluence Task ID even on failure
                        "New Jira Task Key": None,
                        "Linked Work Package": closest_wp_key,
                        "Original Page Version": task_data['original_page_version'],
                        "Original Page Version By": task_data['original_page_version_by'],
                        "Original Page Version When": task_data['original_page_version_when']
                    })

        logger.info("\nAll Jira tasks processed. Now updating Confluence pages...")
        for page_id_to_update, task_mappings_for_this_page in tasks_by_page_for_update.items():
            update_confluence_page_with_jira_links(page_id_to_update, task_mappings_for_this_page)


    if all_results:
        output_df = pd.DataFrame(all_results)
        output_df.to_excel(output_excel_file, index=False)
        logger.info("\n--- Script Finished ---")
        logger.info(f"Results have been saved to '{output_excel_file}'")
    else:
        logger.info("\n--- Script Finished ---")
        logger.info("No tasks were found or processed.")


# --- SCRIPT EXECUTION BLOCK ---
if __name__ == "__main__":
=======
# main.py - Standard standalone file format with __main__ block (Corrected KeyError and Uncommented Transition)

import pandas as pd
import re
import datetime
import uuid
import requests
import os
import logging
import sys

import config

from atlassian import Confluence, Jira
from atlassian.errors import ApiError
from bs4 import BeautifulSoup


# --- Suppress SSL Warnings ---
import warnings
import urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
# -----------------------------

# Global logger instance (will be configured in run_automation_script)
logger = logging.getLogger(__name__)

# Global API client instances (will be initialized in run_automation_script)
confluence = None
jira = None

# --- Helper Function for Logging Setup ---
def _setup_logging(timestamp):
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file_name = os.path.join(log_dir, f'automation_run_{timestamp}.log')

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

       # FileHandler with UTF-8 encoding
        file_handler = logging.FileHandler(log_file_name, encoding='utf-8') # <--- Added encoding='utf-8'
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging initialized. Output will be saved to '{log_file_name}'")

# --- Helper Function for API Client Initialization ---
def _initialize_api_clients():
    global confluence, jira
    logger.info("Initializing API clients for Server instances...")
    confluence = Confluence(
        url=config.CONFLUENCE_URL,
        token=config.CONFLUENCE_API_TOKEN,
        cloud=False,
        verify_ssl=False
    )
    jira = Jira(
        url=config.JIRA_URL,
        token=config.JIRA_API_TOKEN,
        cloud=False,
        verify_ssl=False
    )


# --- 2. HELPER AND LOGIC FUNCTIONS (Refactored) ---

def get_all_child_pages_recursive(start_page_id):
    """
    Recursively finds all descendant pages (children, grandchildren, etc.) of a given page.
    """
    all_child_ids = []
    try:
        children = confluence.get_page_child_by_type(start_page_id, type='page')
        for child in children:
            child_id = child['id']
            all_child_ids.append(child_id)
            all_child_ids.extend(get_all_child_pages_recursive(child_id))
    except ApiError as e:
        logger.error(f"  ERROR: Confluence API error getting children for page {start_page_id}. Details: {e}")
    except Exception as e:
        logger.error(f"  ERROR: Unexpected error getting children for page {start_page_id}. Details: {repr(e)}")
    return all_child_ids


def _extract_page_id_from_long_url(url):
    """Pure function to extract page ID from a standard Confluence long URL."""
    long_url_match = re.search(r'/pages/(\d+)', url)
    if long_url_match:
        return long_url_match.group(1)
    return None

def _resolve_short_url_to_long_url(short_url, token):
    """Performs an authenticated HEAD request to resolve a short Confluence URL."""
    logger.info(f"  Attempting to resolve short URL: {short_url}")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.head(
            short_url, headers=headers, allow_redirects=True, timeout=15, verify=False
        )
        response.raise_for_status()
        final_url = response.url
        logger.info(f"  Short URL resolved to: {final_url}")
        return final_url
    except requests.exceptions.RequestException as e:
        logger.error(f"  ERROR: Could not resolve the short URL '{short_url}'. Details: {e}")
        return None

def get_page_id_from_any_url(url, token):
    """Extracts the Confluence page ID from either a standard long URL or a short link."""
    page_id = _extract_page_id_from_long_url(url)
    if page_id:
        return page_id

    resolved_url = _resolve_short_url_to_long_url(url, token)
    if resolved_url:
        page_id = _extract_page_id_from_long_url(resolved_url)
        if page_id:
            return page_id
        else:
            logger.error(f"  ERROR: Resolved URL '{resolved_url}' did not contain a page ID.")
            return None
    return None

def _parse_jira_macros_from_html(html_content):
    """Extracts non-aggregate Jira macro elements from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    jira_macros = soup.find_all('ac:structured-macro', {'ac:name': 'jira'})

    clean_macros = []
    for macro in jira_macros:
        is_within_aggregate_macro = False
        for parent_macro_name in config.AGGREGATE_MACRO_NAMES:
            if (parent_macro_name != 'jira' and
                macro.find_parent('ac:structured-macro', {'ac:name': parent_macro_name})):
                is_within_aggregate_macro = True
                break
        if not is_within_aggregate_macro:
            clean_macros.append(macro)
    return clean_macros

def _get_jira_issue_details(issue_key):
    """Fetches specific Jira issue fields (issuetype, assignee, reporter)."""
    try:
        return jira.get_issue(issue_key, fields="issuetype,assignee,reporter")
    except ApiError as e:
        if e.response.status_code == 404:
            logger.warning(f"  WARNING: Jira issue '{issue_key}' not found or not accessible.")
        else:
            logger.error(f"  ERROR: Jira API error fetching issue '{issue_key}'. Details: {e}")
    except Exception as e:
        logger.error(f"  ERROR: Unexpected error fetching Jira issue '{issue_key}'. Details: {repr(e)}")
    return None

def _is_work_package(jira_issue_details):
    """Checks if a Jira issue dictionary represents a Work Package."""
    if jira_issue_details:
        issue_type_id = jira_issue_details.get('fields', {}).get('issuetype', {}).get('id')
        return issue_type_id == config.WORK_PACKAGE_ISSUE_TYPE_ID
    return False

def find_work_package_on_page_content(page_id):
    """
    Checks a Confluence page's *own content* for a linked Jira issue by parsing the page HTML.
    Returns the Jira issue object of the Work Package if found, otherwise None.
    """
    logger.info(f"  Searching for Work Package on page ID: {page_id}...")
    try:
        page_content_data = confluence.get_page_by_id(page_id, expand='body.storage')
        html_body = page_content_data['body']['storage']['value']

        jira_macros = _parse_jira_macros_from_html(html_body)

        if not jira_macros:
            logger.info(f"  INFO: No Jira macros (non-aggregate) found on page {page_id}.")
            return None

        for macro in jira_macros:
            key_param = macro.find('ac:parameter', {'ac:name': 'key'})
            if not key_param:
                continue
            issue_key = key_param.get_text()

            jira_issue = _get_jira_issue_details(issue_key)
            if _is_work_package(jira_issue):
                logger.info(f"  SUCCESS: Found Work Package '{issue_key}' on page {page_id}.")
                return jira_issue
    except Exception as e:
        logger.error(f"  ERROR: Failed to process page {page_id} for Work Package. Details: {repr(e)}")

    logger.info(f"  INFO: No Work Package found on page {page_id}.")
    return None


def _get_page_ancestors_info(page_id):
    """Gets the list of ancestor page IDs and titles, from furthest to closest."""
    ancestors = []
    try:
        page_info = confluence.get_page_by_id(page_id, expand='ancestors')
        if 'ancestors' in page_info and page_info['ancestors']:
            for ancestor in page_info['ancestors']:
                ancestors.append({'id': ancestor['id'], 'title': ancestor['title']})
        # Add the current page itself as the closest "ancestor" for WP check
        ancestors.append({'id': page_info['id'], 'title': page_info['title']})
    except ApiError as e:
        logger.error(f"  ERROR: Confluence API error getting ancestors for page {page_id}. Details: {e}")
    except Exception as e:
        logger.error(f"  ERROR: Unexpected error getting ancestors for page {page_id}. Details: {repr(e)}")
    return ancestors


def get_closest_ancestor_work_package(current_page_id):
    """
    Traverses up the Confluence page hierarchy to find the closest ancestor (including the current page)
    that contains a Work Package Jira issue.
    Returns the Jira issue object of the Work Package if found, otherwise None.
    """
    logger.info(f"  Searching for closest Work Package ancestor for page ID: {current_page_id}")
    ancestor_chain = _get_page_ancestors_info(current_page_id)

    for page_info in reversed(ancestor_chain):
        wp_issue = find_work_package_on_page_content(page_info['id'])
        if wp_issue:
            logger.info(f"  -> Found Work Package '{wp_issue['key']}' on closest relevant page: '{page_info['title']}' (ID: {page_info['id']})")
            return wp_issue

    logger.info(f"  -> No Work Package found on page {current_page_id} or any of its ancestors.")
    return None

def _get_confluence_page_details(page_id):
    """
    Fetches full page content, title, web URL, and version details.
    Handles potential missing 'version' key by providing defaults.
    """
    try:
        # Ensure 'version' is expanded
        page = confluence.get_page_by_id(page_id, expand='body.storage,links.webui,version')
        
        page_title = page['title']
        page_content = page['body']['storage']['value']
        links_dict = page.get('links', {})
        page_url = links_dict.get('webui', f"URL-Not-Found-For-Page-ID-{page_id}")

        # Safely get version details using .get() to avoid KeyError if 'version' or sub-keys are missing
        version_info = page.get('version', {})
        version_number = version_info.get('number', 0)
        version_by = version_info.get('by', {}).get('displayName', 'Unknown')
        version_when = version_info.get('when', 'N/A')

        return {
            'id': page_id,
            'title': page_title,
            'url': page_url,
            'content': page_content,
            'version_number': version_number,
            'version_by': version_by,
            'version_when': version_when
        }
    except ApiError as e:
        logger.error(f"  ERROR: Confluence API error fetching page {page_id} details. Details: {e}")
    except Exception as e:
        # Log the full page object if 'version' key is unexpectedly missing from the response
        logger.error(f"  ERROR: Unexpected error fetching page {page_id} details. Details: {repr(e)}")
        # Attempt to re-fetch with minimal expand to see the basic structure if version fails
        try:
            basic_page_info = confluence.get_page_by_id(page_id)
            logger.error(f"  Basic page info without version expand: {basic_page_info}")
        except Exception as inner_e:
            logger.error(f"  Failed to get basic page info too: {repr(inner_e)}")
    return None

def _extract_confluence_tasks_from_html(html_content):
    """Extracts ac:task elements, filtering out those within aggregate macros."""
    soup = BeautifulSoup(html_content, 'html.parser')
    confluence_tasks = soup.find_all('ac:task')
    clean_tasks = []
    for task_element in confluence_tasks:
        is_within_aggregate_macro = False
        current_tag = task_element.parent
        while current_tag:
            if (current_tag.name == 'ac:structured-macro' and
                current_tag.get('ac:name') in config.AGGREGATE_MACRO_NAMES):
                is_within_aggregate_macro = True
                logger.debug(f"    Skipping potential task within aggregate macro: {task_element.get_text().strip()}")
                break
            current_tag = current_tag.parent
        if not is_within_aggregate_macro:
            clean_tasks.append(task_element)
    return clean_tasks

def _get_assignee_from_confluence_userkey(user_key):
    """Looks up assignee username from Confluence userkey."""
    try:
        user_details = confluence.get_user_details_by_userkey(user_key)
        return user_details['username']
    except Exception as e:
        logger.warning(f"      WARNING: Could not look up user with key '{user_key}'. Details: {repr(e)}")
    return None

def _parse_single_confluence_task(task_html_element, page_info, default_wp_assignee_name):
    """
    Parses a single 'ac:task' BeautifulSoup element and returns extracted data.
    Returns None if the task is complete or invalid.
    """
    task_body_tag = task_html_element.find('ac:task-body')
    status_tag = task_html_element.find('ac:task-status')
    task_id_tag = task_html_element.find('ac:task-id')

    if not task_body_tag or not task_id_tag:
        logger.debug("    Skipping task element due to missing body or ID tag.")
        return None

    task_summary = task_body_tag.get_text().strip()
    task_status = status_tag.get_text() if status_tag else 'incomplete'
    confluence_task_id = task_id_tag.get_text()

    if task_status != 'incomplete':
        logger.info(f"    - Task '{task_summary}' (ID: {confluence_task_id}) is COMPLETE. Skipping.")
        return None

    task_assignee_name = None
    user_mention_tag = task_html_element.find('ri:user')
    if user_mention_tag and user_mention_tag.has_attr('ri:userkey'):
        user_key_from_confluence = user_mention_tag['ri:userkey']
        task_assignee_name = _get_assignee_from_confluence_userkey(user_key_from_confluence)

    assignee_to_use = task_assignee_name if task_assignee_name else default_wp_assignee_name

    date_tag = task_html_element.find('time')
    due_date_to_use = date_tag['datetime'] if date_tag and date_tag.has_attr('datetime') else config.DEFAULT_DUE_DATE

    logger.info(
        f"    - Found INCOMPLETE Task | ID: {confluence_task_id} | Due: {due_date_to_use} | Assignee: {assignee_to_use or '(none)'} | Summary: '{task_summary}'"
    )

    return {
        'confluence_page_id': page_info['id'],
        'confluence_page_title': page_info['title'],
        'confluence_page_url': page_info['url'],
        'confluence_task_id': confluence_task_id, # Log the explicit Confluence Task ID
        'task_summary': task_summary,
        'assignee_name': assignee_to_use,
        'due_date': due_date_to_use,
        'original_page_version': page_info['version_number'], # ADDED: Original page version
        'original_page_version_by': page_info['version_by'], # ADDED: Original version author
        'original_page_version_when': page_info['version_when'] # ADDED: Original version timestamp
    }


def process_confluence_page_for_tasks(page_id, default_wp_assignee_name):
    """
    Reads a Confluence page, finds incomplete tasks (excluding aggregate macros),
    and returns their parsed data. This function does NOT create Jira tasks.
    """
    page_tasks_data = []
    page_info = _get_confluence_page_details(page_id)
    if not page_info:
        return []

    logger.info(f"  Scanning page '{page_info['title']}' (ID: {page_info['id']}) for tasks...")

    clean_tasks = _extract_confluence_tasks_from_html(page_info['content'])

    if not clean_tasks:
        logger.info(f"  No valid tasks found on page '{page_info['title']}' (ID: {page_info['id']}).")
        return []

    for task_element in clean_tasks:
        parsed_task = _parse_single_confluence_task(task_element, page_info, default_wp_assignee_name)
        if parsed_task:
            page_tasks_data.append(parsed_task)

    return page_tasks_data


def _prepare_jira_task_fields(task_data, parent_key, assignee_name):
    """Prepares the fields dictionary for Jira issue creation."""
    description_string = (
        f"This task was automatically generated from a Confluence checklist.\n\n"
        f"*Original Task:*\n{task_data['task_summary']}\n\n"
        f"*Source Page:*\n[{task_data['confluence_page_title']}|{task_data['confluence_page_url']}]"
    )
    issue_fields = {
        "project": {"key": config.JIRA_PROJECT_KEY},
        "summary": task_data['task_summary'],
        "issuetype": {"id": config.TASK_ISSUE_TYPE_ID},
        "description": description_string,
        "duedate": task_data['due_date'],
        config.JIRA_PARENT_WP_CUSTOM_FIELD_ID: parent_key,
    }
    if assignee_name:
        issue_fields["assignee"] = {"name": assignee_name}
    return issue_fields

def _perform_jira_issue_creation(issue_fields):
    """Performs the actual Jira issue creation API call."""
    try:
        new_issue = jira.issue_create(fields=issue_fields)
        return new_issue['key']
    except Exception as e:
        logger.error(
            f"    -> ERROR: Failed to create Jira task for summary '{issue_fields.get('summary', 'N/A')}'."
            f" Details: {repr(e)}"
        )
    return None

def _perform_jira_transition_direct(issue_key, target_status_name, jira_url, jira_api_token):
    """
    Attempts to transition a Jira issue to a target status using direct requests.
    """
    # Uncommented as per request.
    if not target_status_name or target_status_name.lower() != 'backlog':
        logger.warning(
            f"    -> WARNING: Transition to '{target_status_name}' is not supported via hardcoded ID for {issue_key}."
            " Manual transition may be needed."
        )
        return

    transition_id = 11 # Hardcoded for 'Backlog'

    transition_url = f"{jira_url}/rest/api/2/issue/{issue_key}/transitions"
    headers = {
        "Authorization": f"Bearer {jira_api_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "transition": {
            "id": str(transition_id) # ID must be a string in the payload
        }
    }

    try:
        response = requests.post(transition_url, headers=headers, json=payload, verify=False)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        logger.info(f"    -> Successfully transitioned Jira issue {issue_key} to '{target_status_name}' (ID: {transition_id}).")
    except requests.exceptions.HTTPError as e:
        logger.warning(
            f"    -> WARNING: HTTPError during transition for {issue_key} to '{target_status_name}'. Status:"
            f" {e.response.status_code}, Response: {e.response.text}. Details: {e}"
        )
    except requests.exceptions.RequestException as e:
        logger.warning(
            f"    -> WARNING: Request error during transition for {issue_key} to '{target_status_name}'. Details: {e}"
        )
    except Exception as e:
        logger.warning(
            f"    -> WARNING: Unexpected error during transition for {issue_key} to '{target_status_name}'. Details: {repr(e)}"
        )


def create_jira_task(task_data, parent_key, final_assignee_name):
    """
    Orchestrates the creation of a Jira task, preparing fields, creating the issue,
    and attempting a transition.
    """
    logger.info(f"      -> Status is INCOMPLETE. Creating Jira task for '{task_data['task_summary']}'...")
    issue_fields = _prepare_jira_task_fields(task_data, parent_key, final_assignee_name)
    new_jira_key = _perform_jira_issue_creation(issue_fields)

    if new_jira_key:
        _perform_jira_transition_direct(new_jira_key, config.JIRA_TARGET_STATUS_NAME, config.JIRA_URL, config.JIRA_API_TOKEN)

    return new_jira_key


def _generate_jira_macro_xml(jira_key):
    """Generates the Confluence storage format XML for a Jira macro."""
    return (
        f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1"'
        f' ac:macro-id="{str(uuid.uuid4())}"><ac:parameter'
        f' ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter><ac:parameter'
        f' ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter><ac:parameter'
        f' ac:name="key">{jira_key}</ac:parameter></ac:structured-macro></p>'
    )

def _insert_jira_macro_and_remove_task(soup, confluence_task_id, new_jira_key):
    """Inserts a Jira macro into the BeautifulSoup tree and removes the original task element."""
    task_id_tag = soup.find('ac:task-id', string=confluence_task_id)
    if not task_id_tag:
        logger.warning(f"    Task ID {confluence_task_id} not found in HTML for update. Skipping.")
        return False

    task_tag = task_id_tag.find_parent('ac:task')
    if not task_tag:
        logger.warning(f"    Parent <ac:task> tag not found for task ID {confluence_task_id}. Skipping.")
        return False

    # Check if this task is within an aggregate macro, do not modify if it is
    current_tag = task_tag.parent
    while current_tag:
        if (current_tag.name == 'ac:structured-macro' and
            current_tag.get('ac:name') in config.AGGREGATE_MACRO_NAMES):
            logger.info(f"    INFO: Not updating task ID {confluence_task_id} as it's part of an aggregate macro. ")
            return False
        current_tag = current_tag.parent

    task_list_tag = task_tag.find_parent('ac:task-list')
    if not task_list_tag:
        logger.warning(f"    <ac:task-list> parent not found for task ID {confluence_task_id}. Inserting after task tag.")

    logger.info(f"    -> Found task ID {confluence_task_id}. Inserting Jira macro and removing Confluence task.")
    jira_macro_xml = _generate_jira_macro_xml(new_jira_key)
    new_macro_element = BeautifulSoup(jira_macro_xml, 'html.parser').find('p')

    if task_list_tag:
        task_list_tag.insert_after(new_macro_element)
    else:
        task_tag.insert_after(new_macro_element) # Fallback if task-list isn't direct parent

    task_tag.decompose() # Remove the original Confluence task
    return True

def _clean_empty_task_lists(soup):
    """Removes any ac:task-list elements that no longer contain tasks."""
    for tl in soup.find_all('ac:task-list'):
        if not tl.find('ac:task'):
            tl.decompose()
            logger.debug(f"    Removed empty ac:task-list tag.")

def _update_confluence_page_content(page_id, page_title, new_content, parent_id):
    """Performs the actual Confluence page update API call."""
    try:
        update_response = confluence.update_page(
            page_id=page_id, title=page_title, body=new_content, parent_id=parent_id, minor_edit=True
        )
        if update_response:
            logger.info(f"  SUCCESS: Confluence API confirmed page {page_id} was updated.")
            return True
        else:
            logger.warning(f"  WARNING: Confluence API did not confirm the page update for {page_id}.")
            return False
    except Exception as e:
        logger.error(f"  ERROR: Failed to update Confluence page {page_id}. Details: {repr(e)}")
        return False

def update_confluence_page_with_jira_links(page_id, task_mappings):
    """
    Orchestrates the update of a Confluence page: fetches content, inserts Jira macros,
    removes original tasks, cleans up, and updates the page via API.
    """
    if not task_mappings:
        logger.info(f"  No task mappings to update for page {page_id}. Skipping page update.")
        return None

    logger.info(f"  Updating Confluence page {page_id} with {len(task_mappings)} Jira link(s)...")
    try:
        page = confluence.get_page_by_id(page_id, expand='body.storage,version,ancestors')
        original_page_title = page['title']
        original_page_content_string = page['body']['storage']['value']
        parent_id = page['ancestors'][-1]['id'] if page.get('ancestors') else None
        
        # Capture previous version details safely
        version_info = page.get('version', {}) # Use .get() to avoid KeyError
        previous_version_number = version_info.get('number', 0)
        previous_version_by = version_info.get('by', {}).get('displayName', 'Unknown')
        previous_version_when = version_info.get('when', 'N/A')

        soup = BeautifulSoup(original_page_content_string, 'html.parser')
        
        modified_count = 0
        for mapping in task_mappings:
            success = _insert_jira_macro_and_remove_task(soup, mapping['confluence_task_id'], mapping['jira_key'])
            if success:
                modified_count += 1

        if modified_count == 0:
            logger.info(f"  No valid tasks were modified on page {page_id}. Skipping page update.")
            return None

        _clean_empty_task_lists(soup)

        new_content = str(soup)
        
        if new_content.strip() == original_page_content_string.strip():
            logger.info(f"  Page {page_id} content effectively unchanged after macro insertion/removal. Skipping API update.")
            return None

        update_success = _update_confluence_page_content(page_id, original_page_title, new_content, parent_id)

        if update_success:
            return {
                'page_id': page_id,
                'original_version_number': previous_version_number,
                'original_version_by': previous_version_by,
                'original_version_when': previous_version_when
            }
        return None

    except Exception as e:
        logger.error(f"  ERROR: A critical exception occurred during the page update process for {page_id}. Details: {repr(e)}")
        return None


# --- Main Execution Function ---
def run_automation_script():
    """
    This function contains the main execution logic of the automation script.
    It's designed to be called when the script is run directly.
    """
    current_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    _setup_logging(current_timestamp)
    _initialize_api_clients()

    logger.info("--- Starting Jira/Confluence Automation Script ---")

    try:
        input_df = pd.read_excel('input.xlsx')
    except FileNotFoundError:
        logger.error("ERROR: 'input.xlsx' not found. Please create it and run again.")
        return
    except Exception as e:
        logger.error(f"ERROR: Failed to read 'input.xlsx'. Details: {repr(e)}")
        return

    output_excel_file = os.path.join('output', f'automation_results_{current_timestamp}.xlsx')

    all_results = []
    
    pages_updated_version_info = {} 

    if not input_df.empty:
        for index, row in input_df.iterrows():
            main_page_url = row['ConfluencePageURL']
            logger.info(f"\nProcessing Main Page and its descendants starting from: {main_page_url}")

            main_page_id = get_page_id_from_any_url(main_page_url, config.CONFLUENCE_API_TOKEN)
            if not main_page_id:
                all_results.append(
                    {"Confluence Page ID": None, "Confluence Page Title": None, "Status": "Skipped - Could not get Main Page ID",
                     "Original Task Summary": None, "New Jira Task Key": None, "Linked Work Package": None,
                     "Confluence Task ID (for undo)": None, # Ensure column exists
                     "Original Page Version": None, "Original Page Version By": None, "Original Page Version When": None}
                )
                continue

            main_page_wp = find_work_package_on_page_content(main_page_id)
            default_wp_assignee_name = None
            if main_page_wp:
                if main_page_wp['fields'].get('assignee'):
                    default_wp_assignee_name = main_page_wp['fields']['assignee']['name']
                    logger.info(f"  Main Page Work Package assignee: {default_wp_assignee_name} (will be fallback)")
                elif main_page_wp['fields'].get('reporter'):
                    default_wp_assignee_name = main_page_wp['fields']['reporter']['name']
                    logger.info(f"  Main Page Work Package reporter: {default_wp_assignee_name} (will be fallback)")
                else:
                    logger.warning("  WARNING: Main Work Package has no assignee or reporter. No fallback assignee set from main WP.")
            else:
                logger.info("  No Work Package found on the main input page. No default fallback assignee determined from main WP.")

            all_pages_to_scan_ids = [main_page_id] + get_all_child_pages_recursive(main_page_id)
            logger.info(f"  Found {len(all_pages_to_scan_ids)} total page(s) to scan for tasks.")

            all_found_tasks = []
            for current_page_id in all_pages_to_scan_ids:
                tasks_on_current_page = process_confluence_page_for_tasks(current_page_id, default_wp_assignee_name)
                all_found_tasks.extend(tasks_on_current_page)

            logger.info(f"\nDiscovered {len(all_found_tasks)} incomplete tasks across all scanned pages. Now processing each task...")

            tasks_by_page_for_update = {}
            
            for task_data in all_found_tasks:
                current_page_id = task_data['confluence_page_id']
                task_summary = task_data['task_summary']
                assignee_from_task = task_data['assignee_name']
                due_date = task_data['due_date']
                confluence_task_id = task_data['confluence_task_id']
                confluence_page_title = task_data['confluence_page_title']
                confluence_page_url = task_data['confluence_page_url']

                logger.info(f"\nProcessing task: '{task_summary}' from page ID: {current_page_id}")

                closest_wp_issue = get_closest_ancestor_work_package(current_page_id)

                if not closest_wp_issue:
                    logger.warning(f"  -> WARNING: No closest ancestor Work Package found for task: '{task_summary}'. Skipping Jira creation for this task.")
                    all_results.append({
                        "Confluence Page ID": current_page_id,
                        "Confluence Page Title": confluence_page_title,
                        "Status": "Skipped - No closest Work Package found",
                        "Original Task Summary": task_summary,
                        "Confluence Task ID (for undo)": confluence_task_id, # Log the Confluence Task ID
                        "New Jira Task Key": None,
                        "Linked Work Package": None,
                        "Original Page Version": task_data['original_page_version'],
                        "Original Page Version By": task_data['original_page_version_by'],
                        "Original Page Version When": task_data['original_page_version_when']
                    })
                    continue

                closest_wp_key = closest_wp_issue['key']
                closest_wp_assignee = closest_wp_issue['fields'].get('assignee', {}).get('name')
                closest_wp_reporter = closest_wp_issue['fields'].get('reporter', {}).get('name')

                final_assignee_name = assignee_from_task

                if not final_assignee_name:
                    if closest_wp_assignee:
                        final_assignee_name = closest_wp_assignee
                        logger.info(f"    Assigning task to closest WP assignee: {final_assignee_name}")
                    elif closest_wp_reporter:
                        final_assignee_name = closest_wp_reporter
                        logger.info(f"    Assigning task to closest WP reporter: {final_assignee_name}")
                    else:
                        logger.warning(f"    WARNING: No assignee found for task '{task_summary}' from task mention, main WP, or closest WP. Task will be unassigned in Jira.")

                new_jira_key = create_jira_task(task_data, closest_wp_key, final_assignee_name)

                if new_jira_key:
                    if current_page_id not in tasks_by_page_for_update:
                        tasks_by_page_for_update[current_page_id] = []
                    tasks_by_page_for_update[current_page_id].append({
                        'confluence_task_id': confluence_task_id, # Use the correctly extracted ID
                        'jira_key': new_jira_key
                    })
                    
                    if current_page_id not in pages_updated_version_info:
                        pages_updated_version_info[current_page_id] = {
                            "original_version_number": task_data['original_page_version'],
                            "original_version_by": task_data['original_page_version_by'],
                            "original_version_when": task_data['original_page_version_when']
                        }

                    all_results.append({
                        "Confluence Page ID": current_page_id,
                        "Confluence Page Title": confluence_page_title,
                        "Status": "Success",
                        "Original Task Summary": task_summary,
                        "Confluence Task ID (for undo)": confluence_task_id, # Log the Confluence Task ID
                        "New Jira Task Key": new_jira_key,
                        "Linked Work Package": closest_wp_key,
                        "Original Page Version": task_data['original_page_version'],
                        "Original Page Version By": task_data['original_page_version_by'],
                        "Original Page Version When": task_data['original_page_version_when']
                    })
                else:
                    all_results.append({
                        "Confluence Page ID": current_page_id,
                        "Confluence Page Title": confluence_page_title,
                        "Status": "Failed - Jira task creation",
                        "Original Task Summary": task_summary,
                        "Confluence Task ID (for undo)": confluence_task_id, # Log the Confluence Task ID even on failure
                        "New Jira Task Key": None,
                        "Linked Work Package": closest_wp_key,
                        "Original Page Version": task_data['original_page_version'],
                        "Original Page Version By": task_data['original_page_version_by'],
                        "Original Page Version When": task_data['original_page_version_when']
                    })

        logger.info("\nAll Jira tasks processed. Now updating Confluence pages...")
        for page_id_to_update, task_mappings_for_this_page in tasks_by_page_for_update.items():
            update_confluence_page_with_jira_links(page_id_to_update, task_mappings_for_this_page)


    if all_results:
        output_df = pd.DataFrame(all_results)
        output_df.to_excel(output_excel_file, index=False)
        logger.info("\n--- Script Finished ---")
        logger.info(f"Results have been saved to '{output_excel_file}'")
    else:
        logger.info("\n--- Script Finished ---")
        logger.info("No tasks were found or processed.")


# --- SCRIPT EXECUTION BLOCK ---
if __name__ == "__main__":
>>>>>>> 71bb2c8db17e8064fbb838a4b18220e793cc0372
    run_automation_script()