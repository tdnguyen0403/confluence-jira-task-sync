<<<<<<< HEAD
# undo_automation.py - Script to undo the changes made by main.py
# Reads the latest results file and uses direct requests for Jira transitions.
# Corrected for API compatibility issues (get_all_transitions and version_message).

import pandas as pd
import logging
import sys
import os
import datetime
import requests # Required for direct API calls in transitions
import json # Required for parsing JSON response from requests

import config  # Your configuration file
from atlassian import Confluence, Jira
from atlassian.errors import ApiError

# --- Suppress SSL Warnings ---
import warnings
import urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
# -----------------------------

# --- Logging Setup ---
log_dir = 'logs_undo'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') # Use datetime.datetime
log_file_name = os.path.join(log_dir, f'undo_run_{timestamp}.log')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(log_file_name, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

logger.info(f"Undo Script Logging initialized. Output will be saved to '{log_file_name}'")
# --- End Logging Setup ---


# --- API Client Initialization ---
logger.info("Initializing API clients for Confluence and Jira...")
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


# --- Helper Functions for Undo Operations ---

def _perform_jira_transition_direct(jira_key, target_status_name, jira_url, jira_api_token):
    """
    Transitions a Jira task to a target status using direct requests API call.
    Dynamically finds the transition ID using the Jira REST API.
    """
    logger.info(f"  Attempting to transition Jira task '{jira_key}' to '{target_status_name}' via direct request...")

    headers = {
        "Authorization": f"Bearer {jira_api_token}",
        "Content-Type": "application/json"
    }

    try:
        # Step 1: Get current status and available transitions
        transitions_api_url = f"{jira_url}/rest/api/2/issue/{jira_key}/transitions"
        transitions_response = requests.get(transitions_api_url, headers=headers, verify=False)
        transitions_response.raise_for_status() # Raise HTTPError for bad responses

        transitions_data = json.loads(transitions_response.text) # Parse JSON response
        
        target_transition_id = None
        for t in transitions_data.get('transitions', []):
            if t['name'].lower() == target_status_name.lower():
                target_transition_id = t['id']
                break
        
        if not target_transition_id:
            current_status_response = jira.get_issue(jira_key, fields="status")
            current_status = current_status_response['fields']['status']['name']
            if current_status.lower() == target_status_name.lower():
                logger.info(f"    -> Jira task '{jira_key}' is already in '{target_status_name}'. Skipping transition.")
                return True
            else:
                logger.warning(f"    -> WARNING: Could not find transition to '{target_status_name}' for Jira task '{jira_key}'. Current status: '{current_status}'. Manual intervention may be needed.")
                return False

        # Step 2: Perform the transition
        payload = {"transition": {"id": str(target_transition_id)}}
        response = requests.post(transitions_api_url, headers=headers, json=payload, verify=False)
        response.raise_for_status()
        
        logger.info(f"    -> Successfully transitioned Jira issue '{jira_key}' to '{target_status_name}' (Transition ID: {target_transition_id}).")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"    -> ERROR: HTTPError during direct transition for '{jira_key}' to '{target_status_name}'. Status:"
            f" {e.response.status_code}, Response: {e.response.text}. Details: {e}"
        )
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"    -> ERROR: Request error during direct transition for '{jira_key}'. Details: {e}")
        return False
    except Exception as e:
        logger.error(f"    -> ERROR: Unexpected error during direct transition for '{jira_key}'. Details: {repr(e)}")
        return False


