import json
from bs4 import BeautifulSoup
from src.utils.context_extractor import get_task_context

# --- Test Data ---
CONFLUENCE_PAGE_JSON = """
{
    "id": "441386294",
    "type": "page",
    "status": "current",
    "title": "Gen 20250628_121411 - L1",
    "version": { "number": 19 },
    "body": {
        "storage": {
            "value": "<h1>Gen 20250628_121411 - L1</h1><p>This page contains Work Package: SFSEA-1258.</p><p><ac:structured-macro ac:name=\\"jira\\" ac:schema-version=\\"1\\" ac:macro-id=\\"6af3b954-a958-4114-8785-3730ba43f1e9\\"><ac:parameter ac:name=\\"server\\">P+F Jira</ac:parameter><ac:parameter ac:name=\\"serverId\\">a9986ca6-387c-3b09-9a85-450e12a1cf94</ac:parameter><ac:parameter ac:name=\\"key\\">SFSEA-1258</ac:parameter></ac:structured-macro></p><p>This is the preceding paragraph</p><ac:task-list>\\n<ac:task>\\n<ac:task-id>9</ac:task-id>\\n<ac:task-uuid>34916e19-b99c-4a5a-aecf-07f9edef29d1</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body>Task under paragraph</ac:task-body>\\n</ac:task>\\n</ac:task-list><p><br /></p><ul><li data-uuid=\\"cba9be4b-f3dd-4b08-9937-ee343cfeaa5d\\">This is the preceding paragraph in the bullet point<br /><ac:task-list>\\n<ac:task>\\n<ac:task-id>10</ac:task-id>\\n<ac:task-uuid>74ac264b-bc79-4ee4-baea-a387729815ef</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body>Task under bullet point</ac:task-body>\\n</ac:task>\\n</ac:task-list></li></ul><p><br /></p><ol><li data-uuid=\\"1147f487-c568-4673-8c57-f766cfe0c597\\">This is the preceding paragraph in the numbering point<br /><ac:task-list>\\n<ac:task>\\n<ac:task-id>11</ac:task-id>\\n<ac:task-uuid>a4f982ea-3662-441b-8647-466b0798862c</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">Task under numbering</span></ac:task-body>\\n</ac:task>\\n</ac:task-list></li></ol><p><br /></p><ac:task-list>\\n<ac:task>\\n<ac:task-id>19</ac:task-id>\\n<ac:task-uuid>652de307-3c35-431a-a72f-715b996d49e9</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body>This is the preceding paragraph which is also a task<br /><ac:task-list>\\n<ac:task>\\n<ac:task-id>20</ac:task-id>\\n<ac:task-uuid>fe4f576e-35fc-4946-a781-590e985d861d</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">Task under task</span></ac:task-body>\\n</ac:task>\\n</ac:task-list></ac:task-body>\\n</ac:task>\\n</ac:task-list><p><br /></p><table class=\\"wrapped\\"><colgroup><col /><col /></colgroup><tbody><tr><th scope=\\"col\\">Details</th><th scope=\\"col\\">Task</th></tr><tr><td>This is the context in the same row</td><td><div class=\\"content-wrapper\\"><p><span class=\\"placeholder-inline-tasks\\">Preceding paragraph inside table</span></p><ac:task-list>\\n<ac:task>\\n<ac:task-id>12</ac:task-id>\\n<ac:task-uuid>c6d59889-ea99-4e64-a984-640ade967163</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">task 1 in the table</span><ac:task-list>\\n<ac:task>\\n<ac:task-id>23</ac:task-id>\\n<ac:task-uuid>f2486449-aaf6-4868-95f8-ede4f4638c10</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">children of task 1 in table</span></ac:task-body>\\n</ac:task>\\n</ac:task-list></ac:task-body>\\n</ac:task>\\n<ac:task>\\n<ac:task-id>13</ac:task-id>\\n<ac:task-uuid>4c7f5323-394f-4481-866e-7a658e3f03c2</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">task 2 in the table</span></ac:task-body>\\n</ac:task>\\n</ac:task-list><p><br /></p></div></td></tr></tbody></table><p><br /></p><p>This is the preceding paragraph before a list of task</p><ac:task-list>\\n<ac:task>\\n<ac:task-id>14</ac:task-id>\\n<ac:task-uuid>101c32aa-0db3-4bac-b6f9-08095efda87b</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">task 1</span><ac:task-list>\\n<ac:task>\\n<ac:task-id>24</ac:task-id>\\n<ac:task-uuid>da0d2a5d-5955-4423-bc83-b538b531a59d</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">children of task 1</span></ac:task-body>\\n</ac:task>\\n</ac:task-list></ac:task-body>\\n</ac:task>\\n<ac:task>\\n<ac:task-id>15</ac:task-id>\\n<ac:task-uuid>54fcaf02-9ba1-4f4b-adb1-74064782bc42</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">task 2</span></ac:task-body>\\n</ac:task>\\n<ac:task>\\n<ac:task-id>16</ac:task-id>\\n<ac:task-uuid>c97ed871-0873-40ed-9961-b58b74dcb8fa</ac:task-uuid>\\n<ac:task-status>incomplete</ac:task-status>\\n<ac:task-body><span class=\\"placeholder-inline-tasks\\">task 3</span></ac:task-body>\\n</ac:task>\\n</ac:task-list><p><br /></p>",
            "representation": "storage"
        }
    }
}
"""

