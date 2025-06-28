from bs4 import BeautifulSoup, NavigableString

def get_task_context(task_element):
    """
    Extracts the clean, human-readable context around a task element
    using a robust, multi-tiered approach.
    """
    
    # Priority 1: Context from a direct container (a list item or another task).
    parent_container = task_element.find_parent(["li", "ac:task"])
    if parent_container:
        container_clone = BeautifulSoup(str(parent_container), 'html.parser')
        # We must remove the nested task lists to get clean context.
        for task_list in container_clone.find_all("ac:task-list"):
            task_list.decompose()
        # If the parent was a task, we only want the body's text.
        if container_clone.find("ac:task-body"):
            return container_clone.find("ac:task-body").get_text(strip=True)
        else:
            return container_clone.get_text(strip=True)
            
    # Priority 2: Table context. This is the most specific.
    parent_row = task_element.find_parent("tr")
    if parent_row:
        parent_table = parent_row.find_parent("table")
        if parent_table:
            headers = [th.get_text(strip=True) for th in parent_table.find_all("th")]
            row_data = []
            task_cell = task_element.find_parent(['td', 'th'])
            for cell in parent_row.find_all(['td', 'th']):
                if cell == task_cell:
                    cell_clone = BeautifulSoup(str(cell), 'html.parser')
                    for task_list in cell_clone.find_all("ac:task-list"):
                        task_list.decompose()
                    row_data.append(cell_clone.get_text(strip=True))
                else:
                    row_data.append(cell.get_text(strip=True))
            context = ""
            if headers:
                context += "| " + " | ".join(headers) + " |\n"
                #context += "| " + " | ".join(["---"] * len(headers)) + " |\n"
            context += "| " + " | ".join(row_data) + " |"
            return context

    # Priority 3: The Definitive Fallback for Top-Level Tasks.
    # This finds the nearest preceding text block regardless of structure.
    parent_task_list = task_element.find_parent("ac:task-list")
    if parent_task_list:
        # Get ALL preceding tags.
        all_previous_tags = parent_task_list.find_all_previous()
        for tag in all_previous_tags:
            # Look for a valid context tag (p, h1-h6, or li).
            if tag.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]:
                # If it's a list item, we must clean it of its own tasks.
                if tag.name == 'li':
                    li_clone = BeautifulSoup(str(tag), 'html.parser')
                    for tl in li_clone.find_all('ac:task-list'):
                        tl.decompose()
                    context_text = li_clone.get_text(strip=True)
                else:
                    context_text = tag.get_text(strip=True)
                
                # The first one we find with actual text is our answer.
                if context_text:
                    return context_text

    return ""