def _rollback_confluence_page_version(page_id, target_version_number):
    """Rolls back a Confluence page to a specific version number."""
    logger.info(f"  Attempting to roll back Confluence page '{page_id}' to version {target_version_number}...")
    try:
        # Get the content of the target version
        version_content_response = confluence.get_page_by_id(page_id, version=target_version_number, expand='body.storage,ancestors')
        if not version_content_response or 'body' not in version_content_response or 'storage' not in version_content_response['body']:
            logger.error(f"    -> ERROR: Could not retrieve content for page {page_id} version {target_version_number}. Skipping rollback.")
            return False

        current_page_details = confluence.get_page_by_id(page_id, expand='ancestors') # Get current title and parent
        current_page_title = current_page_details['title']
        parent_id = current_page_details['ancestors'][-1]['id'] if current_page_details.get('ancestors') else None

        # Update the page with the old content
        update_response = confluence.update_page(
            page_id=page_id,
            title=current_page_title, # Keep current title
            body=version_content_response['body']['storage']['value'], # Use old content
            parent_id=parent_id,
            minor_edit=False, # Make it a major edit to clearly mark rollback
            # Removed 'version_message' as it caused TypeError in some API versions
            # version_message=f"Rolled back to version {target_version_number} by automation undo script."
        )

        if update_response:
            logger.info(f"    -> Successfully rolled back Confluence page '{page_id}' to version {target_version_number}.")
            return True
        else:
            logger.warning(f"    -> WARNING: Confluence API did not confirm rollback for page '{page_id}'.")
            return False
    except ApiError as e:
        logger.error(f"    -> ERROR: Confluence API error rolling back page '{page_id}' to version {target_version_number}. Details: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            logger.error(f"API Error Response Body for Confluence rollback: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"    -> ERROR: Unexpected error rolling back Confluence page '{page_id}'. Details: {repr(e)}")
        return False

def find_latest_results_file(output_folder):
    """
    Finds the latest automation results Excel file in the specified folder
    based on the timestamp in its filename (automation_results_YYYYMMDD_HHMMSS.xlsx).
    """
    latest_file = None
    latest_timestamp = None
    
    logger.info(f"Searching for latest results file in '{output_folder}'...")

    if not os.path.exists(output_folder):
        logger.error(f"ERROR: Output folder '{output_folder}' does not exist.")
        return None

    files = os.listdir(output_folder)
    for filename in files:
        if filename.startswith('automation_results_') and filename.endswith('.xlsx'):
            # Extract timestamp: automation_results_YYYYMMDD_HHMMSS.xlsx
            try:
                timestamp_str = filename[len('automation_results_'):-len('.xlsx')]
                file_timestamp = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                
                if latest_timestamp is None or file_timestamp > latest_timestamp:
                    latest_timestamp = file_timestamp
                    latest_file = filename
            except ValueError:
                logger.warning(f"  WARNING: Could not parse timestamp from filename: {filename}. Skipping.")
                continue
    
    if latest_file:
        full_path = os.path.join(output_folder, latest_file)
        logger.info(f"Found latest results file: '{full_path}' (Timestamp: {latest_timestamp})")
        return full_path
    else:
        logger.warning(f"No automation results files found in '{output_folder}'.")
        return None


# --- Main Undo Execution Logic ---

