"""
Provides a utility function to extract contextual information for a task.

This module contains the `get_task_context` function, which is designed to
find the most relevant surrounding text for a given task element within a
Confluence page's HTML structure. This context is crucial for providing
clear and understandable descriptions when creating Jira issues.
"""

from typing import List

from bs4 import BeautifulSoup, ResultSet, Tag
from bs4.element import NavigableString, PageElement


def get_task_context(task_element: Tag) -> str:
    """
    Extracts the clean, human-readable context around a task element.

    The logic follows this order of priority:

    1.  **Preceding Jira Macro (Highest Priority):** Checks if the item
        immediately preceding the task is a Jira macro. If so, it returns
        a special string containing the Jira issue's KEY.
    2.  **Direct Container:** Looks for the immediate parent `<li>` or
        enclosing `<ac:task>` element.
    3.  **Table Row:** If the task is inside a table, it reconstructs the
        entire row in a markdown-like format.
    4.  **Preceding Text Block:** As a fallback, it searches backwards to
        find the nearest preceding paragraph, heading, or list item.
    """
    if not task_element:
        return ""
    # --- PRIORITY 1: Check for a preceding Jira Macro (NEW ROBUST LOGIC) ---
    parent_task_list = task_element.find_parent("ac:task-list")
    if parent_task_list:
        prev_sibling = parent_task_list.find_previous_sibling()
        if isinstance(prev_sibling, Tag):
            jira_macro = prev_sibling.find("ac:structured-macro", {"ac:name": "jira"})
            if isinstance(jira_macro, Tag):
                key_param = jira_macro.find("ac:parameter", {"ac:name": "key"})
                if key_param:
                    jira_key = key_param.get_text(strip=True)
                    return f"JIRA_KEY_CONTEXT::{jira_key}"

    # Priority 2: Context from a direct container (a list item or another task).
    parent_container = task_element.find_parent(["li", "ac:task"])
    if parent_container:
        container_soup: BeautifulSoup = BeautifulSoup(
            str(parent_container), "html.parser"
        )
        task_lists_raw: ResultSet[PageElement | Tag | NavigableString] = (
            container_soup.find_all("ac:task-list")
        )
        task_lists: List[Tag] = [t for t in task_lists_raw if isinstance(t, Tag)]
        for task_list in task_lists:
            task_list.decompose()

        task_body = container_soup.find("ac:task-body")
        if task_body:
            return task_body.get_text(strip=True)
        else:
            return container_soup.get_text(strip=True)

    # Priority 3: Table context. This provides highly specific context.
    parent_row = task_element.find_parent("tr")
    if isinstance(parent_row, Tag):  # Ensure parent_row is a Tag
        parent_table = parent_row.find_parent("table")
        if parent_table:
            headers = [th.get_text(strip=True) for th in parent_table.find_all("th")]
            row_data: List[str] = []
            task_cell = task_element.find_parent(["td", "th"])

            cells_raw: ResultSet[PageElement | Tag | NavigableString] = (
                parent_row.find_all(["td", "th"])
            )
            cells: List[Tag] = [c for c in cells_raw if isinstance(c, Tag)]
            for cell in cells:
                if cell == task_cell:
                    cell_soup = BeautifulSoup(str(cell), "html.parser")
                    inner_task_lists_raw: ResultSet[
                        PageElement | Tag | NavigableString
                    ] = cell_soup.find_all("ac:task-list")
                    inner_task_lists: List[Tag] = [
                        t for t in inner_task_lists_raw if isinstance(t, Tag)
                    ]
                    for task_list in inner_task_lists:
                        task_list.decompose()
                    row_data.append(cell_soup.get_text(strip=True))
                else:
                    row_data.append(cell.get_text(strip=True))

            context = ""
            if headers:
                context += "| " + " | ".join(headers) + " |\n"
            context += "| " + " | ".join(row_data) + " |"
            return context

    # Priority 4: The definitive fallback for top-level tasks.
    parent_task_list_fallback = task_element.find_parent("ac:task-list")
    if parent_task_list_fallback:
        all_previous_tags_raw = parent_task_list_fallback.find_all_previous()
        all_previous_tags: List[Tag] = [
            t for t in all_previous_tags_raw if isinstance(t, Tag)
        ]
        for tag in all_previous_tags:
            if tag.name in [
                "p",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "li",
            ]:
                if tag.name == "li":
                    li_clone = BeautifulSoup(str(tag), "html.parser")
                    task_lists_in_li_raw: ResultSet[
                        PageElement | Tag | NavigableString
                    ] = li_clone.find_all("ac:task-list")
                    task_lists_in_li: List[Tag] = [
                        tl for tl in task_lists_in_li_raw if isinstance(tl, Tag)
                    ]
                    for tl in task_lists_in_li:
                        tl.decompose()
                    context_text = li_clone.get_text(strip=True)
                else:
                    context_text = tag.get_text(strip=True)

                if context_text:
                    return context_text

    return ""
