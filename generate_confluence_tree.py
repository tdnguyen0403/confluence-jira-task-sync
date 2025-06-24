# generate_confluence_tree.py - Script to generate a complex Confluence page structure for real-life testing
# Ensures a single main generated page as root, fixes userkey resolution, and distributes specific WP keys.

import logging
import sys
import os
import uuid
from datetime import datetime, timedelta, date

import config  # Your configuration file
from atlassian import Confluence
from atlassian.errors import ApiError
from bs4 import BeautifulSoup

# --- Suppress SSL Warnings ---
import warnings
import urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
# -----------------------------

# --- Logging Setup ---
log_dir = 'logs_generator'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file_name = os.path.join(log_dir, f'confluence_generator_run_{timestamp}.log')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File Handler
file_handler = logging.FileHandler(log_file_name, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

logger.info(f"Confluence Page Generator Logging initialized. Output will be saved to '{log_file_name}'")
# --- End Logging Setup ---


# --- Confluence Client Initialization ---
logger.info("Initializing Confluence API client...")
confluence = Confluence(
    url=config.CONFLUENCE_URL,
    token=config.CONFLUENCE_API_TOKEN,
    cloud=False,
    verify_ssl=False
)

# --- Userkey Resolution Helper ---
def _get_userkey_from_username(username):
    """
    Resolves a Confluence username to a userkey using get_user_details_by_username
    and extracts 'userKey' based on provided API response structure.
    """
    if not username:
        return None
    logger.info(f"Attempting to resolve userkey for username: '{username}' using get_user_details_by_username...")
    try:
        # Based on your API call screenshot, this method should directly return the user object.
        user_details = confluence.get_user_details_by_username(username) # <-- Corrected method call

        userkey = user_details.get('userKey') # <-- Access 'userKey' directly from the response

        if userkey:
            logger.info(f"Successfully resolved userkey '{userkey}' for username '{username}'.")
            return userkey
        else:
            logger.warning(f"Found user details for '{username}' but 'userKey' was missing or empty. Full details: {user_details}")
            return None
    except ApiError as e:
        logger.error(f"Confluence API error resolving userkey for '{username}'. Details: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            logger.error(f"API Error Response Body for user lookup: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error resolving userkey for '{username}'. Details: {repr(e)}")
        return None


# --- HTML Content Generation Helpers ---

def _generate_jira_macro_html(jira_key):
    """Generates the Confluence storage format HTML for a Jira Issue macro."""
    return f"""
    <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
        <ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>
        <ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>
        <ac:parameter ac:name="key">{jira_key}</ac:parameter>
    </ac:structured-macro>
    """

def _generate_confluence_task_html(task_id_suffix, summary, status="incomplete", assignee_userkey=None, due_date=None):
    """Generates the Confluence storage format HTML for a single task."""
    unique_task_id = f"task-{uuid.uuid4().hex[:8]}-{task_id_suffix}"
    assignee_html = ""
    if assignee_userkey:
        assignee_html = f'<ri:user ri:userkey="{assignee_userkey}" ac:macro-id="{uuid.uuid4()}"/>'
    
    date_html = ""
    if due_date:
        if isinstance(due_date, (datetime, date)): 
            due_date_str = due_date.strftime('%Y-%m-%d')
        else:
            due_date_str = str(due_date)
        date_html = f'<time datetime="{due_date_str}"></time>'

    return f"""
    <ac:task>
        <ac:task-id>{unique_task_id}</ac:task-id>
        <ac:task-status>{status}</ac:task-status>
        <ac:task-body>{summary} {assignee_html}{date_html}</ac:task-body>
    </ac:task>
    """

def _wrap_in_task_list(task_html_elements):
    """Wraps a list of task HTML strings in an <ac:task-list>."""
    return "<ac:task-list>" + "".join(task_html_elements) + "</ac:task-list>"

def _generate_panel_html(panel_type, title, content_html):
    """Generates an info, note, tip, or warning panel macro with a title."""
    return f"""
    <ac:structured-macro ac:name="{panel_type}" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
        <ac:parameter ac:name="title">{title}</ac:parameter>
        <ac:rich-text-body>
            {content_html}
        </ac:rich-text-body>
    </ac:structured-macro>
    """

def _generate_expand_html(title, content_html):
    """Generates an expand macro."""
    return f"""
    <ac:structured-macro ac:name="expand" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
        <ac:parameter ac:name="title">{title}</ac:parameter>
        <ac:rich-text-body>
            {content_html}
        </ac:rich-text-body>
    </ac:structured-macro>
    """

def _generate_layout_html(sections_content_list, layout_type="two_thirds_right"):
    """Generates a multi-column layout."""
    sections_html = ""
    for content in sections_content_list:
        sections_html += f"""
        <ac:layout-section ac:type="{layout_type}">
            <ac:layout-cell>
                {content}
            </ac:layout-cell>
        </ac:layout-section>
        """
    return f'<ac:layout>{sections_html}</ac:layout>'

def _generate_table_html(rows_of_cells_content):
    """Generates a table from a list of lists of HTML content for cells."""
    table_rows_html = ""
    for row in rows_of_cells_content:
        cells_html = ""
        for cell_content in row:
            cells_html += f"<td>{cell_content}</td>"
        table_rows_html += f"<tr>{cells_html}</tr>"
    return f"<table><tbody>{table_rows_html}</tbody></table>"

def _generate_quote_html(content_html):
    """Generates a quote block."""
    return f"<blockquote>{content_html}</blockquote>"

def _generate_code_block_html(code, language="python"):
    """Generates a code block macro."""
    return f"""
    <ac:structured-macro ac:name="code" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
        <ac:parameter ac:name="language">{language}</ac:parameter>
        <ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>
    </ac:structured-macro>
    """

def _create_page_body_html(title, description, main_content_html=None, jira_macro_html=None):
    """Combines HTML snippets into a full Confluence page body."""
    body_content = f"<p><h1>{title}</h1></p><p>{description}</p>"
    
    if jira_macro_html:
        body_content += f"<p>{jira_macro_html}</p>"

    if main_content_html:
        body_content += main_content_html
        
    return body_content


# --- Confluence Page Creation Function ---

def create_confluence_page(space_key, parent_id, title, content_html):
    """Creates a Confluence page and returns its ID and URL."""
    try:
        new_page = confluence.create_page(
            space=space_key,
            parent_id=parent_id,
            title=title,
            body=content_html,
            representation='storage'
        )
        
        page_url = None
        if '_links' in new_page and 'webui' in new_page['_links']:
            page_url = new_page['_links']['webui']
            if not page_url.startswith('http'):
                base_url = config.CONFLUENCE_URL.rstrip('/')
                page_url = base_url + page_url
        
        if page_url:
            logger.info(f"Created page '{title}' (ID: {new_page['id']}) at: {page_url}")
            return new_page['id'], page_url
        else:
            logger.error(f"ERROR: Confluence create_page response missing expected 'webui' link for page '{title}'. Full response: {new_page}")
            return None, None
            
    except Exception as e:
        logger.error(f"ERROR: Failed to create page '{title}'. Details: {repr(e)}")
        if isinstance(e, ApiError) and hasattr(e, 'response') and hasattr(e.response, 'text'):
            logger.error(f"API Error Response Body: {e.response.text}")
        return None, None


# --- Main Tree Generation Logic ---

def generate_complex_tree_recursive(parent_confluence_id, space_key, wp_keys_to_distribute, assignee_userkey, current_depth, max_depth, task_suffix_counter, wp_index_counter, path_identifier_prefix=""):
    """
    Recursively generates a complex Confluence page hierarchy with various task and WP configurations.
    wp_keys_to_distribute: A list of specific Work Package keys to cycle through.
    wp_index_counter: The current index in the wp_keys_to_distribute list.
    """
    
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    day_after_tomorrow = today + timedelta(days=2)
    next_week = today + timedelta(weeks=1)
    two_weeks = today + timedelta(weeks=2)

    all_created_pages_in_branch = []

    num_pages_at_this_level = 3 if current_depth < max_depth else 1

    for i in range(num_pages_at_this_level):
        # The parent for the page created in *this* loop iteration is always parent_confluence_id
        parent_for_current_page_creation = parent_confluence_id 

        segment_identifier = str(i + 1)
        
        if path_identifier_prefix:
            full_page_identifier = f"{path_identifier_prefix}.{segment_identifier}"
        else:
            full_page_identifier = segment_identifier

        page_title = f"Gen {timestamp} - L{full_page_identifier}"
        page_description = f"This is Level {full_page_identifier} page, generated on {timestamp}."
        
        current_page_wp_key = None
        page_content_blocks = []
        jira_macro_for_page = None

        # --- Work Package Placement Strategy: Cycle through provided WP keys ---
        # Exclude pages specifically designed to test ignored content (e.g., segment '3' pages)
        if segment_identifier != '3' and wp_keys_to_distribute:
            current_page_wp_key = wp_keys_to_distribute[wp_index_counter % len(wp_keys_to_distribute)]
            wp_index_counter += 1 # Increment for the next page that gets a WP
            jira_macro_for_page = _generate_jira_macro_html(current_page_wp_key)
            page_description += f" This page specifically has Work Package: {current_page_wp_key}."
        else:
             page_description += " This page is designed to test ignored macros or has no specific WP assigned from the list."


        # --- Diverse Task Content Generation ---
        if segment_identifier == '1': # Pages like L1.1, L1.1.1, L2.1, etc.
            tasks_html_list = [_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Std Incomplete)", status="incomplete", assignee_userkey=assignee_userkey, due_date=tomorrow)]
            task_suffix_counter += 1
            tasks_html_list.append(_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Std Complete)", status="complete"))
            task_suffix_counter += 1
            tasks_html_list.append(_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Std Incomplete Due Today)", status="incomplete", due_date=today))
            task_suffix_counter += 1
            page_content_blocks.append(_wrap_in_task_list(tasks_html_list))
            
            panel_tasks = [_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Info Panel)", status="incomplete", due_date=next_week)]
            task_suffix_counter += 1
            page_content_blocks.append(_generate_panel_html("info", "Info Panel Tasks", _wrap_in_task_list(panel_tasks)))

        elif segment_identifier == '2': # Pages like L1.2, L2.2, etc.
            table_tasks_row1 = [_wrap_in_task_list([_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Table Cell 1)", status="incomplete")])]
            task_suffix_counter += 1
            table_tasks_row2 = [_wrap_in_task_list([_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Table Cell 2, assigned)", status="incomplete", assignee_userkey=assignee_userkey)])]
            task_suffix_counter += 1
            page_content_blocks.append(_generate_table_html([table_tasks_row1, table_tasks_row2]))

            layout_col1_content = _wrap_in_task_list([_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Layout Col 1)", status="incomplete")])
            task_suffix_counter += 1
            layout_col2_content = _wrap_in_task_list([_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Layout Col 2)", status="incomplete", due_date=day_after_tomorrow)])
            task_suffix_counter += 1
            page_content_blocks.append(_generate_layout_html([layout_col1_content, layout_col2_content], layout_type="two_columns"))

            note_tasks = [_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Note Panel)", status="incomplete")]
            task_suffix_counter += 1
            page_content_blocks.append(_generate_panel_html("note", "Important Notes", _wrap_in_task_list(note_tasks)))

        elif segment_identifier == '3': # Pages like L1.3, L2.3, L3.3 (Aggregate/Ignored Content)
            page_content_blocks.append(f"""
            <p>Tasks inside excerpt-include (automation should IGNORE):</p>
            <ac:structured-macro ac:name="excerpt-include" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
                <ac:parameter ac:name="exclude">true</ac:parameter>
                <ac:rich-text-body>
                    <ac:task-list>
                        {_generate_confluence_task_html(task_suffix_counter, f"Task {task_suffix_counter} (Ignored Excerpt)", status="incomplete")}
                    </ac:task-list>
                </ac:rich-text-body>
            </ac:structured-macro>
            """)
            task_suffix_counter += 1

            page_content_blocks.append(_generate_code_block_html(
                f"\n"
                f"<ac:task-list><ac:task><ac:task-id>task-in-code-{task_suffix_counter}</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Ignored Task (in code block)</ac:task-body></ac:task></ac:task-list>"
            ))
            task_suffix_counter += 1
            
            page_content_blocks.append(f"""
            <p>Jira Filter Macro (automation should IGNORE):</p>
            <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
                <ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>
                <ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>
                <ac:parameter ac:name="jql">project = {config.JIRA_PROJECT_KEY} AND issuetype = Bug ORDER BY created DESC</ac:parameter>
                <ac:parameter ac:name="columns">key,summary,status</ac:parameter>
                <ac:parameter ac:name="displaySummary">false</ac:parameter>
            </ac:structured-macro>
            """)

        # Create the page
        full_page_content_html = _create_page_body_html(
            title=page_title,
            description=page_description,
            main_content_html="".join(page_content_blocks),
            jira_macro_html=jira_macro_for_page
        )

        page_id, page_url = create_confluence_page(space_key, parent_for_current_page_creation, page_title, full_page_content_html)
        
        if page_id:
            all_created_pages_in_branch.append({'id': page_id, 'url': page_url, 'title': page_title, 'wp_on_page': current_page_wp_key})
            
            # Recurse for next level if max_depth not reached
            if current_depth + 1 <= max_depth:
                child_pages, updated_wp_index = generate_complex_tree_recursive( # Pass and get wp_index_counter
                    parent_confluence_id=page_id,
                    space_key=space_key,
                    wp_keys_to_distribute=wp_keys_to_distribute, # Pass the list
                    assignee_userkey=assignee_userkey,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    task_suffix_counter=task_suffix_counter,
                    wp_index_counter=wp_index_counter, # Pass current wp_index_counter
                    path_identifier_prefix=full_page_identifier
                )
                all_created_pages_in_branch.extend(child_pages)
                wp_index_counter = updated_wp_index # Update after recursive call
        else:
            logger.error(f"Failed to create page '{page_title}'. Skipping its children.")

    return all_created_pages_in_branch, wp_index_counter # Return updated wp_index_counter

# --- Main Orchestration for Tree Generation ---
def generate_main_test_tree(base_parent_confluence_id, space_key, wp_keys_to_distribute_initial, assignee_username=None, max_depth=4):
    """
    Orchestrates the creation of the entire test page hierarchy starting with a single main page.
    """
    logger.info(f"\n--- Initiating Main Test Tree Generation under Confluence Parent ID: {base_parent_confluence_id} ---")
    logger.info(f"Generating tree up to {max_depth} levels deep (below the main test page).")

    assignee_userkey = None
    if assignee_username:
        assignee_userkey = _get_userkey_from_username(assignee_username)
        if not assignee_userkey:
            logger.error(f"Could not resolve userkey for username '{assignee_username}'. Tasks won't be assigned.")
            assignee_username = None # Clear username if resolution failed

    # --- Create the single main generated page (Root of the test hierarchy) ---
    main_page_title = f"Gen {timestamp} - Main Test Page Root"
    main_page_description = f"This is the root page for a complex generated test hierarchy created on {timestamp}."
    
    # Assign the first Work Package from the list to the main test page
    main_page_wp_index = 0
    main_page_wp_key = wp_keys_to_distribute_initial[main_page_wp_index % len(wp_keys_to_distribute_initial)]
    main_page_jira_macro = _generate_jira_macro_html(main_page_wp_key)
    main_page_description += f" This main page has Work Package: {main_page_wp_key}."

    # Initial tasks for the main test page
    main_page_tasks_counter = 0
    main_page_tasks = [_generate_confluence_task_html(main_page_tasks_counter, "Main Page Task A (Incomplete)", status="incomplete", assignee_userkey=assignee_userkey, due_date=datetime.now().date() + timedelta(days=5))]
    main_page_tasks_counter += 1
    main_page_tasks.append(_generate_confluence_task_html(main_page_tasks_counter, "Main Page Task B (Complete)", status="complete"))
    main_page_tasks_counter += 1

    main_page_content = _create_page_body_html(main_page_title, main_page_description, main_content_html=_wrap_in_task_list(main_page_tasks), jira_macro_html=main_page_jira_macro)

    main_page_id, main_page_url = create_confluence_page(space_key, base_parent_confluence_id, main_page_title, main_page_content)

    all_generated_pages_info = []

    if main_page_id:
        all_generated_pages_info.append({'id': main_page_id, 'url': main_page_url, 'title': main_page_title, 'wp_on_page': main_page_wp_key})

        # Now, recursively generate the levels under this main page
        logger.info(f"\n--- Generating sub-levels under '{main_page_title}' (ID: {main_page_id}) ---")
        
        # Start recursion:
        # parent_confluence_id is the main_page_id
        # current_depth is 1 for Level 1 pages
        # task_suffix_counter carries over from main_page_tasks
        # wp_index_counter starts from the next index after main_page_wp_index
        child_pages_info, final_wp_index = generate_complex_tree_recursive(
            parent_confluence_id=main_page_id,
            space_key=space_key,
            wp_keys_to_distribute=wp_keys_to_distribute_initial, # Pass the list
            assignee_userkey=assignee_userkey, # Pass the resolved userkey
            current_depth=1, # Start at Level 1 for generated pages
            max_depth=max_depth,
            task_suffix_counter=main_page_tasks_counter, # Start task counter after main page tasks
            wp_index_counter=main_page_wp_index + 1, # Start WP index from next one after main page
            path_identifier_prefix="" # Level 1 pages don't have a prefix, their identifier is just '1', '2', '3'
        )
        all_generated_pages_info.extend(child_pages_info)
    else:
        logger.error(f"Failed to create the main test page '{main_page_title}'. Aborting tree generation.")

    if all_generated_pages_info:
        logger.info(f"\n--- Final Confluence Test Tree Generation Summary ---")
        logger.info(f"Total {len(all_generated_pages_info)} pages generated (including main test page).")
        logger.info("URLs of ALL generated pages (and their direct WP):")
        for page in all_generated_pages_info:
            wp_status = f"(WP: {page['wp_on_page']})" if page.get('wp_on_page') else "(No WP on page)"
            logger.info(f"- {page['title']} {wp_status}: {page['url']}")
        
        logger.info(f"\nTo test your main automation script, add the URL of the Main Test Page: '{all_generated_pages_info[0]['url']}' to your input.xlsx file.")
    
    return all_generated_pages_info


# --- Script Execution Block ---
if __name__ == "__main__":
    # --- Configuration for Generator Script ---
    # !! IMPORTANT !!
    # This is the Confluence Page ID under which the *entire test tree will reside*.
    # Replace with a real Confluence page ID you own and can freely create/delete pages under.
    # Example: A 'Test Automation' page in your Confluence.
    # You can get this ID from the page URL (e.g., /pages/12345/Page+Title -> ID is 12345)
    # This script will NOT create this BASE_PARENT_CONFLUENCE_PAGE_ID page itself.
    BASE_PARENT_CONFLUENCE_PAGE_ID = "422189655" # <--- **YOUR EXISTING BASE PAGE ID**

    # !! IMPORTANT !!
    # Replace with your Confluence Space Key (e.g., 'MYSPACE', 'DEV')
    CONFLUENCE_SPACE_KEY = "EUDEMHTM0589" # <--- **YOUR EXISTING SPACE KEY**

    # !! OPTIONAL !!
    # Provide the Confluence USERNAME if you want tasks to be assigned.
    # The script will try to resolve this username to a userkey.
    # If set to None, tasks will not have an explicit assignee.
    ASSIGNEE_USERNAME_FOR_GENERATED_TASKS = "tdnguyen" # <--- **OPTIONAL: Change to a real username, e.g., "tdnguyen"**

    # !! IMPORTANT !!
    # This is the list of Jira Work Package keys that will be distributed across pages.
    # Ensure these keys exist in your Jira.
    TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE = ["SFSEA-777", "SFSEA-882", "SFSEA-883"] 

    # --- Run Generation ---
    if BASE_PARENT_CONFLUENCE_PAGE_ID == "YOUR_BASE_PARENT_PAGE_ID_HERE" or \
       CONFLUENCE_SPACE_KEY == "YOUR_CONFLUENCE_SPACE_KEY_HERE":
        logger.error("\n*** ERROR: Please update BASE_PARENT_CONFLUENCE_PAGE_ID and CONFLUENCE_SPACE_KEY in generate_confluence_tree.py before running! ***")
    elif not TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE:
        logger.error("\n*** ERROR: Please provide at least one Work Package key in TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE. ***")
    else:
        final_generated_pages_info = generate_main_test_tree(
            base_parent_confluence_id=BASE_PARENT_CONFLUENCE_PAGE_ID,
            space_key=CONFLUENCE_SPACE_KEY,
            wp_keys_to_distribute_initial=TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE, # Pass the list
            assignee_username=ASSIGNEE_USERNAME_FOR_GENERATED_TASKS,
            max_depth=2 # Generates Level 1 to Level 4 pages under the Main Test Page
        )

        if final_generated_pages_info:
            logger.info("\nGenerator script finished successfully.")
        else:
            logger.error("\nPage generation failed or no pages were created.")