def run_undo_automation(results_file_path_override=None):
    """
    Executes the undo operations based on a previous automation run's results file.
    If results_file_path_override is provided, uses that. Otherwise, finds the latest.
    """
    logger.info(f"\n--- Starting Undo Automation Script ---")

    if results_file_path_override:
        results_file_path = results_file_path_override
        logger.info(f"Using provided results file: '{results_file_path}'")
    else:
        results_file_path = find_latest_results_file('output')
        if not results_file_path:
            logger.error("ERROR: No results file found to undo. Aborting.")
            return

    try:
        results_df = pd.read_excel(results_file_path)
    except Exception as e:
        logger.error(f"ERROR: Failed to read results file '{results_file_path}'. Details: {repr(e)}")
        return

    jira_keys_to_transition = set()
    pages_to_rollback = {} # {page_id: target_version_number}

    for index, row in results_df.iterrows():
        page_id = str(row['Confluence Page ID'])
        jira_key = row['New Jira Task Key']
        status = row['Status']
        original_version = row.get('Original Page Version')

        # Collect Jira keys from successful task creations
        if pd.notna(jira_key) and status == "Success":
            jira_keys_to_transition.add(jira_key)
        
        # Collect page IDs and their original versions if they were successfully updated
        if pd.notna(page_id) and pd.notna(original_version) and status == "Success":
            # Only record the rollback version for a page once (the version it had BEFORE any script modification)
            if page_id not in pages_to_rollback:
                pages_to_rollback[page_id] = original_version


    # --- Phase 1: Transition Jira Tasks ---
    logger.info(f"\n--- Phase 1: Transitioning Jira Tasks to '{config.JIRA_TARGET_STATUS_NAME}' ---")
    if not jira_keys_to_transition:
        logger.info("  No Jira tasks found for transition.")
    for jira_key in sorted(list(jira_keys_to_transition)): # Sort for consistent logging order
        _perform_jira_transition_direct(jira_key, config.JIRA_TARGET_STATUS_NAME, config.JIRA_URL, config.JIRA_API_TOKEN)


    # --- Phase 2: Rollback Confluence Pages ---
    logger.info("\n--- Phase 2: Rolling back Confluence Pages to Previous Versions ---")
    logger.warning("NOTE: This operation reverts the page to a previous version. Any legitimate changes made to the page by other users *after* the automation script ran will also be undone by this rollback.")

    if not pages_to_rollback:
        logger.info("  No Confluence pages found for rollback.")
    for page_id, original_version in sorted(pages_to_rollback.items()): # Sort for consistent logging order
        _rollback_confluence_page_version(page_id, original_version)


    logger.info("\n--- Undo Automation Script Finished ---")
    logger.info("Review the log file and Confluence/Jira to confirm changes.")


# --- Script Execution Block ---
if __name__ == "__main__":
    # You can either provide a specific file path, or let it find the latest.
    # Set to None to automatically find the latest file.
    # Set to a string like "output/automation_results_20250620_164758.xlsx" to use a specific file.
    SPECIFIC_RESULTS_FILE_TO_UNDO = None # <--- **CHANGE THIS or leave as None**

    if SPECIFIC_RESULTS_FILE_TO_UNDO:
        run_undo_automation(SPECIFIC_RESULTS_FILE_TO_UNDO)
    else:
=======
# undo_automation.py - Script to undo the changes made by main.py
# Reads the latest results file and uses direct requests for Jira transitions.
# Corrected for API compatibility issues (get_all_transitions and version_message).

import pandas as pd
import logging
import sys
import os
import datetime
import requests # Required for direct API calls in transitions
import json # Required for parsing JSON response from requests

import config  # Your configuration file
from atlassian import Confluence, Jira
from atlassian.errors import ApiError

# --- Suppress SSL Warnings ---
import warnings
import urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
# -----------------------------

# --- Logging Setup ---
log_dir = 'logs_undo'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') # Use datetime.datetime
log_file_name = os.path.join(log_dir, f'undo_run_{timestamp}.log')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(log_file_name, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

logger.info(f"Undo Script Logging initialized. Output will be saved to '{log_file_name}'")
# --- End Logging Setup ---


# --- API Client Initialization ---
logger.info("Initializing API clients for Confluence and Jira...")
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


# --- Helper Functions for Undo Operations ---

def _perform_jira_transition_direct(jira_key, target_status_name, jira_url, jira_api_token):
    """
    Transitions a Jira task to a target status using direct requests API call.
    Dynamically finds the transition ID using the Jira REST API.
    """
    logger.info(f"  Attempting to transition Jira task '{jira_key}' to '{target_status_name}' via direct request...")

    headers = {
        "Authorization": f"Bearer {jira_api_token}",
        "Content-Type": "application/json"
    }

    try:
        # Step 1: Get current status and available transitions
        transitions_api_url = f"{jira_url}/rest/api/2/issue/{jira_key}/transitions"
        transitions_response = requests.get(transitions_api_url, headers=headers, verify=False)
        transitions_response.raise_for_status() # Raise HTTPError for bad responses

        transitions_data = json.loads(transitions_response.text) # Parse JSON response
        
        target_transition_id = None
        for t in transitions_data.get('transitions', []):
            if t['name'].lower() == target_status_name.lower():
                target_transition_id = t['id']
                break
        
        if not target_transition_id:
            current_status_response = jira.get_issue(jira_key, fields="status")
            current_status = current_status_response['fields']['status']['name']
            if current_status.lower() == target_status_name.lower():
                logger.info(f"    -> Jira task '{jira_key}' is already in '{target_status_name}'. Skipping transition.")
                return True
            else:
                logger.warning(f"    -> WARNING: Could not find transition to '{target_status_name}' for Jira task '{jira_key}'. Current status: '{current_status}'. Manual intervention may be needed.")
                return False

        # Step 2: Perform the transition
        payload = {"transition": {"id": str(target_transition_id)}}
        response = requests.post(transitions_api_url, headers=headers, json=payload, verify=False)
        response.raise_for_status()
        
        logger.info(f"    -> Successfully transitioned Jira issue '{jira_key}' to '{target_status_name}' (Transition ID: {target_transition_id}).")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"    -> ERROR: HTTPError during direct transition for '{jira_key}' to '{target_status_name}'. Status:"
            f" {e.response.status_code}, Response: {e.response.text}. Details: {e}"
        )
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"    -> ERROR: Request error during direct transition for '{jira_key}'. Details: {e}")
        return False
    except Exception as e:
        logger.error(f"    -> ERROR: Unexpected error during direct transition for '{jira_key}'. Details: {repr(e)}")
        return False


