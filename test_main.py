<<<<<<< HEAD
# test_main.py - Final Complete and Corrected Unit tests for main.py

import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os # Ensure os is imported here for test file operations
import datetime
import pandas as pd
import logging # Import logging module

# Import ApiError and requests for side_effect
from atlassian.errors import ApiError
import requests

# Adjust the path to import main and config correctly if not in the same directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import the main script and config
import main
import config

# --- Mock Data (DEFINED GLOBALLY AT THE TOP) ---
MOCK_CONFLUENCE_LONG_URL = "https://pfteamspace.pepperl-fuchs.com/spaces/EUDEMHTM0589/pages/422189659/Main+page"
MOCK_CONFLUENCE_SHORT_URL = "https://pfteamspace.pepperl-fuchs.com/x/WxoqGQ"
MOCK_CONFLUENCE_API_TOKEN = "TEST_CONFLUENCE_TOKEN"
MOCK_JIRA_API_TOKEN = "TEST_JIRA_TOKEN"
MOCK_JIRA_URL = "https://pfjira.pepperl-fuchs.com/"
MOCK_JIRA_PROJECT_KEY = "SFSEA"
MOCK_WORK_PACKAGE_ISSUE_TYPE_ID = "10100"
MOCK_TASK_ISSUE_TYPE_ID = "10002"
MOCK_DEFAULT_DUE_DATE = "2025-06-27"
MOCK_JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"

# Mock Confluence Page HTML Content (body.storage.value)
MOCK_HTML_NO_MACROS = "<body><p>Some plain text content.</p></body>"

MOCK_HTML_WITH_WORK_PACKAGE = f"""
<body>
    <p>This page has a work package:</p>
    <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="macro1">
        <ac:parameter ac:name="key">{MOCK_JIRA_PROJECT_KEY}-777</ac:parameter>
    </ac:structured-macro>
    <p>More content.</p>
</body>
"""

MOCK_HTML_WITH_NON_WP_JIRA_MACRO = f"""
<body>
    <p>This page has a non-work package Jira link:</p>
    <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="macro2">
        <ac:parameter ac:name="key">{MOCK_JIRA_PROJECT_KEY}-123</ac:parameter>
    </ac:structured-macro>
</body>
"""

MOCK_HTML_WITH_AGGREGATE_JIRA_MACRO = f"""
<body>
    <p>This page has an aggregate macro with a Jira inside:</p>
    <ac:structured-macro ac:name="excerpt-include" ac:schema-version="1" ac:macro-id="agg_macro">
        <ac:parameter ac:name="jira">
            <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="inner_macro">
                <ac:parameter ac:name="key">{MOCK_JIRA_PROJECT_KEY}-999</ac:parameter>
            </ac:structured-macro>
        </ac:parameter>
    </ac:structured-macro>
</body>
"""

MOCK_HTML_WITH_INCOMPLETE_TASK_NO_ASSIGNEE_NO_DATE = """
<body>
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task without assignee or date</ac:task-body></ac:task></ac:task-list>
</body>
"""

MOCK_HTML_WITH_INCOMPLETE_TASK_WITH_ASSIGNEE_AND_DATE = """
<body>
    <ac:task-list><ac:task><ac:task-id>task2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task with assignee and date <ri:user ri:userkey="12345:mockuserkey" /></ac:task-body><time datetime="2025-07-01"></time></ac:task></ac:task-list>
</body>
"""

MOCK_HTML_WITH_COMPLETE_TASK = """
<body>
    <ac:task-list><ac:task><ac:task-id>task3</ac:task-id><ac:task-status>complete</ac:task-status><ac:task-body>Completed Task</ac:task-body></ac:task></ac:task-list>
</body>
"""

MOCK_HTML_WITH_TASK_IN_AGGREGATE_MACRO = """
<body>
    <ac:structured-macro ac:name="excerpt-include" ac:schema-version="1" ac:macro-id="agg_task_macro">
        <ac:task-list><ac:task><ac:task-id>task4</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task inside excerpt-include</ac:task-body></ac:task></ac:task-list>
    </ac:structured-macro>
</body>
"""

# Mock Jira Issue Responses
MOCK_JIRA_WP_ISSUE = {
    'key': f"{MOCK_JIRA_PROJECT_KEY}-777",
    'fields': {
        'issuetype': {'id': MOCK_WORK_PACKAGE_ISSUE_TYPE_ID},
        'assignee': {'name': 'tdnguyen'},
        'reporter': {'name': 'testreporter'}
    }
}

MOCK_JIRA_TASK_ISSUE_CREATED = {
    'key': f"{MOCK_JIRA_PROJECT_KEY}-800",
    'id': '10000'
}

MOCK_JIRA_NON_WP_ISSUE = {
    'key': f"{MOCK_JIRA_PROJECT_KEY}-123",
    'fields': {
        'issuetype': {'id': '10001'}, # Different issue type
        'assignee': None,
        'reporter': None
    }
}

# Mock Confluence Page Responses (from get_page_by_id)
def mock_confluence_get_page_response(page_id, html_content, title="Mock Page", ancestors=None):
    if ancestors is None:
        ancestors = []
    return {
        'id': page_id,
        'title': title,
        'body': {'storage': {'value': html_content}},
        'links': {'webui': f"http://mock-confluence.com/pages/{page_id}/Mock+Page"},
        'ancestors': ancestors
    }


