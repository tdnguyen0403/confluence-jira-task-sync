"""
Tests for the get_task_context utility function using a realistic,
complex HTML document. This file preserves all original test scenarios.
"""

from pathlib import Path
from typing import Optional

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

# Correctly import the standalone function to be tested
from src.utils.context_extractor import get_task_context

# --- Fixture to Load and Parse the Complex HTML Data ---


@pytest.fixture(scope="module")
def soup() -> BeautifulSoup:
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


def _get_task_element_by_id(soup: BeautifulSoup, task_id: str) -> Optional[Tag]:
    """Finds a specific <ac:task> element by its <ac:task-id>."""
    task_id_tag = soup.find("ac:task-id", string=task_id)
    if not task_id_tag:
        pytest.fail(
            "Test setup failed: Could not find task with ID "
            f"{task_id} in the test HTML."
        )
    return task_id_tag.find_parent("ac:task")


def test_task_preceded_by_jira_macro(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 1: The preceding element is a Jira macro."""
    task_element = _get_task_element_by_id(soup, "38")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "JIRA_KEY_CONTEXT::SFSEA-1524"


def test_task_preceded_by_paragraph(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 4: A standard paragraph precedes the task list."""
    task_element = _get_task_element_by_id(soup, "32")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph"


def test_task_nested_in_bullet_point(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: The task's direct parent is a list item `<li>`."""
    task_element = _get_task_element_by_id(soup, "10")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph in the bullet point"


def test_task_nested_in_numbered_list(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: The task's direct parent is a numbered list item `<li>`."""
    task_element = _get_task_element_by_id(soup, "11")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph in the numbering point"


def test_task_nested_in_another_task(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: The task's direct parent is another `<ac:task>`."""
    task_element = _get_task_element_by_id(soup, "20")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph which is also a task"


def test_task_doubly_nested(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: A task nested two levels deep gets context from its direct parent task."""
    task_element = _get_task_element_by_id(soup, "35")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "Task under task"


def test_task_inside_table_cell(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 3: The task is in a table, so the context is the entire row."""
    task_element = _get_task_element_by_id(soup, "12")
    assert task_element is not None
    context = get_task_context(task_element)
    expected_context = (
        "| Details | Task |\n"
        "| This is the context in the same row | Preceding paragraph inside table |"
    )
    assert context == expected_context


def test_sibling_task_inside_table(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 3: A sibling task in the same table cell gets the same row context."""
    task_element = _get_task_element_by_id(soup, "40")
    assert task_element is not None
    context = get_task_context(task_element)
    expected_context = (
        "| Details | Task |\n"
        "| This is the context in the same row | Preceding paragraph inside table |"
    )
    assert context == expected_context


def test_nested_task_in_table(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: A nested task in a table gets its parent task's body as context."""
    task_element = _get_task_element_by_id(soup, "23")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "task 1 in the table"


def test_grandchild_task_in_table(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: A grandchild task in a table gets its direct parent's body as context."""
    task_element = _get_task_element_by_id(soup, "36")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "children of task 1 in table"


def test_first_task_in_a_list(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 4: The first task in a list is preceded by a paragraph."""
    task_element = _get_task_element_by_id(soup, "14")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph before a list of task"


def test_subsequent_task_in_a_list(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 4: A subsequent task in the same list gets the same preceding paragraph."""
    task_element = _get_task_element_by_id(soup, "15")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph before a list of task"


def test_nested_task_under_bullet_point(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: A grandchild task gets its direct parent task's body."""
    task_element = _get_task_element_by_id(soup, "33")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "Task under bullet point"


def test_nested_task_under_numbering(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: A grandchild task gets its direct parent task's body."""
    task_element = _get_task_element_by_id(soup, "34")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "Task under numbering"


def test_nested_task_in_list(soup: BeautifulSoup) -> None:
    """CONTEXT PRIORITY 2: A nested task gets its parent task's body."""
    task_element = _get_task_element_by_id(soup, "24")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "task 1 in a list"


def test_task_with_empty_body(soup: BeautifulSoup) -> None:
    """Ensure a task with an empty body doesn't cause an error and gets preceding context."""
    task_element = _get_task_element_by_id(soup, "16")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "This is the preceding paragraph before a list of task"


def test_handles_none_input() -> None:
    """Ensure the function handles None input gracefully."""
    # This test intentionally violates the type hint to check runtime safety.
    assert get_task_context(None) == ""  # type: ignore[arg-type]


def test_task_with_no_preceding_context(soup: BeautifulSoup) -> None:
    """Test a task with no preceding context (should return empty string)."""
    # Create a minimal soup with a task and no context
    html = (
        "<ac:task><ac:task-id>999</ac:task-id><ac:task-body></ac:task-body></ac:task>"
    )
    bs = BeautifulSoup(html, "html.parser")
    task_element = bs.find("ac:task")
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == ""


def test_task_with_multiple_parents() -> None:
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
    assert task_element is not None
    context = get_task_context(task_element)
    assert context == "Multi Parent Task"


def test_get_task_context_malformed_html() -> None:
    """Test get_task_context with malformed HTML input."""
    html = "<ac:task><ac:task-id></ac:task>"
    bs = BeautifulSoup(html, "html.parser")
    task_element = bs.find("ac:task")
    assert task_element is not None
    context = get_task_context(task_element)
    assert isinstance(context, str)