def _rollback_confluence_page_version(page_id, target_version_number):
    """Rolls back a Confluence page to a specific version number."""
    logger.info(f"  Attempting to roll back Confluence page '{page_id}' to version {target_version_number}...")
    try:
        # Get the content of the target version
        version_content_response = confluence.get_page_by_id(page_id, version=target_version_number, expand='body.storage,ancestors')
        if not version_content_response or 'body' not in version_content_response or 'storage' not in version_content_response['body']:
            logger.error(f"    -> ERROR: Could not retrieve content for page {page_id} version {target_version_number}. Skipping rollback.")
            return False

        current_page_details = confluence.get_page_by_id(page_id, expand='ancestors') # Get current title and parent
        current_page_title = current_page_details['title']
        parent_id = current_page_details['ancestors'][-1]['id'] if current_page_details.get('ancestors') else None

        # Update the page with the old content
        update_response = confluence.update_page(
            page_id=page_id,
            title=current_page_title, # Keep current title
            body=version_content_response['body']['storage']['value'], # Use old content
            parent_id=parent_id,
            minor_edit=False, # Make it a major edit to clearly mark rollback
            # Removed 'version_message' as it caused TypeError in some API versions
            # version_message=f"Rolled back to version {target_version_number} by automation undo script."
        )

        if update_response:
            logger.info(f"    -> Successfully rolled back Confluence page '{page_id}' to version {target_version_number}.")
            return True
        else:
            logger.warning(f"    -> WARNING: Confluence API did not confirm rollback for page '{page_id}'.")
            return False
    except ApiError as e:
        logger.error(f"    -> ERROR: Confluence API error rolling back page '{page_id}' to version {target_version_number}. Details: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            logger.error(f"API Error Response Body for Confluence rollback: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"    -> ERROR: Unexpected error rolling back Confluence page '{page_id}'. Details: {repr(e)}")
        return False

def find_latest_results_file(output_folder):
    """
    Finds the latest automation results Excel file in the specified folder
    based on the timestamp in its filename (automation_results_YYYYMMDD_HHMMSS.xlsx).
    """
    latest_file = None
    latest_timestamp = None
    
    logger.info(f"Searching for latest results file in '{output_folder}'...")

    if not os.path.exists(output_folder):
        logger.error(f"ERROR: Output folder '{output_folder}' does not exist.")
        return None

    files = os.listdir(output_folder)
    for filename in files:
        if filename.startswith('automation_results_') and filename.endswith('.xlsx'):
            # Extract timestamp: automation_results_YYYYMMDD_HHMMSS.xlsx
            try:
                timestamp_str = filename[len('automation_results_'):-len('.xlsx')]
                file_timestamp = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                
                if latest_timestamp is None or file_timestamp > latest_timestamp:
                    latest_timestamp = file_timestamp
                    latest_file = filename
            except ValueError:
                logger.warning(f"  WARNING: Could not parse timestamp from filename: {filename}. Skipping.")
                continue
    
    if latest_file:
        full_path = os.path.join(output_folder, latest_file)
        logger.info(f"Found latest results file: '{full_path}' (Timestamp: {latest_timestamp})")
        return full_path
    else:
        logger.warning(f"No automation results files found in '{output_folder}'.")
        return None