class TestAutomationScript(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Temporarily disable actual logging output during tests
        for handler in main.logger.handlers[:]:
            main.logger.removeHandler(handler)
        main.logger.propagate = False
        main.logger.setLevel(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        # Re-enable logging after tests
        main.logger.propagate = True
        main.logger.setLevel(logging.INFO)


    def setUp(self):
        # Patch the classes where they are imported/instantiated in main.py
        self.patcher_confluence_class = patch('main.Confluence')
        self.mock_confluence_class = self.patcher_confluence_class.start()
        self.mock_confluence_instance = MagicMock()
        self.mock_confluence_class.return_value = self.mock_confluence_instance

        self.patcher_jira_class = patch('main.Jira')
        self.mock_jira_class = self.patcher_jira_class.start()
        self.mock_jira_instance = MagicMock()
        self.mock_jira_class.return_value = self.mock_jira_instance

        # Patch requests (the module itself, not just its methods)
        self.patcher_requests = patch('main.requests')
        self.mock_requests = self.patcher_requests.start()
        self.mock_requests.exceptions = requests.exceptions

        # Patch os.makedirs and os.path.exists globally in setUp
        # These will be explicitly controlled in run_automation_script_full_flow
        self.patcher_os_makedirs = patch('main.os.makedirs')
        self.mock_os_makedirs = self.patcher_os_makedirs.start()
        
        self.patcher_os_path_exists = patch('main.os.path.exists')
        self.mock_os_path_exists = self.patcher_os_path_exists.start()
        # Do NOT set return_value here. It will be set as side_effect in the specific test.


        self.patcher_pd_read_excel = patch('main.pd.read_excel')
        self.mock_pd_read_excel = self.patcher_pd_read_excel.start()
        
        self.patcher_pd_DataFrame_to_excel = patch('main.pd.DataFrame.to_excel')
        self.mock_pd_DataFrame_to_excel = self.patcher_pd_DataFrame_to_excel.start()

        # Patch module-level global instances in main.py
        self.patcher_main_confluence_global_obj = patch('main.confluence', new=self.mock_confluence_instance)
        self.patcher_main_confluence_global_obj.start()

        self.patcher_main_jira_global_obj = patch('main.jira', new=self.mock_jira_instance)
        self.patcher_main_jira_global_obj.start()


        # Mock config values
        self.original_config_jira_url = config.JIRA_URL
        self.original_config_jira_token = config.JIRA_API_TOKEN
        self.original_config_wp_issue_type_id = config.WORK_PACKAGE_ISSUE_TYPE_ID
        self.original_config_task_issue_type_id = config.TASK_ISSUE_TYPE_ID
        self.original_config_jira_project_key = config.JIRA_PROJECT_KEY
        self.original_config_jira_macro_server_name = config.JIRA_MACRO_SERVER_NAME
        self.original_config_jira_macro_server_id = config.JIRA_MACRO_SERVER_ID
        self.original_config_jira_parent_wp_custom_field_id = config.JIRA_PARENT_WP_CUSTOM_FIELD_ID
        self.original_config_aggregate_macro_names = config.AGGREGATE_MACRO_NAMES
        self.original_config_default_due_date = config.DEFAULT_DUE_DATE
        self.original_config_jira_target_status_name = config.JIRA_TARGET_STATUS_NAME

        config.WORK_PACKAGE_ISSUE_TYPE_ID = MOCK_WORK_PACKAGE_ISSUE_TYPE_ID
        config.TASK_ISSUE_TYPE_ID = MOCK_TASK_ISSUE_TYPE_ID
        config.JIRA_PROJECT_KEY = MOCK_JIRA_PROJECT_KEY
        config.JIRA_MACRO_SERVER_NAME = "P+F Jira"
        config.JIRA_MACRO_SERVER_ID = "a9986ca6-387c-3b09-9a85-450e12a1cf94"
        config.JIRA_PARENT_WP_CUSTOM_FIELD_ID = MOCK_JIRA_PARENT_WP_CUSTOM_FIELD_ID
        config.AGGREGATE_MACRO_NAMES = ["jira", "jiraissues", "excerpt-include", "include", "widget", "html"]
        config.JIRA_URL = MOCK_JIRA_URL
        config.JIRA_API_TOKEN = MOCK_JIRA_API_TOKEN
        config.DEFAULT_DUE_DATE = MOCK_DEFAULT_DUE_DATE
        config.JIRA_TARGET_STATUS_NAME = "Backlog"

        # Patch internal setup functions that are called at the start of run_automation_script
        self.patcher_main_setup_logging = patch('main._setup_logging')
        self.mock_main_setup_logging = self.patcher_main_setup_logging.start()
        self.patcher_main_initialize_api_clients = patch('main._initialize_api_clients')
        self.mock_main_initialize_api_clients = self.patcher_main_initialize_api_clients.start()


    def tearDown(self):
        # Stop all patches
        self.patcher_confluence_class.stop()
        self.patcher_jira_class.stop()
        self.patcher_requests.stop()
        
        # Stop the os.makedirs and os.path.exists patches
        self.patcher_os_makedirs.stop()
        self.patcher_os_path_exists.stop()

        self.patcher_pd_read_excel.stop()
        self.patcher_pd_DataFrame_to_excel.stop()

        self.patcher_main_confluence_global_obj.stop()
        self.patcher_main_jira_global_obj.stop()

        self.patcher_main_setup_logging.stop()
        self.patcher_main_initialize_api_clients.stop()

        # Restore original config values
        config.JIRA_URL = self.original_config_jira_url
        config.JIRA_API_TOKEN = self.original_config_jira_token
        config.WORK_PACKAGE_ISSUE_TYPE_ID = self.original_config_wp_issue_type_id
        config.TASK_ISSUE_TYPE_ID = self.original_config_task_issue_type_id
        config.JIRA_PROJECT_KEY = self.original_config_jira_project_key
        config.JIRA_MACRO_SERVER_NAME = self.original_config_jira_macro_server_name
        config.JIRA_MACRO_SERVER_ID = self.original_config_jira_macro_server_id
        config.JIRA_PARENT_WP_CUSTOM_FIELD_ID = self.original_config_jira_parent_wp_custom_field_id
        config.AGGREGATE_MACRO_NAMES = self.original_config_aggregate_macro_names
        config.DEFAULT_DUE_DATE = self.original_config_default_due_date
        config.JIRA_TARGET_STATUS_NAME = self.original_config_jira_target_status_name


    # --- Test Cases for get_page_id_from_any_url ---
    def test_get_page_id_from_long_url(self):
        url = MOCK_CONFLUENCE_LONG_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertEqual(page_id, "422189659")
        self.mock_requests.head.assert_not_called()

    def test_get_page_id_from_short_url_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = MOCK_CONFLUENCE_LONG_URL
        mock_response.raise_for_status.return_value = None

        self.mock_requests.head.return_value = mock_response

        url = MOCK_CONFLUENCE_SHORT_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertEqual(page_id, "422189659")
        self.mock_requests.head.assert_called_once_with(
            url, headers={"Authorization": f"Bearer {MOCK_CONFLUENCE_API_TOKEN}"}, allow_redirects=True, timeout=15, verify=False
        )

    def test_get_page_id_from_short_url_failure(self):
        self.mock_requests.head.side_effect = requests.exceptions.RequestException("Network error")

        url = MOCK_CONFLUENCE_SHORT_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertIsNone(page_id)
        self.mock_requests.head.assert_called_once()

    def test_get_page_id_from_short_url_no_id_in_resolved(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "http://mock-confluence.com/some/other/path"
        mock_response.raise_for_status.return_value = None

        self.mock_requests.head.return_value = mock_response

        url = MOCK_CONFLUENCE_SHORT_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertIsNone(page_id)

    # --- Test Cases for find_work_package_on_page_content ---
    def test_find_wp_on_page_success(self):
        page_id = "100"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_WORK_PACKAGE)
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_WP_ISSUE

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNotNone(wp_issue)
        self.assertEqual(wp_issue['key'], MOCK_JIRA_WP_ISSUE['key'])
        self.mock_jira_instance.get_issue.assert_called_once_with(f"{MOCK_JIRA_PROJECT_KEY}-777", fields="issuetype,assignee,reporter")
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_no_jira_macros(self):
        page_id = "101"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_NO_MACROS)

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_not_called()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_non_wp_jira_macro(self):
        page_id = "102"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_NON_WP_JIRA_MACRO)
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_NON_WP_ISSUE

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_called_once()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_jira_macro_in_aggregate(self):
        page_id = "103"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_AGGREGATE_JIRA_MACRO)

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_not_called()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_jira_issue_404_error(self):
        page_id = "104"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_WORK_PACKAGE)

        mock_response = MagicMock()
        mock_response.status_code = 404
        self.mock_jira_instance.get_issue.side_effect = ApiError(reason="Not Found", response=mock_response)

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_called_once()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    # --- Test Cases for get_all_child_pages_recursive ---
    def test_get_all_child_pages_recursive(self):
        self.mock_confluence_instance.get_page_child_by_type.side_effect = [
            [{'id': 'C1'}, {'id': 'C2'}],
            [{'id': 'G1'}],
            [],
            []
        ]
        
        children = main.get_all_child_pages_recursive('P1')
        self.assertEqual(sorted(children), sorted(['C1', 'C2', 'G1']))
        self.assertEqual(self.mock_confluence_instance.get_page_child_by_type.call_count, 4)

    def test_get_all_child_pages_recursive_no_children(self):
        self.mock_confluence_instance.get_page_child_by_type.return_value = []
        children = main.get_all_child_pages_recursive('P_NoChildren')
        self.assertEqual(children, [])
        self.mock_confluence_instance.get_page_child_by_type.assert_called_once_with('P_NoChildren', type='page')

    # --- Test Cases for get_closest_ancestor_work_package ---
    def test_get_closest_ancestor_wp_on_current_page(self):
        page_id = "B"
        ancestor_id = "A"

        self.mock_confluence_instance.get_page_by_id.side_effect = [
            mock_confluence_get_page_response(page_id, "", title="Page B", ancestors=[{'id': ancestor_id, 'title': 'Page A'}]),
            mock_confluence_get_page_response(page_id, MOCK_HTML_NO_MACROS, title="Page B"),
            mock_confluence_get_page_response(ancestor_id, MOCK_HTML_WITH_WORK_PACKAGE, title="Page A"),
        ]
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_WP_ISSUE

        wp_issue = main.get_closest_ancestor_work_package(page_id)
        self.assertIsNotNone(wp_issue)
        self.assertEqual(wp_issue['key'], MOCK_JIRA_WP_ISSUE['key'])
        self.assertEqual(self.mock_confluence_instance.get_page_by_id.call_count, 3)
        self.mock_jira_instance.get_issue.assert_called_once_with(f"{MOCK_JIRA_PROJECT_KEY}-777", fields="issuetype,assignee,reporter")


    def test_get_closest_ancestor_wp_on_grandparent_page(self):
        grandparent_id = "G"
        parent_id = "P"
        current_page_id = "C"

        self.mock_confluence_instance.get_page_by_id.side_effect = [
            mock_confluence_get_page_response(current_page_id, "", title="Page C", ancestors=[{'id': parent_id, 'title': 'Page P'}, {'id': grandparent_id, 'title': 'Page G'}]),
            mock_confluence_get_page_response(current_page_id, MOCK_HTML_NO_MACROS, title="Page C"),
            mock_confluence_get_page_response(parent_id, MOCK_HTML_NO_MACROS, title="Page P"),
            mock_confluence_get_page_response(grandparent_id, MOCK_HTML_WITH_WORK_PACKAGE, title="Page G")
        ]
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_WP_ISSUE

        wp_issue = main.get_closest_ancestor_work_package(current_page_id)
        self.assertIsNotNone(wp_issue)
        self.assertEqual(wp_issue['key'], MOCK_JIRA_WP_ISSUE['key'])
        self.assertEqual(self.mock_confluence_instance.get_page_by_id.call_count, 4)
        self.mock_jira_instance.get_issue.assert_called_once_with(f"{MOCK_JIRA_PROJECT_KEY}-777", fields="issuetype,assignee,reporter")


    def test_get_closest_ancestor_wp_no_wp_in_hierarchy(self):
        parent_id = "B"
        grandparent_id = "A"
        current_page_id = "C"

        self.mock_confluence_instance.get_page_by_id.side_effect = [
            mock_confluence_get_page_response(current_page_id, "", title="Page C", ancestors=[{'id': parent_id, 'title': 'Page B'}, {'id': grandparent_id, 'title': 'Page A'}]),
            mock_confluence_get_page_response(current_page_id, MOCK_HTML_NO_MACROS, title="Page C"),
            mock_confluence_get_page_response(parent_id, MOCK_HTML_NO_MACROS, title="Page B"),
            mock_confluence_get_page_response(grandparent_id, MOCK_HTML_NO_MACROS, title="Page A")
        ]
        self.mock_jira_instance.get_issue.return_value = None

        wp_issue = main.get_closest_ancestor_work_package(current_page_id)
        self.assertIsNone(wp_issue)
        self.assertEqual(self.mock_confluence_instance.get_page_by_id.call_count, 4)
        self.assertEqual(self.mock_jira_instance.get_issue.call_count, 0) # Corrected assertion to 0


    # --- Test Cases for process_confluence_page_for_tasks ---
    @patch('main._get_confluence_page_details')
    @patch('main._get_assignee_from_confluence_userkey')
    def test_process_page_with_incomplete_task(self, mock_get_assignee, mock_get_page_details):
        page_id = "200"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page",
            'content': MOCK_HTML_WITH_INCOMPLETE_TASK_NO_ASSIGNEE_NO_DATE
        }
        mock_get_page_details.return_value = page_info_mock
        mock_get_assignee.return_value = None

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 1)
        self.assertEqual(tasks_data[0]['task_summary'], "Task without assignee or date")
        self.assertEqual(tasks_data[0]['assignee_name'], "default_assignee")
        self.assertEqual(tasks_data[0]['due_date'], MOCK_DEFAULT_DUE_DATE)
        self.assertEqual(tasks_data[0]['confluence_task_id'], "task1")
        mock_get_page_details.assert_called_once_with(page_id)


    @patch('main._get_confluence_page_details')
    @patch('main._get_assignee_from_confluence_userkey')
    def test_process_page_with_incomplete_task_with_assignee_and_date(self, mock_get_assignee, mock_get_page_details):
        page_id = "201"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page 2',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page+2",
            'content': MOCK_HTML_WITH_INCOMPLETE_TASK_WITH_ASSIGNEE_AND_DATE
        }
        mock_get_page_details.return_value = page_info_mock
        mock_get_assignee.return_value = "mockusername"

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 1)
        self.assertEqual(tasks_data[0]['task_summary'], "Task with assignee and date")
        self.assertEqual(tasks_data[0]['assignee_name'], "mockusername")
        self.assertEqual(tasks_data[0]['due_date'], "2025-07-01")
        self.assertEqual(tasks_data[0]['confluence_task_id'], "task2")
        mock_get_page_details.assert_called_once_with(page_id)


    @patch('main._get_confluence_page_details')
    def test_process_page_with_complete_task(self, mock_get_page_details):
        page_id = "202"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page 3',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page+3",
            'content': MOCK_HTML_WITH_COMPLETE_TASK
        }
        mock_get_page_details.return_value = page_info_mock

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 0)
        mock_get_page_details.assert_called_once_with(page_id)


    @patch('main._get_confluence_page_details')
    def test_process_page_with_task_in_aggregate_macro(self, mock_get_page_details):
        page_id = "203"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page 4',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page+4",
            'content': MOCK_HTML_WITH_TASK_IN_AGGREGATE_MACRO
        }
        mock_get_page_details.return_value = page_info_mock

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 0)
        mock_get_page_details.assert_called_once_with(page_id)


    # --- Test Cases for create_jira_task ---
    @patch('main._perform_jira_issue_creation')
    @patch('main._prepare_jira_task_fields')
    @patch('main._perform_jira_transition_direct')
    def test_create_jira_task_success(self, mock_transition_direct, mock_prepare_fields, mock_issue_creation):
        task_data = {
            'confluence_page_id': 'page1', 'confluence_page_title': 'Page Title',
            'confluence_page_url': 'http://url.com/page1', 'confluence_task_id': 'task1',
            'task_summary': 'New Jira Task', 'assignee_name': 'test_user', 'due_date': '2025-07-15'
        }
        parent_key = f"{MOCK_JIRA_PROJECT_KEY}-777"
        final_assignee_name = 'test_user'

        mock_prepare_fields.return_value = {'mock_fields': True}
        mock_issue_creation.return_value = MOCK_JIRA_TASK_ISSUE_CREATED['key']
        mock_transition_direct.return_value = None

        jira_key = main.create_jira_task(task_data, parent_key, final_assignee_name)

        self.assertEqual(jira_key, MOCK_JIRA_TASK_ISSUE_CREATED['key'])
        mock_prepare_fields.assert_called_once_with(task_data, parent_key, final_assignee_name)
        mock_issue_creation.assert_called_once_with(mock_prepare_fields.return_value)
        mock_transition_direct.assert_called_once_with(
            MOCK_JIRA_TASK_ISSUE_CREATED['key'], config.JIRA_TARGET_STATUS_NAME, config.JIRA_URL, config.JIRA_API_TOKEN
        )

    @patch('main._perform_jira_issue_creation')
    @patch('main._prepare_jira_task_fields')
    @patch('main._perform_jira_transition_direct')
    def test_create_jira_task_creation_failure(self, mock_transition_direct, mock_prepare_fields, mock_issue_creation):
        task_data = {
            'confluence_page_id': 'page1', 'confluence_page_title': 'Page Title',
            'confluence_page_url': 'http://url.com/page1', 'confluence_task_id': 'task1',
            'task_summary': 'Failed Jira Task', 'assignee_name': 'test_user', 'due_date': '2025-07-15'
        }
        parent_key = f"{MOCK_JIRA_PROJECT_KEY}-777"
        final_assignee_name = 'test_user'

        mock_prepare_fields.return_value = {'mock_fields': True}
        mock_issue_creation.return_value = None
        mock_transition_direct.return_value = None

        jira_key = main.create_jira_task(task_data, parent_key, final_assignee_name)

        self.assertIsNone(jira_key)
        mock_prepare_fields.assert_called_once_with(task_data, parent_key, final_assignee_name)
        mock_issue_creation.assert_called_once_with(mock_prepare_fields.return_value)
        mock_transition_direct.assert_not_called()


    # --- Test Cases for _perform_jira_transition_direct ---
    def test_perform_jira_transition_direct_success(self):
        issue_key = f"{MOCK_JIRA_PROJECT_KEY}-888"
        target_status_name = "Backlog"
        
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status.return_value = None
        self.mock_requests.post.return_value = mock_response

        main._perform_jira_transition_direct(issue_key, target_status_name, MOCK_JIRA_URL, MOCK_JIRA_API_TOKEN)

        self.mock_requests.post.assert_called_once_with(
            f"{MOCK_JIRA_URL}/rest/api/2/issue/{issue_key}/transitions",
            headers={
                "Authorization": f"Bearer {MOCK_JIRA_API_TOKEN}",
                "Content-Type": "application/json"
            },
            json={"transition": {"id": "11"}},
            verify=False
        )

    def test_perform_jira_transition_direct_unsupported_status(self):
        issue_key = f"{MOCK_JIRA_PROJECT_KEY}-889"
        target_status_name = "In Progress"

        main._perform_jira_transition_direct(issue_key, target_status_name, MOCK_JIRA_URL, MOCK_JIRA_API_TOKEN)
        self.mock_requests.post.assert_not_called()

    def test_perform_jira_transition_direct_http_error(self):
        issue_key = f"{MOCK_JIRA_PROJECT_KEY}-890"
        target_status_name = "Backlog"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        self.mock_requests.post.side_effect = requests.exceptions.HTTPError(response=mock_response)

        main._perform_jira_transition_direct(issue_key, target_status_name, MOCK_JIRA_URL, MOCK_JIRA_API_TOKEN)
        self.mock_requests.post.assert_called_once()


    # --- Test Cases for update_confluence_page_with_jira_links ---
    @patch('main._generate_jira_macro_xml', return_value='<mock_jira_macro_xml/>')
    @patch('main._insert_jira_macro_and_remove_task')
    @patch('main._clean_empty_task_lists')
    @patch('main._update_confluence_page_content')
    def test_update_confluence_page_with_jira_links_success(self, mock_update_content, mock_clean_lists, mock_insert_macro, mock_generate_xml):
        page_id = "300"
        task_mappings = [{'confluence_task_id': 'task_a', 'jira_key': 'JIRA-1'},
                         {'confluence_task_id': 'task_b', 'jira_key': 'JIRA-2'}]
        
        initial_html = """
        <body>
            <ac:task-list>
                <ac:task><ac:task-id>task_a</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task A</ac:task-body></ac:task>
                <ac:task><ac:task-id>task_b</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task B</ac:task-body></ac:task>
            </ac:task-list>
            <p>Some other content.</p>
        </body>
        """
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, initial_html, ancestors=[])
        
        mock_insert_macro.return_value = True
        mock_update_content.return_value = True

        main.update_confluence_page_with_jira_links(page_id, task_mappings)

        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage,version,ancestors')
        self.assertEqual(mock_insert_macro.call_count, len(task_mappings))
        mock_clean_lists.assert_called_once()
        mock_update_content.assert_called_once()


    @patch('main._get_confluence_page_details')
    def test_update_confluence_page_no_mappings(self, mock_get_page_details):
        page_id = "301"
        main.update_confluence_page_with_jira_links(page_id, [])
        self.mock_confluence_instance.get_page_by_id.assert_not_called()
        self.mock_confluence_instance.update_page.assert_not_called()
        mock_get_page_details.assert_not_called()


    @patch('main._generate_jira_macro_xml')
    @patch('main._insert_jira_macro_and_remove_task')
    @patch('main._clean_empty_task_lists')
    @patch('main._update_confluence_page_content')
    def test_update_confluence_page_task_in_aggregate_not_modified(self, mock_update_content, mock_clean_lists, mock_insert_macro, mock_generate_xml):
        page_id = "302"
        task_mappings = [{'confluence_task_id': 'task_agg', 'jira_key': 'JIRA-3'}]
        initial_html = MOCK_HTML_WITH_TASK_IN_AGGREGATE_MACRO
        
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, initial_html, ancestors=[])
        
        mock_insert_macro.return_value = False

        main.update_confluence_page_with_jira_links(page_id, task_mappings)

        self.mock_confluence_instance.get_page_by_id.assert_called_once()
        mock_insert_macro.assert_called_once()
        mock_clean_lists.assert_not_called()
        mock_update_content.assert_not_called()


    # --- Test Cases for run_automation_script (the main execution function) ---
    @patch('main._setup_logging')
    @patch('main._initialize_api_clients')
    @patch('main.get_page_id_from_any_url')
    @patch('main.find_work_package_on_page_content')
    @patch('main.get_all_child_pages_recursive')
    @patch('main.process_confluence_page_for_tasks')
    @patch('main.get_closest_ancestor_work_package')
    @patch('main.create_jira_task')
    @patch('main.update_confluence_page_with_jira_links')
    @patch('main.datetime') # Patch datetime to control timestamp
    # os.makedirs and os.path.exists are patched globally in setUp/tearDown
    def test_run_automation_script_full_flow(self, mock_datetime, mock_update_confluence, mock_create_jira_task,
                                        mock_get_closest_wp, mock_process_tasks,
                                        mock_get_all_child_pages_recursive, mock_find_wp_on_page_content,
                                        mock_get_page_id_from_any_url,
                                        mock_initialize_api_clients, mock_setup_logging):
        
        # Mock os.path.exists to return False for BOTH 'logs' and 'output' directories
        # This is CRUCIAL: It covers the sequence of calls to os.path.exists
        self.mock_os_path_exists.side_effect = [False, False]

        mock_datetime.datetime.now.return_value.strftime.return_value = "20250620_153000"
        mock_datetime.datetime.now.return_value = datetime.datetime(2025, 6, 20, 15, 30, 0)

        mock_setup_logging.return_value = None
        mock_initialize_api_clients.return_value = None

        mock_input_df = pd.DataFrame([
            {'ConfluencePageURL': MOCK_CONFLUENCE_LONG_URL}
        ])
        self.mock_pd_read_excel.return_value = mock_input_df
        
        mock_get_page_id_from_any_url.return_value = "422189659"

        mock_find_wp_on_page_content.return_value = MOCK_JIRA_WP_ISSUE
        
        mock_get_all_child_pages_recursive.return_value = ['sub_page_id_1']

        expected_tasks_from_subpage_1 = [{
            'confluence_page_id': 'sub_page_id_1',
            'confluence_page_title': 'Sub Page 1',
            'confluence_page_url': 'http://url.com/sub1',
            'confluence_task_id': 'sub_task_1',
            'task_summary': 'Task from Sub Page',
            'assignee_name': None,
            'due_date': '2025-08-01'
        }]
        mock_process_tasks.side_effect = [
            [], # Result for main page (ID 422189659)
            expected_tasks_from_subpage_1 # Result for sub_page_id_1
        ]
        
        mock_get_closest_wp.return_value = MOCK_JIRA_WP_ISSUE

        mock_create_jira_task.return_value = f"{MOCK_JIRA_PROJECT_KEY}-900"

        main.run_automation_script()

        mock_setup_logging.assert_called_once_with("20250620_153000")
        mock_initialize_api_clients.assert_called_once()
        self.mock_pd_read_excel.assert_called_once_with('input.xlsx')
        mock_get_page_id_from_any_url.assert_called_once_with(MOCK_CONFLUENCE_LONG_URL, config.CONFLUENCE_API_TOKEN)
        mock_find_wp_on_page_content.assert_called_once_with("422189659")
        mock_get_all_child_pages_recursive.assert_called_once_with("422189659")
        
        self.assertEqual(mock_process_tasks.call_count, 2)
        mock_process_tasks.assert_any_call("422189659", MOCK_JIRA_WP_ISSUE['fields']['assignee']['name'])
        mock_process_tasks.assert_any_call("sub_page_id_1", MOCK_JIRA_WP_ISSUE['fields']['assignee']['name'])

        self.assertEqual(mock_get_closest_wp.call_count, 1)
        mock_get_closest_wp.assert_called_once_with('sub_page_id_1')

        self.assertEqual(mock_create_jira_task.call_count, 1)
        mock_create_jira_task.assert_called_once_with(
            expected_tasks_from_subpage_1[0],
            MOCK_JIRA_WP_ISSUE['key'],
            MOCK_JIRA_WP_ISSUE['fields']['assignee']['name']
        )
        
        self.assertEqual(mock_update_confluence.call_count, 1)
        mock_update_confluence.assert_called_once_with(
            'sub_page_id_1',
            [{'confluence_task_id': 'sub_task_1', 'jira_key': f"{MOCK_JIRA_PROJECT_KEY}-900"}]
        )
        self.mock_pd_DataFrame_to_excel.assert_called_once()
        
        # Assert os.makedirs was called as output directory should not exist in test mock
        self.assertEqual(self.mock_os_makedirs.call_count, 2) # Called for logs and output
        self.mock_os_makedirs.assert_any_call('logs')
        self.mock_os_makedirs.assert_any_call('output')

        # Assert os.path.exists was called
        self.assertEqual(self.mock_os_path_exists.call_count, 2) # Called for logs and output
        self.mock_os_path_exists.assert_any_call('logs')
        self.mock_os_path_exists.assert_any_call('output')