def run_test_on_task(soup, task_id, test_name, expected_context):
    print(f"--- Running Test: {test_name} (Task ID: {task_id}) ---")
    task_element = soup.find("ac:task-id", string=str(task_id))
    if task_element:
        parent_task = task_element.find_parent("ac:task")
        extracted_context = get_task_context(parent_task)
        print(f"Expected Context: '{expected_context}'")
        print(f"Actual Extracted Context: '{extracted_context}'")
        if extracted_context.strip() == expected_context.strip():
            print("\nResult: PASSED")
        else:
            print(f"\nResult: FAILED - Context did not match.")
            assert extracted_context.strip() == expected_context.strip(), f"Test failed for Task ID {task_id}"
    else:
        print(f"Result: FAILED - Could not find task with ID {task_id}")
        assert False, f"Could not find task with ID {task_id}"
    print("-" * (len(test_name) + 26) + "\n")

if __name__ == "__main__":
    data = json.loads(CONFLUENCE_PAGE_JSON)
    html_content = data['body']['storage']['value']
    soup = BeautifulSoup(html_content, 'html.parser')

    print("Running final, complete test suite...\n")

    table_context = "| Details | Task |\n| --- | --- |\n| This is the context in the same row | Preceding paragraph inside table |"
    main_list_context = "This is the preceding paragraph before a list of task"

    run_test_on_task(soup, 9, "Task under a paragraph", "This is the preceding paragraph")
    run_test_on_task(soup, 10, "Task in a bullet point", "This is the preceding paragraph in the bullet point")
    run_test_on_task(soup, 11, "Task in a numbered list", "This is the preceding paragraph in the numbering point")
    run_test_on_task(soup, 12, "Task inside a table", table_context)
    run_test_on_task(soup, 13, "Sibling task in table", table_context)
    run_test_on_task(soup, 14, "First task in a list", main_list_context)
    run_test_on_task(soup, 15, "Second task in a list", main_list_context)
    run_test_on_task(soup, 16, "Third task in a list", main_list_context)
    run_test_on_task(soup, 19, "Top-level task with robust fallback", "This is the preceding paragraph in the numbering point")
    run_test_on_task(soup, 20, "Nested under a top-level task", "This is the preceding paragraph which is also a task")
    run_test_on_task(soup, 23, "Nested task in table", table_context)
    run_test_on_task(soup, 24, "Nested under a list task", "task 1")
    
    print("All tests passed successfully!")