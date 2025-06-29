"""
Unit tests for the get_task_context utility function.

This module verifies that the `get_task_context` function correctly extracts
the most relevant contextual text for a task element from a complex
Confluence page's HTML structure. Each test case targets a specific
scenario, such as a task located under a paragraph, inside a list, within a
table, or nested under another task.
"""

import json
import logging
import os
import sys
import unittest
from typing import Any, Dict

from bs4 import BeautifulSoup

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.context_extractor import get_task_context

# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)

# --- Test Data: A sample Confluence page body in HTML format ---
# This long string is broken into multiple lines for PEP 8 compliance
# using implicit string concatenation inside parentheses.
CONFLUENCE_PAGE_HTML = (
    "<h1>Gen 20250628_121411 - L1</h1><p>This page contains Work Package: SFSEA-1258.</p>"
    '<p><ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="cb5506bf-9103-455f-966b-43372dd4eab8">'
    '<ac:parameter ac:name="server">P+F Jira</ac:parameter>'
    '<ac:parameter ac:name="columnIds">issuekey,summary,issuetype,created,updated,duedate,assignee,reporter,priority,status,resolution</ac:parameter>'
    '<ac:parameter ac:name="columns">key,summary,type,created,updated,due,assignee,reporter,priority,status,resolution</ac:parameter>'
    '<ac:parameter ac:name="serverId">a9986ca6-387c-3b09-9a85-450e12a1cf94</ac:parameter>'
    '<ac:parameter ac:name="key">SFSEA-1524</ac:parameter></ac:structured-macro></p>'
    "<ac:task-list>\n<ac:task>\n<ac:task-id>38</ac:task-id>\n<ac:task-uuid>f2613ffd-0b7f-4b3f-96a1-b35748e4d83e</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">This is the task under Jira macro</span></ac:task-body>\n'
    "</ac:task>\n</ac:task-list><p>This is the preceding paragraph</p><ac:task-list>\n<ac:task>\n<ac:task-id>32</ac:task-id>\n"
    "<ac:task-uuid>b95a1463-518e-4048-84af-444807dca84a</ac:task-uuid>\n<ac:task-status>incomplete</ac:task-status>\n"
    "<ac:task-body>Task under paragraph</ac:task-body>\n</ac:task>\n</ac:task-list><p><br /></p><ul>"
    '<li data-uuid="cba9be4b-f3dd-4b08-9937-ee343cfeaa5d">This is the preceding paragraph in the bullet point<br />'
    "<ac:task-list>\n<ac:task>\n<ac:task-id>10</ac:task-id>\n<ac:task-uuid>74ac264b-bc79-4ee4-baea-a387729815ef</ac:task-uuid>\n"
    "<ac:task-status>complete</ac:task-status>\n<ac:task-body>Task under bullet point<ac:task-list>\n<ac:task>\n"
    "<ac:task-id>33</ac:task-id>\n<ac:task-uuid>8b3ab12b-aed9-476f-8d3d-8e7034644f91</ac:task-uuid>\n"
    "<ac:task-status>incomplete</ac:task-status>\n<ac:task-body>chidlren of task under bullet point</ac:task-body>\n"
    "</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n</ac:task-list></li></ul><p><br /></p><ol>"
    '<li data-uuid="1147f487-c568-4673-8c57-f766cfe0c597">This is the preceding paragraph in the numbering point<br />'
    "<ac:task-list>\n<ac:task>\n<ac:task-id>11</ac:task-id>\n<ac:task-uuid>a4f982ea-3662-441b-8647-466b0798862c</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">Task under numbering</span><ac:task-list>\n'
    "<ac:task>\n<ac:task-id>34</ac:task-id>\n<ac:task-uuid>6f616b52-c9c0-47ee-82b9-3a802359b698</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">children of task under numbering point</span></ac:task-body>\n'
    "</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n</ac:task-list></li></ol><p><br /></p><ac:task-list>\n"
    "<ac:task>\n<ac:task-id>19</ac:task-id>\n<ac:task-uuid>652de307-3c35-431a-a72f-715b996d49e9</ac:task-uuid>\n"
    "<ac:task-status>incomplete</ac:task-status>\n<ac:task-body>This is the preceding paragraph which is also a task<br />"
    "<ac:task-list>\n<ac:task>\n<ac:task-id>20</ac:task-id>\n<ac:task-uuid>fe4f576e-35fc-4946-a781-590e985d861d</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">Task under task</span><ac:task-list>\n'
    "<ac:task>\n<ac:task-id>35</ac:task-id>\n<ac:task-uuid>2ad09049-14bc-44df-90cd-5faf95ab98fd</ac:task-uuid>\n"
    '<ac:task-status>complete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">children of task under tasks </span></ac:task-body>\n'
    "</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n</ac:task-list><p><br /></p>"
    '<table class="wrapped"><colgroup><col /><col /></colgroup><tbody><tr><th scope="col">Details</th><th scope="col">Task</th></tr>'
    '<tr><td><div class="content-wrapper"><p><ac:image ac:thumbnail="true" ac:height="150"><ri:attachment ri:filename="pf_rgb_camera.png" /></ac:image>This is the context in the same row</p></div></td>'
    '<td><div class="content-wrapper"><p><span class="placeholder-inline-tasks">Preceding paragraph inside table</span></p>'
    "<ac:task-list>\n<ac:task>\n<ac:task-id>12</ac:task-id>\n<ac:task-uuid>c6d59889-ea99-4e64-a984-640ade967163</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">task 1 in the table</span><ac:task-list>\n'
    "<ac:task>\n<ac:task-id>23</ac:task-id>\n<ac:task-uuid>f2486449-aaf6-4868-95f8-ede4f4638c10</ac:task-uuid>\n"
    '<ac:task-status>complete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">children of task 1 in table</span><ac:task-list>\n'
    "<ac:task>\n<ac:task-id>36</ac:task-id>\n<ac:task-uuid>4fa6ca23-7816-4b74-8a64-0e31c31fd076</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">grandchildren of task 1 in the table</span></ac:task-body>\n'
    "</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n"
    "<ac:task>\n<ac:task-id>40</ac:task-id>\n<ac:task-uuid>9a8fdfd4-db08-4760-9d26-f29f7f6b142a</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">task 2 same sibling in table</span></ac:task-body>\n'
    "</ac:task>\n</ac:task-list><p><br /></p></div></td></tr></tbody></table><p><br /></p>"
    "<p>This is the preceding paragraph before a list of task</p><ac:task-list>\n<ac:task>\n<ac:task-id>14</ac:task-id>\n"
    "<ac:task-uuid>101c32aa-0db3-4bac-b6f9-08095efda87b</ac:task-uuid>\n<ac:task-status>incomplete</ac:task-status>\n"
    '<ac:task-body><span class="placeholder-inline-tasks">task 1 in a list</span><ac:task-list>\n<ac:task>\n'
    "<ac:task-id>24</ac:task-id>\n<ac:task-uuid>da0d2a5d-5955-4423-bc83-b538b531a59d</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">children of task 1 in a list</span><ac:task-list>\n'
    "<ac:task>\n<ac:task-id>26</ac:task-id>\n<ac:task-uuid>c40b7c3b-b51d-4d39-85ad-2372834946c8</ac:task-uuid>\n"
    '<ac:task-status>complete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">grandchildren of task 1 in a list</span></ac:task-body>\n'
    "</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n</ac:task-list></ac:task-body>\n</ac:task>\n"
    "<ac:task>\n<ac:task-id>15</ac:task-id>\n<ac:task-uuid>54fcaf02-9ba1-4f4b-adb1-74064782bc42</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span class="placeholder-inline-tasks">task 2 in a list</span></ac:task-body>\n'
    "</ac:task>\n<ac:task>\n<ac:task-id>16</ac:task-id>\n<ac:task-uuid>c97ed871-0873-40ed-9961-b58b74dcb8fa</ac:task-uuid>\n"
    '<ac:task-status>incomplete</ac:task-status>\n<ac:task-body><span> </span></ac:task-body>\n</ac:task>\n'
    "</ac:task-list><p><br /></p>"
)