if __name__ == '__main__':
=======
# test_main.py - Final Complete and Corrected Unit tests for main.py

import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os # Ensure os is imported here for test file operations
import datetime
import pandas as pd
import logging # Import logging module

# Import ApiError and requests for side_effect
from atlassian.errors import ApiError
import requests

# Adjust the path to import main and config correctly if not in the same directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import the main script and config
import main
import config

# --- Mock Data (DEFINED GLOBALLY AT THE TOP) ---
MOCK_CONFLUENCE_LONG_URL = "https://pfteamspace.pepperl-fuchs.com/spaces/EUDEMHTM0589/pages/422189659/Main+page"
MOCK_CONFLUENCE_SHORT_URL = "https://pfteamspace.pepperl-fuchs.com/x/WxoqGQ"
MOCK_CONFLUENCE_API_TOKEN = "TEST_CONFLUENCE_TOKEN"
MOCK_JIRA_API_TOKEN = "TEST_JIRA_TOKEN"
MOCK_JIRA_URL = "https://pfjira.pepperl-fuchs.com/"
MOCK_JIRA_PROJECT_KEY = "SFSEA"
MOCK_WORK_PACKAGE_ISSUE_TYPE_ID = "10100"
MOCK_TASK_ISSUE_TYPE_ID = "10002"
MOCK_DEFAULT_DUE_DATE = "2025-06-27"
MOCK_JIRA_PARENT_WP_CUSTOM_FIELD_ID = "customfield_10207"

