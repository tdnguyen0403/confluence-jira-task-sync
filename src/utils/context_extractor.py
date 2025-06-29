"""
Provides a utility function to extract contextual information for a task.

This module contains the `get_task_context` function, which is designed to
find the most relevant surrounding text for a given task element within a
Confluence page's HTML structure. This context is crucial for providing
clear and understandable descriptions when creating Jira issues.
"""

from bs4 import BeautifulSoup


def get_task_context(task_element: BeautifulSoup) -> str:
    """
    Extracts the clean, human-readable context around a task element.

    This function uses a robust, multi-tiered approach to find the most
    relevant context, prioritizing the most immediate and specific sources.
    The logic follows this order:

    1.  **Direct Container:** Looks for the immediate parent `<li>` or
        enclosing `<ac:task>` element. This is the most common context for
        nested tasks.
    2.  **Table Row:** If the task is inside a table, it reconstructs the
        entire row, including headers, in a markdown-like format. This
        provides rich, structured context.
    3.  **Preceding Text Block:** As a fallback for top-level tasks, it
        searches backwards from the task's location to find the nearest
        preceding paragraph (`<p>`), heading (`<h1>-<h6>`), or list item
        (`<li>`) that contains text.

    Args:
        task_element (BeautifulSoup): The BeautifulSoup object representing
                                      the `<ac:task>` element.

    Returns:
        str: The extracted contextual text, or an empty string if no
             suitable context is found.
    """
    # Priority 1: Context from a direct container (a list item or another task).
    # This handles nested tasks effectively.
    parent_container = task_element.find_parent(["li", "ac:task"])
    if parent_container:
        # Clone the container to avoid modifying the original soup object.
        container_clone = BeautifulSoup(str(parent_container), "html.parser")
        # Remove any nested task lists from the clone to get clean context.
        for task_list in container_clone.find_all("ac:task-list"):
            task_list.decompose()
        # If the parent was another task, we only want the text of its body.
        if container_clone.find("ac:task-body"):
            return container_clone.find("ac:task-body").get_text(strip=True)
        else:
            return container_clone.get_text(strip=True)

    # Priority 2: Table context. This provides highly specific context.
    parent_row = task_element.find_parent("tr")
    if parent_row:
        parent_table = parent_row.find_parent("table")
        if parent_table:
            headers = [
                th.get_text(strip=True) for th in parent_table.find_all("th")
            ]
            row_data = []
            task_cell = task_element.find_parent(["td", "th"])

            for cell in parent_row.find_all(["td", "th"]):
                # If this is the cell containing our task, we need to clean it.
                if cell == task_cell:
                    cell_clone = BeautifulSoup(str(cell), "html.parser")
                    for task_list in cell_clone.find_all("ac:task-list"):
                        task_list.decompose()
                    row_data.append(cell_clone.get_text(strip=True))
                else:
                    row_data.append(cell.get_text(strip=True))

            # Format the table context as a markdown-style table row.
            context = ""
            if headers:
                context += "| " + " | ".join(headers) + " |\n"
            context += "| " + " | ".join(row_data) + " |"
            return context

    # Priority 3: The definitive fallback for top-level tasks. This finds the
    # nearest preceding text block regardless of the specific structure.
    parent_task_list = task_element.find_parent("ac:task-list")
    if parent_task_list:
        # Get all preceding tags in the document order.
        all_previous_tags = parent_task_list.find_all_previous()
        for tag in all_previous_tags:
            # Look for a valid context-providing tag (p, h1-h6, or li).
            if tag.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]:
                # If it's a list item, we must clean it of its own tasks.
                if tag.name == "li":
                    li_clone = BeautifulSoup(str(tag), "html.parser")
                    for tl in li_clone.find_all("ac:task-list"):
                        tl.decompose()
                    context_text = li_clone.get_text(strip=True)
                else:
                    context_text = tag.get_text(strip=True)

                # The first preceding tag with actual text is our answer.
                if context_text:
                    return context_text

    return ""
