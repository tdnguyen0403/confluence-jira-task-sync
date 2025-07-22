"""
Tests for the get_task_context utility function using a realistic,
complex HTML document. This file preserves all original test scenarios.
"""

import pytest
from pathlib import Path
from bs4 import BeautifulSoup

# Correctly import the standalone function to be tested
from src.utils.context_extractor import get_task_context

# --- Fixture to Load and Parse the Complex HTML Data ---


@pytest.fixture(scope="module")
def soup():
    """
    Loads and parses the real, complex Confluence page HTML from an external file.
    The scope is 'module' so this only happens once per test run for efficiency.
    """
    path = Path(__file__).parent / "test_data" / "real_confluence_page.html"
    with open(path, "r", encoding="utf-8") as f:
        html_content = f.read()
    # It's important to use 'html.parser' for consistency with the application
    return BeautifulSoup(html_content, "html.parser")


# --- Helper Function to find tasks ---


def _get_task_element_by_id(soup: BeautifulSoup, task_id: str):
    """Finds a specific <ac:task> element by its <ac:task-id>."""
    task_id_tag = soup.find("ac:task-id", string=task_id)
    if not task_id_tag:
        pytest.fail(
            f"Test setup failed: Could not find task with ID {task_id} in the test HTML."
        )
    return task_id_tag.find_parent("ac:task")


def test_task_preceded_by_jira_macro(soup):
    """CONTEXT PRIORITY 1: The preceding element is a Jira macro."""
    task_element = _get_task_element_by_id(soup, "38")
    context = get_task_context(task_element)
    assert context == "JIRA_KEY_CONTEXT::SFSEA-1524"


def test_task_preceded_by_paragraph(soup):
    """CONTEXT PRIORITY 4: A standard paragraph precedes the task list."""
    task_element = _get_task_element_by_id(soup, "32")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph"


def test_task_nested_in_bullet_point(soup):
    """CONTEXT PRIORITY 2: The task's direct parent is a list item `<li>`."""
    task_element = _get_task_element_by_id(soup, "10")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph in the bullet point"


def test_task_nested_in_numbered_list(soup):
    """CONTEXT PRIORITY 2: The task's direct parent is a numbered list item `<li>`."""
    task_element = _get_task_element_by_id(soup, "11")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph in the numbering point"


def test_task_nested_in_another_task(soup):
    """CONTEXT PRIORITY 2: The task's direct parent is another `<ac:task>`."""
    task_element = _get_task_element_by_id(soup, "20")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph which is also a task"


def test_task_doubly_nested(soup):
    """CONTEXT PRIORITY 2: A task nested two levels deep gets context from its direct parent task."""
    task_element = _get_task_element_by_id(soup, "35")
    context = get_task_context(task_element)
    assert context == "Task under task"


def test_task_inside_table_cell(soup):
    """CONTEXT PRIORITY 3: The task is in a table, so the context is the entire row."""
    task_element = _get_task_element_by_id(soup, "12")
    context = get_task_context(task_element)
    expected_context = (
        "| Details | Task |\n"
        "| This is the context in the same row | Preceding paragraph inside table |"
    )
    assert context == expected_context


def test_sibling_task_inside_table(soup):
    """CONTEXT PRIORITY 3: A sibling task in the same table cell gets the same row context."""
    task_element = _get_task_element_by_id(soup, "40")
    context = get_task_context(task_element)
    expected_context = (
        "| Details | Task |\n"
        "| This is the context in the same row | Preceding paragraph inside table |"
    )
    assert context == expected_context


def test_nested_task_in_table(soup):
    """CONTEXT PRIORITY 2: A nested task in a table gets its parent task's body as context."""
    task_element = _get_task_element_by_id(soup, "23")
    context = get_task_context(task_element)
    assert context == "task 1 in the table"


def test_grandchild_task_in_table(soup):
    """CONTEXT PRIORITY 2: A grandchild task in a table gets its direct parent's body as context."""
    task_element = _get_task_element_by_id(soup, "36")
    context = get_task_context(task_element)
    assert context == "children of task 1 in table"


def test_first_task_in_a_list(soup):
    """CONTEXT PRIORITY 4: The first task in a list is preceded by a paragraph."""
    task_element = _get_task_element_by_id(soup, "14")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph before a list of task"


def test_subsequent_task_in_a_list(soup):
    """CONTEXT PRIORITY 4: A subsequent task in the same list gets the same preceding paragraph."""
    task_element = _get_task_element_by_id(soup, "15")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph before a list of task"


def test_nested_task_under_bullet_point(soup):
    """CONTEXT PRIORITY 2: A grandchild task gets its direct parent task's body."""
    task_element = _get_task_element_by_id(soup, "33")
    context = get_task_context(task_element)
    assert context == "Task under bullet point"


def test_nested_task_under_numbering(soup):
    """CONTEXT PRIORITY 2: A grandchild task gets its direct parent task's body."""
    task_element = _get_task_element_by_id(soup, "34")
    context = get_task_context(task_element)
    assert context == "Task under numbering"


def test_nested_task_in_list(soup):
    """CONTEXT PRIORITY 2: A nested task gets its parent task's body."""
    task_element = _get_task_element_by_id(soup, "24")
    context = get_task_context(task_element)
    assert context == "task 1 in a list"


def test_task_with_empty_body(soup):
    """Ensure a task with an empty body doesn't cause an error and gets preceding context."""
    task_element = _get_task_element_by_id(soup, "16")
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph before a list of task"


def test_handles_none_input():
    """Ensure the function handles None input gracefully."""
    # The function expects a BeautifulSoup object, but we test the edge case of None.
    assert get_task_context(None) == ""


def test_task_with_no_preceding_context(soup):
    """Test a task with no preceding context (should return empty string)."""
    # Create a minimal soup with a task and no context
    html = (
        "<ac:task><ac:task-id>999</ac:task-id><ac:task-body></ac:task-body></ac:task>"
    )
    bs = BeautifulSoup(html, "html.parser")
    task_element = bs.find("ac:task")
    context = get_task_context(task_element)
    assert context == ""


def test_task_with_multiple_parents():
    """Test a task with multiple parent elements."""
    html = """
    <li>
        <ac:task>
            <ac:task-id>multi</ac:task-id>
            <ac:task-body>Multi Parent Task</ac:task-body>
        </ac:task>
    </li>
    """
    bs = BeautifulSoup(html, "html.parser")
    task_element = bs.find("ac:task")
    context = get_task_context(task_element)
    assert context == "Multi Parent Task"


def test_get_task_context_malformed_html():
    """Test get_task_context with malformed HTML input."""
    html = "<ac:task><ac:task-id></ac:task>"
    bs = BeautifulSoup(html, "html.parser")
    task_element = bs.find("ac:task")
    context = get_task_context(task_element)
    assert isinstance(context, str)