# Mock Confluence Page HTML Content (body.storage.value)
MOCK_HTML_NO_MACROS = "<body><p>Some plain text content.</p></body>"

MOCK_HTML_WITH_WORK_PACKAGE = f"""
<body>
    <p>This page has a work package:</p>
    <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="macro1">
        <ac:parameter ac:name="key">{MOCK_JIRA_PROJECT_KEY}-777</ac:parameter>
    </ac:structured-macro>
    <p>More content.</p>
</body>
"""

MOCK_HTML_WITH_NON_WP_JIRA_MACRO = f"""
<body>
    <p>This page has a non-work package Jira link:</p>
    <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="macro2">
        <ac:parameter ac:name="key">{MOCK_JIRA_PROJECT_KEY}-123</ac:parameter>
    </ac:structured-macro>
</body>
"""

MOCK_HTML_WITH_AGGREGATE_JIRA_MACRO = f"""
<body>
    <p>This page has an aggregate macro with a Jira inside:</p>
    <ac:structured-macro ac:name="excerpt-include" ac:schema-version="1" ac:macro-id="agg_macro">
        <ac:parameter ac:name="jira">
            <ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="inner_macro">
                <ac:parameter ac:name="key">{MOCK_JIRA_PROJECT_KEY}-999</ac:parameter>
            </ac:structured-macro>
        </ac:parameter>
    </ac:structured-macro>
</body>
"""