# --- Main Undo Execution Logic ---

def run_undo_automation(results_file_path_override=None):
    """
    Executes the undo operations based on a previous automation run's results file.
    If results_file_path_override is provided, uses that. Otherwise, finds the latest.
    """
    logger.info(f"\n--- Starting Undo Automation Script ---")

    if results_file_path_override:
        results_file_path = results_file_path_override
        logger.info(f"Using provided results file: '{results_file_path}'")
    else:
        results_file_path = find_latest_results_file('output')
        if not results_file_path:
            logger.error("ERROR: No results file found to undo. Aborting.")
            return

    try:
        results_df = pd.read_excel(results_file_path)
    except Exception as e:
        logger.error(f"ERROR: Failed to read results file '{results_file_path}'. Details: {repr(e)}")
        return

    jira_keys_to_transition = set()
    pages_to_rollback = {} # {page_id: target_version_number}

    for index, row in results_df.iterrows():
        page_id = str(row['Confluence Page ID'])
        jira_key = row['New Jira Task Key']
        status = row['Status']
        original_version = row.get('Original Page Version')

        # Collect Jira keys from successful task creations
        if pd.notna(jira_key) and status == "Success":
            jira_keys_to_transition.add(jira_key)
        
        # Collect page IDs and their original versions if they were successfully updated
        if pd.notna(page_id) and pd.notna(original_version) and status == "Success":
            # Only record the rollback version for a page once (the version it had BEFORE any script modification)
            if page_id not in pages_to_rollback:
                pages_to_rollback[page_id] = original_version


    # --- Phase 1: Transition Jira Tasks ---
    logger.info(f"\n--- Phase 1: Transitioning Jira Tasks to '{config.JIRA_TARGET_STATUS_NAME}' ---")
    if not jira_keys_to_transition:
        logger.info("  No Jira tasks found for transition.")
    for jira_key in sorted(list(jira_keys_to_transition)): # Sort for consistent logging order
        _perform_jira_transition_direct(jira_key, config.JIRA_TARGET_STATUS_NAME, config.JIRA_URL, config.JIRA_API_TOKEN)


    # --- Phase 2: Rollback Confluence Pages ---
    logger.info("\n--- Phase 2: Rolling back Confluence Pages to Previous Versions ---")
    logger.warning("NOTE: This operation reverts the page to a previous version. Any legitimate changes made to the page by other users *after* the automation script ran will also be undone by this rollback.")

    if not pages_to_rollback:
        logger.info("  No Confluence pages found for rollback.")
    for page_id, original_version in sorted(pages_to_rollback.items()): # Sort for consistent logging order
        _rollback_confluence_page_version(page_id, original_version)


    logger.info("\n--- Undo Automation Script Finished ---")
    logger.info("Review the log file and Confluence/Jira to confirm changes.")


# --- Script Execution Block ---
if __name__ == "__main__":
    # You can either provide a specific file path, or let it find the latest.
    # Set to None to automatically find the latest file.
    # Set to a string like "output/automation_results_20250620_164758.xlsx" to use a specific file.
    SPECIFIC_RESULTS_FILE_TO_UNDO = None # <--- **CHANGE THIS or leave as None**

    if SPECIFIC_RESULTS_FILE_TO_UNDO:
        run_undo_automation(SPECIFIC_RESULTS_FILE_TO_UNDO)
    else:
>>>>>>> 71bb2c8db17e8064fbb838a4b18220e793cc0372
        run_undo_automation() # Find and use the latest file automatically