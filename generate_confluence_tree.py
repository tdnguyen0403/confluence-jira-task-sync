# generate_confluence_tree.py - Refactored to use the SafeConfluenceService and with full functionality restored.

import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Tuple

from atlassian import Confluence
import warnings
import requests

import config
from safe_api import SafeConfluenceService

# --- Suppress SSL Warnings ---
urllib3 = requests.packages.urllib3
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)


class TestDataGenerator:
    """Generates a complex Confluence page structure using the safe service."""

    def __init__(self, safe_confluence: SafeConfluenceService, space_key: str, assignee_username: Optional[str]):
        self.confluence = safe_confluence
        self.space_key = space_key
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.all_created_pages: List[Dict[str, Any]] = []
        
        assignee_details = self.confluence.get_user_details_by_username(assignee_username) if assignee_username else None
        self.assignee_userkey = assignee_details.get("userKey") if assignee_details else None


    def run(self, base_parent_id: str, wp_keys: List[str], max_depth: int = 2):
        """Main method to generate the entire test tree."""
        logging.info(f"\n--- Initiating Test Tree Generation under Parent ID: {base_parent_id} ---")
        if not wp_keys:
            logging.error("ERROR: Must provide at least one Work Package key.")
            return

        main_page_id, task_counter = self._create_main_test_page(base_parent_id, wp_keys[0])

        if not main_page_id:
            logging.error("Failed to create the main test page. Aborting.")
            return

        logging.info(f"\n--- Generating sub-levels under '{self.all_created_pages[0]['title']}' ---")
        self._generate_tree_recursive(
            parent_id=main_page_id,
            wp_keys=wp_keys,
            current_depth=1,
            max_depth=max_depth,
            task_counter=task_counter,
            wp_index=1,
            path_prefix=""
        )

        self._print_summary()

    def _create_main_test_page(self, base_parent_id: str, wp_key: str) -> Tuple[Optional[str], int]:
        """Creates the top-level page for the generated test tree."""
        title = f"Gen {self.timestamp} - Main Test Page Root"
        task_counter = 0
        tasks = [
            self._generate_task_html(task_counter, "Main Page Task A (Incomplete)", due_date=datetime.now().date() + timedelta(days=5)),
            self._generate_task_html(task_counter + 1, "Main Page Task B (Complete)", status="complete"),
        ]
        task_counter += 2

        content_html = self._create_page_body(
            title=title,
            description=f"This page has Work Package: {wp_key}.",
            main_content_html=self._wrap_in_task_list(tasks),
            jira_macro_html=self._generate_jira_macro_html(wp_key),
        )

        page = self.confluence.create_page(
            space=self.space_key, parent_id=base_parent_id, title=title, body=content_html, representation="storage"
        )
        if page and page.get('id'):
            self.all_created_pages.append({
                "id": page['id'], "url": page.get('_links', {}).get('webui'), "title": title, "wp_on_page": wp_key
            })
            return page['id'], task_counter
        return None, task_counter
        
    def _generate_tree_recursive(self, parent_id, wp_keys, current_depth, max_depth, task_counter, wp_index, path_prefix):
        if current_depth > max_depth:
            return task_counter, wp_index

        for i in range(2): # Create 2 diverse pages at each level
            page_identifier = f"{path_prefix}{current_depth}.{i+1}"
            page_title = f"Gen {self.timestamp} - L{page_identifier}"
            
            # Cycle through WP keys
            current_wp_key = wp_keys[wp_index % len(wp_keys)]
            wp_index += 1

            page_content, task_counter = self._generate_diverse_content(task_counter, i)
            
            content_html = self._create_page_body(
                title=page_title,
                description=f"This page specifically has Work Package: {current_wp_key}.",
                main_content_html=page_content,
                jira_macro_html=self._generate_jira_macro_html(current_wp_key)
            )

            new_page = self.confluence.create_page(
                space=self.space_key, parent_id=parent_id, title=page_title, body=content_html, representation="storage"
            )

            if new_page and new_page.get('id'):
                self.all_created_pages.append({
                    "id": new_page['id'], "url": new_page.get('_links', {}).get('webui'), "title": page_title, "wp_on_page": current_wp_key
                })
                # Recurse deeper
                task_counter, wp_index = self._generate_tree_recursive(
                    parent_id=new_page['id'], wp_keys=wp_keys, current_depth=current_depth + 1,
                    max_depth=max_depth, task_counter=task_counter, wp_index=wp_index, path_prefix=f"{page_identifier}-"
                )
        return task_counter, wp_index

    def _generate_diverse_content(self, task_counter: int, index: int) -> Tuple[str, int]:
        """Creates different content blocks based on an index to ensure variety."""
        content_blocks = []
        if index == 0:  # Page type 1: Standard tasks and a panel
            tasks = [
                self._generate_task_html(task_counter, "Std Incomplete", due_date=date.today() + timedelta(days=1)),
                self._generate_task_html(task_counter + 1, "Std Complete", status="complete"),
                self._generate_task_html(task_counter + 2, "Std Incomplete Due Today", due_date=date.today()),
            ]
            content_blocks.append(self._wrap_in_task_list(tasks))
            panel_task = self._generate_task_html(task_counter + 3, "Task in Info Panel", due_date=date.today() + timedelta(weeks=1))
            content_blocks.append(self._generate_panel_html("info", "Informational Tasks", self._wrap_in_task_list([panel_task])))
            task_counter += 4
        else:  # Page type 2: Table, layout, and ignored macros
            table_task = self._generate_task_html(task_counter, "Task in Table Cell")
            content_blocks.append(self._generate_table_html([[table_task, "Some other cell"]]))
            
            layout_task1 = self._generate_task_html(task_counter + 1, "Task in Layout Column 1")
            layout_task2 = self._generate_task_html(task_counter + 2, "Task in Layout Column 2")
            content_blocks.append(self._generate_layout_html([self._wrap_in_task_list([layout_task1]), self._wrap_in_task_list([layout_task2])]))

            # Add an ignored macro for testing
            ignored_task = self._generate_task_html(task_counter + 3, "Ignored Task (in excerpt)")
            content_blocks.append(f'<ac:structured-macro ac:name="excerpt-include"><ac:rich-text-body>{self._wrap_in_task_list([ignored_task])}</ac:rich-text-body></ac:structured-macro>')
            task_counter += 4
            
        return "".join(content_blocks), task_counter

    def _print_summary(self):
        """Prints a final summary of all created pages."""
        logging.info("\n--- Final Confluence Test Tree Generation Summary ---")
        logging.info(f"Total {len(self.all_created_pages)} pages generated.")
        for page in self.all_created_pages:
            wp_status = f"(WP: {page['wp_on_page']})" if page.get("wp_on_page") else "(No WP)"
            url = page.get('url', 'URL not available')
            logging.info(f"- {page['title']} {wp_status}: {url}")
        if self.all_created_pages:
            main_url = self.all_created_pages[0].get('url', 'N/A')
            logging.info(f"\nTo test, add the Main Test Page URL to input.xlsx: {main_url}")
    
    # --- HTML Generation Helpers ---
    def _generate_jira_macro_html(self, jira_key: str) -> str:
        return f"""<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
            <ac:parameter ac:name="key">{jira_key}</ac:parameter></ac:structured-macro>"""

    def _generate_task_html(self, task_id_suffix: int, summary: str, status: str = "incomplete", due_date=None) -> str:
        assignee_html = f'<ri:user ri:userkey="{self.assignee_userkey}"/>' if self.assignee_userkey else ""
        date_html = f'<time datetime="{due_date.strftime("%Y-%m-%d")}"/>' if due_date else ""
        return f"""<ac:task><ac:task-id>task-{uuid.uuid4().hex[:4]}-{task_id_suffix}</ac:task-id>
            <ac:task-status>{status}</ac:task-status><ac:task-body>{summary} {assignee_html}{date_html}</ac:task-body></ac:task>"""

    def _wrap_in_task_list(self, tasks: List[str]) -> str: return f"<ac:task-list>{''.join(tasks)}</ac:task-list>"
    def _generate_panel_html(self, p_type, title, content): return f"""<ac:structured-macro ac:name="{p_type}"><ac:parameter ac:name="title">{title}</ac:parameter><ac:rich-text-body>{content}</ac:rich-text-body></ac:structured-macro>"""
    def _generate_layout_html(self, sections: List[str]): return f"<ac:layout><ac:layout-section ac:type='two_equal'>{''.join([f'<ac:layout-cell>{s}</ac:layout-cell>' for s in sections])}</ac:layout-section></ac:layout>"
    def _generate_table_html(self, rows: List[List[str]]): return f"<table><tbody>{''.join(['<tr>' + ''.join([f'<td>{c}</td>' for c in r]) + '</tr>' for r in rows])}</tbody></table>"
    def _create_page_body(self, **kwargs) -> str: return f"""<h1>{kwargs['title']}</h1><p>{kwargs['description']}</p>{kwargs.get('jira_macro_html', '')}{kwargs.get('main_content_html', '')}"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if config.BASE_PARENT_CONFLUENCE_PAGE_ID == "YOUR_BASE_PARENT_PAGE_ID_HERE":
        logging.error("Please update BASE_PARENT_CONFLUENCE_PAGE_ID in config.py")
    else:
        confluence_client = Confluence(url=config.CONFLUENCE_URL, token=config.CONFLUENCE_API_TOKEN, cloud=False, verify_ssl=False)
        safe_confluence = SafeConfluenceService(confluence_client)
        generator = TestDataGenerator(safe_confluence, config.CONFLUENCE_SPACE_KEY, config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS)
        generator.run(config.BASE_PARENT_CONFLUENCE_PAGE_ID, config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE)