MOCK_HTML_WITH_INCOMPLETE_TASK_NO_ASSIGNEE_NO_DATE = """
<body>
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task without assignee or date</ac:task-body></ac:task></ac:task-list>
</body>
"""

MOCK_HTML_WITH_INCOMPLETE_TASK_WITH_ASSIGNEE_AND_DATE = """
<body>
    <ac:task-list><ac:task><ac:task-id>task2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task with assignee and date <ri:user ri:userkey="12345:mockuserkey" /></ac:task-body><time datetime="2025-07-01"></time></ac:task></ac:task-list>
</body>
"""

MOCK_HTML_WITH_COMPLETE_TASK = """
<body>
    <ac:task-list><ac:task><ac:task-id>task3</ac:task-id><ac:task-status>complete</ac:task-status><ac:task-body>Completed Task</ac:task-body></ac:task></ac:task-list>
</body>
"""

MOCK_HTML_WITH_TASK_IN_AGGREGATE_MACRO = """
<body>
    <ac:structured-macro ac:name="excerpt-include" ac:schema-version="1" ac:macro-id="agg_task_macro">
        <ac:task-list><ac:task><ac:task-id>task4</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task inside excerpt-include</ac:task-body></ac:task></ac:task-list>
    </ac:structured-macro>
</body>
"""

# Mock Jira Issue Responses
MOCK_JIRA_WP_ISSUE = {
    'key': f"{MOCK_JIRA_PROJECT_KEY}-777",
    'fields': {
        'issuetype': {'id': MOCK_WORK_PACKAGE_ISSUE_TYPE_ID},
        'assignee': {'name': 'tdnguyen'},
        'reporter': {'name': 'testreporter'}
    }
}

MOCK_JIRA_TASK_ISSUE_CREATED = {
    'key': f"{MOCK_JIRA_PROJECT_KEY}-800",
    'id': '10000'
}

MOCK_JIRA_NON_WP_ISSUE = {
    'key': f"{MOCK_JIRA_PROJECT_KEY}-123",
    'fields': {
        'issuetype': {'id': '10001'}, # Different issue type
        'assignee': None,
        'reporter': None
    }
}

# Mock Confluence Page Responses (from get_page_by_id)
def mock_confluence_get_page_response(page_id, html_content, title="Mock Page", ancestors=None):
    if ancestors is None:
        ancestors = []
    return {
        'id': page_id,
        'title': title,
        'body': {'storage': {'value': html_content}},
        'links': {'webui': f"http://mock-confluence.com/pages/{page_id}/Mock+Page"},
        'ancestors': ancestors
    }