# A dictionary representing the full page object.
PAGE_DATA_DICT = {
    "id": "441386294",
    "type": "page",
    "status": "current",
    "title": "Gen 20250628_121411 - L1",
    "version": {
        "by": {
            "type": "known",
            "username": "tdnguyen",
            "userKey": "ff80818177ca630d0177cf5f93370044",
            "profilePicture": {
                "path": "/download/attachments/3408224/user-avatar",
                "width": 48,
                "height": 48,
                "isDefault": False,
            },
            "displayName": "Nguyen Tuan Dat",
            "_links": {
                "self": "https://pfteamspace.pepperl-fuchs.com/rest/api/user?key=ff80818177ca630d0177cf5f93370044"
            },
            "_expandable": {"status": ""},
        },
        "when": "2025-06-29T10:29:43.000+02:00",
        "number": 69,
        "minorEdit": False,
        "hidden": False,
        "_links": {
            "self": "https://pfteamspace.pepperl-fuchs.com/rest/experimental/content/441386294/version/69"
        },
        "_expandable": {"content": "/rest/api/content/441386294"},
    },
    "position": -1,
    "body": {
        "storage": {
            "value": CONFLUENCE_PAGE_HTML,
            "representation": "storage",
            "_expandable": {"content": "/rest/api/content/441386294"},
        },
        "_expandable": {
            "editor": "",
            "view": "",
            "export_view": "",
            "styled_view": "",
            "anonymous_export_view": "",
        },
    },
    "extensions": {"position": "none"},
    "_links": {
        "webui": "/spaces/EUDEMHTM0589/pages/441386294/Gen+20250628_121411+-+L1",
        "edit": "/pages/resumedraft.action?draftId=441386294",
        "tinyui": "/x/NgVPGg",
        "collection": "/rest/api/content",
        "base": "https://pfteamspace.pepperl-fuchs.com",
        "context": "",
        "self": "https://pfteamspace.pepperl-fuchs.com/rest/api/content/441386294",
    },
    "_expandable": {
        "container": "/rest/api/space/EUDEMHTM0589",
        "metadata": "",
        "operations": "",
        "children": "/rest/api/content/441386294/child",
        "restrictions": "/rest/api/content/441386294/restriction/byOperation",
        "history": "/rest/api/content/441386294/history",
        "ancestors": "",
        "descendants": "/rest/api/content/441386294/descendant",
        "space": "/rest/api/space/EUDEMHTM0589",
    },
}