class TestAutomationScript(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Temporarily disable actual logging output during tests
        for handler in main.logger.handlers[:]:
            main.logger.removeHandler(handler)
        main.logger.propagate = False
        main.logger.setLevel(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        # Re-enable logging after tests
        main.logger.propagate = True
        main.logger.setLevel(logging.INFO)


    def setUp(self):
        # Patch the classes where they are imported/instantiated in main.py
        self.patcher_confluence_class = patch('main.Confluence')
        self.mock_confluence_class = self.patcher_confluence_class.start()
        self.mock_confluence_instance = MagicMock()
        self.mock_confluence_class.return_value = self.mock_confluence_instance

        self.patcher_jira_class = patch('main.Jira')
        self.mock_jira_class = self.patcher_jira_class.start()
        self.mock_jira_instance = MagicMock()
        self.mock_jira_class.return_value = self.mock_jira_instance

        # Patch requests (the module itself, not just its methods)
        self.patcher_requests = patch('main.requests')
        self.mock_requests = self.patcher_requests.start()
        self.mock_requests.exceptions = requests.exceptions

        # Patch os.makedirs and os.path.exists globally in setUp
        # These will be explicitly controlled in run_automation_script_full_flow
        self.patcher_os_makedirs = patch('main.os.makedirs')
        self.mock_os_makedirs = self.patcher_os_makedirs.start()
        
        self.patcher_os_path_exists = patch('main.os.path.exists')
        self.mock_os_path_exists = self.patcher_os_path_exists.start()
        # Do NOT set return_value here. It will be set as side_effect in the specific test.


        self.patcher_pd_read_excel = patch('main.pd.read_excel')
        self.mock_pd_read_excel = self.patcher_pd_read_excel.start()
        
        self.patcher_pd_DataFrame_to_excel = patch('main.pd.DataFrame.to_excel')
        self.mock_pd_DataFrame_to_excel = self.patcher_pd_DataFrame_to_excel.start()

        # Patch module-level global instances in main.py
        self.patcher_main_confluence_global_obj = patch('main.confluence', new=self.mock_confluence_instance)
        self.patcher_main_confluence_global_obj.start()

        self.patcher_main_jira_global_obj = patch('main.jira', new=self.mock_jira_instance)
        self.patcher_main_jira_global_obj.start()


        # Mock config values
        self.original_config_jira_url = config.JIRA_URL
        self.original_config_jira_token = config.JIRA_API_TOKEN
        self.original_config_wp_issue_type_id = config.WORK_PACKAGE_ISSUE_TYPE_ID
        self.original_config_task_issue_type_id = config.TASK_ISSUE_TYPE_ID
        self.original_config_jira_project_key = config.JIRA_PROJECT_KEY
        self.original_config_jira_macro_server_name = config.JIRA_MACRO_SERVER_NAME
        self.original_config_jira_macro_server_id = config.JIRA_MACRO_SERVER_ID
        self.original_config_jira_parent_wp_custom_field_id = config.JIRA_PARENT_WP_CUSTOM_FIELD_ID
        self.original_config_aggregate_macro_names = config.AGGREGATE_MACRO_NAMES
        self.original_config_default_due_date = config.DEFAULT_DUE_DATE
        self.original_config_jira_target_status_name = config.JIRA_TARGET_STATUS_NAME

        config.WORK_PACKAGE_ISSUE_TYPE_ID = MOCK_WORK_PACKAGE_ISSUE_TYPE_ID
        config.TASK_ISSUE_TYPE_ID = MOCK_TASK_ISSUE_TYPE_ID
        config.JIRA_PROJECT_KEY = MOCK_JIRA_PROJECT_KEY
        config.JIRA_MACRO_SERVER_NAME = "P+F Jira"
        config.JIRA_MACRO_SERVER_ID = "a9986ca6-387c-3b09-9a85-450e12a1cf94"
        config.JIRA_PARENT_WP_CUSTOM_FIELD_ID = MOCK_JIRA_PARENT_WP_CUSTOM_FIELD_ID
        config.AGGREGATE_MACRO_NAMES = ["jira", "jiraissues", "excerpt-include", "include", "widget", "html"]
        config.JIRA_URL = MOCK_JIRA_URL
        config.JIRA_API_TOKEN = MOCK_JIRA_API_TOKEN
        config.DEFAULT_DUE_DATE = MOCK_DEFAULT_DUE_DATE
        config.JIRA_TARGET_STATUS_NAME = "Backlog"

        # Patch internal setup functions that are called at the start of run_automation_script
        self.patcher_main_setup_logging = patch('main._setup_logging')
        self.mock_main_setup_logging = self.patcher_main_setup_logging.start()
        self.patcher_main_initialize_api_clients = patch('main._initialize_api_clients')
        self.mock_main_initialize_api_clients = self.patcher_main_initialize_api_clients.start()


    def tearDown(self):
        # Stop all patches
        self.patcher_confluence_class.stop()
        self.patcher_jira_class.stop()
        self.patcher_requests.stop()
        
        # Stop the os.makedirs and os.path.exists patches
        self.patcher_os_makedirs.stop()
        self.patcher_os_path_exists.stop()

        self.patcher_pd_read_excel.stop()
        self.patcher_pd_DataFrame_to_excel.stop()

        self.patcher_main_confluence_global_obj.stop()
        self.patcher_main_jira_global_obj.stop()

        self.patcher_main_setup_logging.stop()
        self.patcher_main_initialize_api_clients.stop()

        # Restore original config values
        config.JIRA_URL = self.original_config_jira_url
        config.JIRA_API_TOKEN = self.original_config_jira_token
        config.WORK_PACKAGE_ISSUE_TYPE_ID = self.original_config_wp_issue_type_id
        config.TASK_ISSUE_TYPE_ID = self.original_config_task_issue_type_id
        config.JIRA_PROJECT_KEY = self.original_config_jira_project_key
        config.JIRA_MACRO_SERVER_NAME = self.original_config_jira_macro_server_name
        config.JIRA_MACRO_SERVER_ID = self.original_config_jira_macro_server_id
        config.JIRA_PARENT_WP_CUSTOM_FIELD_ID = self.original_config_jira_parent_wp_custom_field_id
        config.AGGREGATE_MACRO_NAMES = self.original_config_aggregate_macro_names
        config.DEFAULT_DUE_DATE = self.original_config_default_due_date
        config.JIRA_TARGET_STATUS_NAME = self.original_config_jira_target_status_name


    # --- Test Cases for get_page_id_from_any_url ---
    def test_get_page_id_from_long_url(self):
        url = MOCK_CONFLUENCE_LONG_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertEqual(page_id, "422189659")
        self.mock_requests.head.assert_not_called()

    def test_get_page_id_from_short_url_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = MOCK_CONFLUENCE_LONG_URL
        mock_response.raise_for_status.return_value = None

        self.mock_requests.head.return_value = mock_response

        url = MOCK_CONFLUENCE_SHORT_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertEqual(page_id, "422189659")
        self.mock_requests.head.assert_called_once_with(
            url, headers={"Authorization": f"Bearer {MOCK_CONFLUENCE_API_TOKEN}"}, allow_redirects=True, timeout=15, verify=False
        )

    def test_get_page_id_from_short_url_failure(self):
        self.mock_requests.head.side_effect = requests.exceptions.RequestException("Network error")

        url = MOCK_CONFLUENCE_SHORT_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertIsNone(page_id)
        self.mock_requests.head.assert_called_once()

    def test_get_page_id_from_short_url_no_id_in_resolved(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "http://mock-confluence.com/some/other/path"
        mock_response.raise_for_status.return_value = None

        self.mock_requests.head.return_value = mock_response

        url = MOCK_CONFLUENCE_SHORT_URL
        page_id = main.get_page_id_from_any_url(url, MOCK_CONFLUENCE_API_TOKEN)
        self.assertIsNone(page_id)

    # --- Test Cases for find_work_package_on_page_content ---
    def test_find_wp_on_page_success(self):
        page_id = "100"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_WORK_PACKAGE)
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_WP_ISSUE

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNotNone(wp_issue)
        self.assertEqual(wp_issue['key'], MOCK_JIRA_WP_ISSUE['key'])
        self.mock_jira_instance.get_issue.assert_called_once_with(f"{MOCK_JIRA_PROJECT_KEY}-777", fields="issuetype,assignee,reporter")
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_no_jira_macros(self):
        page_id = "101"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_NO_MACROS)

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_not_called()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_non_wp_jira_macro(self):
        page_id = "102"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_NON_WP_JIRA_MACRO)
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_NON_WP_ISSUE

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_called_once()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_jira_macro_in_aggregate(self):
        page_id = "103"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_AGGREGATE_JIRA_MACRO)

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_not_called()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    def test_find_wp_on_page_jira_issue_404_error(self):
        page_id = "104"
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, MOCK_HTML_WITH_WORK_PACKAGE)

        mock_response = MagicMock()
        mock_response.status_code = 404
        self.mock_jira_instance.get_issue.side_effect = ApiError(reason="Not Found", response=mock_response)

        wp_issue = main.find_work_package_on_page_content(page_id)
        self.assertIsNone(wp_issue)
        self.mock_jira_instance.get_issue.assert_called_once()
        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage')


    # --- Test Cases for get_all_child_pages_recursive ---
    def test_get_all_child_pages_recursive(self):
        self.mock_confluence_instance.get_page_child_by_type.side_effect = [
            [{'id': 'C1'}, {'id': 'C2'}],
            [{'id': 'G1'}],
            [],
            []
        ]
        
        children = main.get_all_child_pages_recursive('P1')
        self.assertEqual(sorted(children), sorted(['C1', 'C2', 'G1']))
        self.assertEqual(self.mock_confluence_instance.get_page_child_by_type.call_count, 4)

    def test_get_all_child_pages_recursive_no_children(self):
        self.mock_confluence_instance.get_page_child_by_type.return_value = []
        children = main.get_all_child_pages_recursive('P_NoChildren')
        self.assertEqual(children, [])
        self.mock_confluence_instance.get_page_child_by_type.assert_called_once_with('P_NoChildren', type='page')

    # --- Test Cases for get_closest_ancestor_work_package ---
    def test_get_closest_ancestor_wp_on_current_page(self):
        page_id = "B"
        ancestor_id = "A"

        self.mock_confluence_instance.get_page_by_id.side_effect = [
            mock_confluence_get_page_response(page_id, "", title="Page B", ancestors=[{'id': ancestor_id, 'title': 'Page A'}]),
            mock_confluence_get_page_response(page_id, MOCK_HTML_NO_MACROS, title="Page B"),
            mock_confluence_get_page_response(ancestor_id, MOCK_HTML_WITH_WORK_PACKAGE, title="Page A"),
        ]
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_WP_ISSUE

        wp_issue = main.get_closest_ancestor_work_package(page_id)
        self.assertIsNotNone(wp_issue)
        self.assertEqual(wp_issue['key'], MOCK_JIRA_WP_ISSUE['key'])
        self.assertEqual(self.mock_confluence_instance.get_page_by_id.call_count, 3)
        self.mock_jira_instance.get_issue.assert_called_once_with(f"{MOCK_JIRA_PROJECT_KEY}-777", fields="issuetype,assignee,reporter")


    def test_get_closest_ancestor_wp_on_grandparent_page(self):
        grandparent_id = "G"
        parent_id = "P"
        current_page_id = "C"

        self.mock_confluence_instance.get_page_by_id.side_effect = [
            mock_confluence_get_page_response(current_page_id, "", title="Page C", ancestors=[{'id': parent_id, 'title': 'Page P'}, {'id': grandparent_id, 'title': 'Page G'}]),
            mock_confluence_get_page_response(current_page_id, MOCK_HTML_NO_MACROS, title="Page C"),
            mock_confluence_get_page_response(parent_id, MOCK_HTML_NO_MACROS, title="Page P"),
            mock_confluence_get_page_response(grandparent_id, MOCK_HTML_WITH_WORK_PACKAGE, title="Page G")
        ]
        self.mock_jira_instance.get_issue.return_value = MOCK_JIRA_WP_ISSUE

        wp_issue = main.get_closest_ancestor_work_package(current_page_id)
        self.assertIsNotNone(wp_issue)
        self.assertEqual(wp_issue['key'], MOCK_JIRA_WP_ISSUE['key'])
        self.assertEqual(self.mock_confluence_instance.get_page_by_id.call_count, 4)
        self.mock_jira_instance.get_issue.assert_called_once_with(f"{MOCK_JIRA_PROJECT_KEY}-777", fields="issuetype,assignee,reporter")


    def test_get_closest_ancestor_wp_no_wp_in_hierarchy(self):
        parent_id = "B"
        grandparent_id = "A"
        current_page_id = "C"

        self.mock_confluence_instance.get_page_by_id.side_effect = [
            mock_confluence_get_page_response(current_page_id, "", title="Page C", ancestors=[{'id': parent_id, 'title': 'Page B'}, {'id': grandparent_id, 'title': 'Page A'}]),
            mock_confluence_get_page_response(current_page_id, MOCK_HTML_NO_MACROS, title="Page C"),
            mock_confluence_get_page_response(parent_id, MOCK_HTML_NO_MACROS, title="Page B"),
            mock_confluence_get_page_response(grandparent_id, MOCK_HTML_NO_MACROS, title="Page A")
        ]
        self.mock_jira_instance.get_issue.return_value = None

        wp_issue = main.get_closest_ancestor_work_package(current_page_id)
        self.assertIsNone(wp_issue)
        self.assertEqual(self.mock_confluence_instance.get_page_by_id.call_count, 4)
        self.assertEqual(self.mock_jira_instance.get_issue.call_count, 0) # Corrected assertion to 0


    # --- Test Cases for process_confluence_page_for_tasks ---
    @patch('main._get_confluence_page_details')
    @patch('main._get_assignee_from_confluence_userkey')
    def test_process_page_with_incomplete_task(self, mock_get_assignee, mock_get_page_details):
        page_id = "200"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page",
            'content': MOCK_HTML_WITH_INCOMPLETE_TASK_NO_ASSIGNEE_NO_DATE
        }
        mock_get_page_details.return_value = page_info_mock
        mock_get_assignee.return_value = None

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 1)
        self.assertEqual(tasks_data[0]['task_summary'], "Task without assignee or date")
        self.assertEqual(tasks_data[0]['assignee_name'], "default_assignee")
        self.assertEqual(tasks_data[0]['due_date'], MOCK_DEFAULT_DUE_DATE)
        self.assertEqual(tasks_data[0]['confluence_task_id'], "task1")
        mock_get_page_details.assert_called_once_with(page_id)


    @patch('main._get_confluence_page_details')
    @patch('main._get_assignee_from_confluence_userkey')
    def test_process_page_with_incomplete_task_with_assignee_and_date(self, mock_get_assignee, mock_get_page_details):
        page_id = "201"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page 2',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page+2",
            'content': MOCK_HTML_WITH_INCOMPLETE_TASK_WITH_ASSIGNEE_AND_DATE
        }
        mock_get_page_details.return_value = page_info_mock
        mock_get_assignee.return_value = "mockusername"

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 1)
        self.assertEqual(tasks_data[0]['task_summary'], "Task with assignee and date")
        self.assertEqual(tasks_data[0]['assignee_name'], "mockusername")
        self.assertEqual(tasks_data[0]['due_date'], "2025-07-01")
        self.assertEqual(tasks_data[0]['confluence_task_id'], "task2")
        mock_get_page_details.assert_called_once_with(page_id)


    @patch('main._get_confluence_page_details')
    def test_process_page_with_complete_task(self, mock_get_page_details):
        page_id = "202"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page 3',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page+3",
            'content': MOCK_HTML_WITH_COMPLETE_TASK
        }
        mock_get_page_details.return_value = page_info_mock

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 0)
        mock_get_page_details.assert_called_once_with(page_id)


    @patch('main._get_confluence_page_details')
    def test_process_page_with_task_in_aggregate_macro(self, mock_get_page_details):
        page_id = "203"
        page_info_mock = {
            'id': page_id,
            'title': 'Test Page 4',
            'url': f"http://mock-confluence.com/pages/{page_id}/Test+Page+4",
            'content': MOCK_HTML_WITH_TASK_IN_AGGREGATE_MACRO
        }
        mock_get_page_details.return_value = page_info_mock

        tasks_data = main.process_confluence_page_for_tasks(page_id, "default_assignee")
        self.assertEqual(len(tasks_data), 0)
        mock_get_page_details.assert_called_once_with(page_id)


    # --- Test Cases for create_jira_task ---
    @patch('main._perform_jira_issue_creation')
    @patch('main._prepare_jira_task_fields')
    @patch('main._perform_jira_transition_direct')
    def test_create_jira_task_success(self, mock_transition_direct, mock_prepare_fields, mock_issue_creation):
        task_data = {
            'confluence_page_id': 'page1', 'confluence_page_title': 'Page Title',
            'confluence_page_url': 'http://url.com/page1', 'confluence_task_id': 'task1',
            'task_summary': 'New Jira Task', 'assignee_name': 'test_user', 'due_date': '2025-07-15'
        }
        parent_key = f"{MOCK_JIRA_PROJECT_KEY}-777"
        final_assignee_name = 'test_user'

        mock_prepare_fields.return_value = {'mock_fields': True}
        mock_issue_creation.return_value = MOCK_JIRA_TASK_ISSUE_CREATED['key']
        mock_transition_direct.return_value = None

        jira_key = main.create_jira_task(task_data, parent_key, final_assignee_name)

        self.assertEqual(jira_key, MOCK_JIRA_TASK_ISSUE_CREATED['key'])
        mock_prepare_fields.assert_called_once_with(task_data, parent_key, final_assignee_name)
        mock_issue_creation.assert_called_once_with(mock_prepare_fields.return_value)
        mock_transition_direct.assert_called_once_with(
            MOCK_JIRA_TASK_ISSUE_CREATED['key'], config.JIRA_TARGET_STATUS_NAME, config.JIRA_URL, config.JIRA_API_TOKEN
        )

    @patch('main._perform_jira_issue_creation')
    @patch('main._prepare_jira_task_fields')
    @patch('main._perform_jira_transition_direct')
    def test_create_jira_task_creation_failure(self, mock_transition_direct, mock_prepare_fields, mock_issue_creation):
        task_data = {
            'confluence_page_id': 'page1', 'confluence_page_title': 'Page Title',
            'confluence_page_url': 'http://url.com/page1', 'confluence_task_id': 'task1',
            'task_summary': 'Failed Jira Task', 'assignee_name': 'test_user', 'due_date': '2025-07-15'
        }
        parent_key = f"{MOCK_JIRA_PROJECT_KEY}-777"
        final_assignee_name = 'test_user'

        mock_prepare_fields.return_value = {'mock_fields': True}
        mock_issue_creation.return_value = None
        mock_transition_direct.return_value = None

        jira_key = main.create_jira_task(task_data, parent_key, final_assignee_name)

        self.assertIsNone(jira_key)
        mock_prepare_fields.assert_called_once_with(task_data, parent_key, final_assignee_name)
        mock_issue_creation.assert_called_once_with(mock_prepare_fields.return_value)
        mock_transition_direct.assert_not_called()


    # --- Test Cases for _perform_jira_transition_direct ---
    def test_perform_jira_transition_direct_success(self):
        issue_key = f"{MOCK_JIRA_PROJECT_KEY}-888"
        target_status_name = "Backlog"
        
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status.return_value = None
        self.mock_requests.post.return_value = mock_response

        main._perform_jira_transition_direct(issue_key, target_status_name, MOCK_JIRA_URL, MOCK_JIRA_API_TOKEN)

        self.mock_requests.post.assert_called_once_with(
            f"{MOCK_JIRA_URL}/rest/api/2/issue/{issue_key}/transitions",
            headers={
                "Authorization": f"Bearer {MOCK_JIRA_API_TOKEN}",
                "Content-Type": "application/json"
            },
            json={"transition": {"id": "11"}},
            verify=False
        )

    def test_perform_jira_transition_direct_unsupported_status(self):
        issue_key = f"{MOCK_JIRA_PROJECT_KEY}-889"
        target_status_name = "In Progress"

        main._perform_jira_transition_direct(issue_key, target_status_name, MOCK_JIRA_URL, MOCK_JIRA_API_TOKEN)
        self.mock_requests.post.assert_not_called()

    def test_perform_jira_transition_direct_http_error(self):
        issue_key = f"{MOCK_JIRA_PROJECT_KEY}-890"
        target_status_name = "Backlog"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        self.mock_requests.post.side_effect = requests.exceptions.HTTPError(response=mock_response)

        main._perform_jira_transition_direct(issue_key, target_status_name, MOCK_JIRA_URL, MOCK_JIRA_API_TOKEN)
        self.mock_requests.post.assert_called_once()


    # --- Test Cases for update_confluence_page_with_jira_links ---
    @patch('main._generate_jira_macro_xml', return_value='<mock_jira_macro_xml/>')
    @patch('main._insert_jira_macro_and_remove_task')
    @patch('main._clean_empty_task_lists')
    @patch('main._update_confluence_page_content')
    def test_update_confluence_page_with_jira_links_success(self, mock_update_content, mock_clean_lists, mock_insert_macro, mock_generate_xml):
        page_id = "300"
        task_mappings = [{'confluence_task_id': 'task_a', 'jira_key': 'JIRA-1'},
                         {'confluence_task_id': 'task_b', 'jira_key': 'JIRA-2'}]
        
        initial_html = """
        <body>
            <ac:task-list>
                <ac:task><ac:task-id>task_a</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task A</ac:task-body></ac:task>
                <ac:task><ac:task-id>task_b</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task B</ac:task-body></ac:task>
            </ac:task-list>
            <p>Some other content.</p>
        </body>
        """
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, initial_html, ancestors=[])
        
        mock_insert_macro.return_value = True
        mock_update_content.return_value = True

        main.update_confluence_page_with_jira_links(page_id, task_mappings)

        self.mock_confluence_instance.get_page_by_id.assert_called_once_with(page_id, expand='body.storage,version,ancestors')
        self.assertEqual(mock_insert_macro.call_count, len(task_mappings))
        mock_clean_lists.assert_called_once()
        mock_update_content.assert_called_once()


    @patch('main._get_confluence_page_details')
    def test_update_confluence_page_no_mappings(self, mock_get_page_details):
        page_id = "301"
        main.update_confluence_page_with_jira_links(page_id, [])
        self.mock_confluence_instance.get_page_by_id.assert_not_called()
        self.mock_confluence_instance.update_page.assert_not_called()
        mock_get_page_details.assert_not_called()


    @patch('main._generate_jira_macro_xml')
    @patch('main._insert_jira_macro_and_remove_task')
    @patch('main._clean_empty_task_lists')
    @patch('main._update_confluence_page_content')
    def test_update_confluence_page_task_in_aggregate_not_modified(self, mock_update_content, mock_clean_lists, mock_insert_macro, mock_generate_xml):
        page_id = "302"
        task_mappings = [{'confluence_task_id': 'task_agg', 'jira_key': 'JIRA-3'}]
        initial_html = MOCK_HTML_WITH_TASK_IN_AGGREGATE_MACRO
        
        self.mock_confluence_instance.get_page_by_id.return_value = mock_confluence_get_page_response(page_id, initial_html, ancestors=[])
        
        mock_insert_macro.return_value = False

        main.update_confluence_page_with_jira_links(page_id, task_mappings)

        self.mock_confluence_instance.get_page_by_id.assert_called_once()
        mock_insert_macro.assert_called_once()
        mock_clean_lists.assert_not_called()
        mock_update_content.assert_not_called()


    # --- Test Cases for run_automation_script (the main execution function) ---
    @patch('main._setup_logging')
    @patch('main._initialize_api_clients')
    @patch('main.get_page_id_from_any_url')
    @patch('main.find_work_package_on_page_content')
    @patch('main.get_all_child_pages_recursive')
    @patch('main.process_confluence_page_for_tasks')
    @patch('main.get_closest_ancestor_work_package')
    @patch('main.create_jira_task')
    @patch('main.update_confluence_page_with_jira_links')
    @patch('main.datetime') # Patch datetime to control timestamp
    # os.makedirs and os.path.exists are patched globally in setUp/tearDown
    def test_run_automation_script_full_flow(self, mock_datetime, mock_update_confluence, mock_create_jira_task,
                                        mock_get_closest_wp, mock_process_tasks,
                                        mock_get_all_child_pages_recursive, mock_find_wp_on_page_content,
                                        mock_get_page_id_from_any_url,
                                        mock_initialize_api_clients, mock_setup_logging):
        
        # Mock os.path.exists to return False for BOTH 'logs' and 'output' directories
        # This is CRUCIAL: It covers the sequence of calls to os.path.exists
        self.mock_os_path_exists.side_effect = [False, False]

        mock_datetime.datetime.now.return_value.strftime.return_value = "20250620_153000"
        mock_datetime.datetime.now.return_value = datetime.datetime(2025, 6, 20, 15, 30, 0)

        mock_setup_logging.return_value = None
        mock_initialize_api_clients.return_value = None

        mock_input_df = pd.DataFrame([
            {'ConfluencePageURL': MOCK_CONFLUENCE_LONG_URL}
        ])
        self.mock_pd_read_excel.return_value = mock_input_df
        
        mock_get_page_id_from_any_url.return_value = "422189659"

        mock_find_wp_on_page_content.return_value = MOCK_JIRA_WP_ISSUE
        
        mock_get_all_child_pages_recursive.return_value = ['sub_page_id_1']

        expected_tasks_from_subpage_1 = [{
            'confluence_page_id': 'sub_page_id_1',
            'confluence_page_title': 'Sub Page 1',
            'confluence_page_url': 'http://url.com/sub1',
            'confluence_task_id': 'sub_task_1',
            'task_summary': 'Task from Sub Page',
            'assignee_name': None,
            'due_date': '2025-08-01'
        }]
        mock_process_tasks.side_effect = [
            [], # Result for main page (ID 422189659)
            expected_tasks_from_subpage_1 # Result for sub_page_id_1
        ]
        
        mock_get_closest_wp.return_value = MOCK_JIRA_WP_ISSUE

        mock_create_jira_task.return_value = f"{MOCK_JIRA_PROJECT_KEY}-900"

        main.run_automation_script()

        mock_setup_logging.assert_called_once_with("20250620_153000")
        mock_initialize_api_clients.assert_called_once()
        self.mock_pd_read_excel.assert_called_once_with('input.xlsx')
        mock_get_page_id_from_any_url.assert_called_once_with(MOCK_CONFLUENCE_LONG_URL, config.CONFLUENCE_API_TOKEN)
        mock_find_wp_on_page_content.assert_called_once_with("422189659")
        mock_get_all_child_pages_recursive.assert_called_once_with("422189659")
        
        self.assertEqual(mock_process_tasks.call_count, 2)
        mock_process_tasks.assert_any_call("422189659", MOCK_JIRA_WP_ISSUE['fields']['assignee']['name'])
        mock_process_tasks.assert_any_call("sub_page_id_1", MOCK_JIRA_WP_ISSUE['fields']['assignee']['name'])

        self.assertEqual(mock_get_closest_wp.call_count, 1)
        mock_get_closest_wp.assert_called_once_with('sub_page_id_1')

        self.assertEqual(mock_create_jira_task.call_count, 1)
        mock_create_jira_task.assert_called_once_with(
            expected_tasks_from_subpage_1[0],
            MOCK_JIRA_WP_ISSUE['key'],
            MOCK_JIRA_WP_ISSUE['fields']['assignee']['name']
        )
        
        self.assertEqual(mock_update_confluence.call_count, 1)
        mock_update_confluence.assert_called_once_with(
            'sub_page_id_1',
            [{'confluence_task_id': 'sub_task_1', 'jira_key': f"{MOCK_JIRA_PROJECT_KEY}-900"}]
        )
        self.mock_pd_DataFrame_to_excel.assert_called_once()
        
        # Assert os.makedirs was called as output directory should not exist in test mock
        self.assertEqual(self.mock_os_makedirs.call_count, 2) # Called for logs and output
        self.mock_os_makedirs.assert_any_call('logs')
        self.mock_os_makedirs.assert_any_call('output')

        # Assert os.path.exists was called
        self.assertEqual(self.mock_os_path_exists.call_count, 2) # Called for logs and output
        self.mock_os_path_exists.assert_any_call('logs')
        self.mock_os_path_exists.assert_any_call('output')


if __name__ == '__main__':
>>>>>>> 71bb2c8db17e8064fbb838a4b18220e793cc0372
    unittest.main(argv=['first-arg-is-ignored'], exit=False)