# The dictionary is converted to a valid JSON string for testing.
CONFLUENCE_PAGE_JSON = json.dumps(PAGE_DATA_DICT)


class TestContextExtractor(unittest.TestCase):
    """Test suite for the get_task_context function."""

    def setUp(self) -> None:
        """
        Set up the test environment before each test case.

        This method loads the sample Confluence page HTML from the JSON
        string and parses it into a BeautifulSoup object, making it
        available as `self.soup` for all tests.
        """
        data: Dict[str, Any] = json.loads(CONFLUENCE_PAGE_JSON)
        html_content: str = data["body"]["storage"]["value"]
        self.soup = BeautifulSoup(html_content, "html.parser")

    def _get_task_parent_by_id(self, task_id: str) -> BeautifulSoup:
        """
        A helper method to find a specific task element by its ID.

        Args:
            task_id (str): The ID of the task to find (can be numerical or string).

        Returns:
            BeautifulSoup: The parent `<ac:task>` element.
        """
        task_element = self.soup.find("ac:task-id", string=str(task_id))
        self.assertIsNotNone(
            task_element, f"Test setup failed: Could not find task with ID {task_id}"
        )
        return task_element.find_parent("ac:task")
        
    def test_task_preceded_by_jira_macro(self) -> None:
        """Verify context extraction for a task preceded by a Jira macro."""
        task_element = self._get_task_parent_by_id("38")
        expected_context = "JIRA_KEY_CONTEXT::SFSEA-1524"
        self.assertEqual(get_task_context(task_element), expected_context)   
        
    def test_task_under_paragraph(self) -> None:
        """Verify context extraction for a task directly under a paragraph."""
        task_element = self._get_task_parent_by_id("32")
        expected_context = "This is the preceding paragraph"
        self.assertEqual(get_task_context(task_element), expected_context)
    
    def test_task_in_bullet_point(self) -> None:
        """Verify context extraction for a task within a `<li>` (bullet) element."""
        task_element = self._get_task_parent_by_id("10")
        expected_context = "This is the preceding paragraph in the bullet point"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_task_in_numbered_list(self) -> None:
        """Verify context extraction for a task within an `<ol>` list."""
        task_element = self._get_task_parent_by_id("11")
        expected_context = "This is the preceding paragraph in the numbering point"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_task_inside_table(self) -> None:
        """Verify context extraction for a task inside a table cell."""
        task_element = self._get_task_parent_by_id("12")
        # Expected context should NOT contain the image tag now that it's being removed
        expected_context = (
            "| Details | Task |\n"
            "| This is the context in the same row | Preceding paragraph inside table |"
        )
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_sibling_task_in_table(self) -> None:
        """Verify context for a sibling task in the same table cell."""
        task_element = self._get_task_parent_by_id("40") 
        # Expected context should NOT contain the image tag now that it's being removed
        expected_context = (
            "| Details | Task |\n"
            "| This is the context in the same row | Preceding paragraph inside table |"
        )
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_task_in_table(self) -> None:
        """Verify context for a deeply nested task within a table cell."""
        task_element = self._get_task_parent_by_id("23")
        # The logic prioritizes the immediate parent task's body as context.
        # This test verifies that behavior.
        expected_context = "task 1 in the table"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_task_in_table_grandchild(self) -> None:
        """Verify context for a grandchild task within a table cell."""
        task_element = self._get_task_parent_by_id("36")
        expected_context = "children of task 1 in table"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_first_task_in_list(self) -> None:
        """Verify context for the first task in a list with a preceding paragraph."""
        task_element = self._get_task_parent_by_id("14")
        expected_context = "This is the preceding paragraph before a list of task"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_subsequent_tasks_in_list(self) -> None:
        """Verify context for subsequent tasks in the same list."""
        task_element_15 = self._get_task_parent_by_id("15")
        task_element_16 = self._get_task_parent_by_id("16")
        expected_context = "This is the preceding paragraph before a list of task"
        self.assertEqual(get_task_context(task_element_15), expected_context)
        self.assertEqual(get_task_context(task_element_16), expected_context)

    def test_nested_task_under_list_task(self) -> None:
        """Verify context for a task nested under another task in a list."""
        task_element = self._get_task_parent_by_id("24")
        expected_context = "task 1 in a list"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_task_under_list_task_grandchild(self) -> None:
        """Verify context for a grandchild task nested under a task in a list."""
        task_element = self._get_task_parent_by_id("26")
        expected_context = "children of task 1 in a list"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_top_level_task_with_robust_fallback(self) -> None:
        """Verify the fallback mechanism finds the nearest preceding text block."""
        task_element = self._get_task_parent_by_id("19")
        expected_context = "This is the preceding paragraph in the numbering point"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_under_top_level_task(self) -> None:
        """Verify context for a task nested under a top-level task."""
        task_element = self._get_task_parent_by_id("20")
        expected_context = "This is the preceding paragraph which is also a task"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_under_top_level_task_grandchild(self) -> None:
        """Verify context for a grandchild task nested under a top-level task."""
        task_element = self._get_task_parent_by_id("35")
        expected_context = "Task under task"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_task_in_bullet_point_grandchild(self) -> None:
        """Verify context for a grandchild task within a `<li>` (bullet) element."""
        task_element = self._get_task_parent_by_id("33")
        expected_context = "Task under bullet point"
        self.assertEqual(get_task_context(task_element), expected_context)

    def test_nested_task_in_numbered_list_grandchild(self) -> None:
        """Verify context for a grandchild task within an `<ol>` list."""
        task_element = self._get_task_parent_by_id("34")
        expected_context = "Task under numbering"
        self.assertEqual(get_task_context(task_element), expected_context)


if __name__ == "__main__":
    unittest.main()