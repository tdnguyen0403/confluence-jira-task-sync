import logging
import uuid
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Tuple
import warnings

from atlassian import Confluence, Jira
import requests

from src.config import config
from src.interfaces.api_service_interface import ApiServiceInterface
from src.services.confluence_service import ConfluenceService
from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.safe_jira_api import SafeJiraApi
from src.utils.logging_config import setup_logging

warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)


class TestDataGenerator:
    """Generates a Confluence test page structure using the unified service interface."""

    def __init__(self, confluence_service: ApiServiceInterface):
        self.confluence = confluence_service
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.all_created_pages: List[Dict[str, Any]] = []
        self.assignee_userkey: Optional[str] = None
        self.task_counter = 0

    def _initialize_assignee(self, username: Optional[str]):
        """Resolves the user key via the service interface."""
        if not username:
            logging.warning("No assignee username provided; tasks will be unassigned.")
            return
        logging.info(f"Attempting to resolve userkey for username: '{username}'...")
        user_details = self.confluence.get_user_details_by_username(username=username)
        if user_details and "userKey" in user_details:
            self.assignee_userkey = user_details["userKey"]
            logging.info(f"Successfully resolved userkey '{self.assignee_userkey}'.")
        else:
            logging.error(f"Could not find userkey for username '{username}'.")
    
    def run(self, base_parent_id: str, wp_keys: List[str], max_depth: int, tasks_per_page: int):
        """Main method to generate the entire test tree."""
        setup_logging("logs_generator", "confluence_generator_run")
        logging.info(f"\n--- Initiating Test Tree Generation under Parent ID: {base_parent_id} ---")
        
        if not wp_keys:
            logging.error("ERROR: Must provide at least one Work Package key.")
            return

        self._initialize_assignee(config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS)
        
        main_page_id = self._create_page(
            parent_id=base_parent_id,
            title=f"Gen {self.timestamp} - Main Test Page Root",
            wp_key=wp_keys[0],
            tasks_per_page=tasks_per_page
        )

        if not main_page_id:
            logging.error("Failed to create the main test page. Aborting.")
            return

        logging.info(f"\n--- Generating sub-levels under '{self.all_created_pages[0]['title']}' ---")
        self._generate_tree_recursive(
            parent_id=main_page_id,
            wp_keys=wp_keys,
            current_depth=1,
            max_depth=max_depth,
            tasks_per_page=tasks_per_page,
            wp_index=1
        )
        self._print_summary()

    def _generate_tree_recursive(self, parent_id: str, wp_keys: List[str], current_depth: int, max_depth: int, tasks_per_page: int, wp_index: int):
        """Recursively generates diverse pages under a given parent."""
        if current_depth > max_depth:
            return
            
        page_title = f"Gen {self.timestamp} - L{current_depth}"
        current_wp_key = wp_keys[wp_index % len(wp_keys)]
        
        new_page_id = self._create_page(
            parent_id=parent_id,
            title=page_title,
            wp_key=current_wp_key,
            tasks_per_page=tasks_per_page
        )
        
        if new_page_id:
            self._generate_tree_recursive(
                parent_id=new_page_id,
                wp_keys=wp_keys,
                current_depth=current_depth + 1,
                max_depth=max_depth,
                tasks_per_page=tasks_per_page,
                wp_index=wp_index + 1
            )

    def _create_page(self, parent_id: str, title: str, wp_key: str, tasks_per_page: int) -> Optional[str]:
        """Creates a single Confluence page with a specified number of tasks."""
        tasks = [self._generate_task_html(f"Task {i+1} on page {title}") for i in range(tasks_per_page)]
        content_html = self._create_page_body(
            title=title,
            description=f"This page contains Work Package: {wp_key}.",
            main_content_html=self._wrap_in_task_list(tasks),
            jira_macro_html=self._generate_jira_macro_html(wp_key)
        )
        
        page = self.confluence.create_page(
            space=config.CONFLUENCE_SPACE_KEY,
            parent_id=parent_id,
            title=title,
            body=content_html,
            representation="storage"
        )
        
        if page and page.get('id'):
            logging.info(f"Created page \"{config.CONFLUENCE_SPACE_KEY}\" -> \"{title}\"")
            self.all_created_pages.append({
                "id": page['id'], "url": page.get('_links', {}).get('webui'), "title": title, "wp_on_page": wp_key
            })
            return page['id']
        return None

    def _generate_diverse_content(self, task_counter: int, index: int) -> Tuple[str, int]:
        """Creates different sets of content based on an index to ensure test variety."""
        content_blocks = []
        if index == 0:
            tasks = [
                self._generate_task_html(task_counter, "Std Incomplete", due_date=date.today() + timedelta(days=1)),
                self._generate_task_html(task_counter + 1, "Std Complete", status="complete"),
                self._generate_task_html(task_counter + 2, "Std Incomplete Due Today", due_date=date.today()),
            ]
            content_blocks.append(self._wrap_in_task_list(tasks))
            panel_task = self._generate_task_html(task_counter + 3, "Task in Info Panel", due_date=date.today() + timedelta(weeks=1))
            content_blocks.append(self._generate_panel_html("info", "Informational Tasks", self._wrap_in_task_list([panel_task])))
            task_counter += 4
        else:
            table_task = self._generate_task_html(task_counter, "Task in Table Cell")
            content_blocks.append(self._generate_table_html([["Task in Header", "Status"], [table_task, "Open"]]))
            
            layout_task1 = self._generate_task_html(task_counter + 1, "Task in Layout Column 1")
            layout_task2 = self._generate_task_html(task_counter + 2, "Task in Layout Column 2")
            content_blocks.append(self._generate_layout_html([self._wrap_in_task_list([layout_task1]), self._wrap_in_task_list([layout_task2])]))
            ignored_task = self._generate_task_html(task_counter + 3, "Ignored Task (in excerpt)")
            content_blocks.append(f'<ac:structured-macro ac:name="excerpt"><ac:rich-text-body>{self._wrap_in_task_list([ignored_task])}</ac:rich-text-body></ac:structured-macro>')
            task_counter += 4
            
        return "".join(content_blocks), task_counter

    def _print_summary(self):
        """Prints a final summary of all created pages to the console."""
        logging.info("\n--- Final Confluence Test Tree Generation Summary ---")
        logging.info(f"Total {len(self.all_created_pages)} pages generated.")
        for page in self.all_created_pages:
            wp_status = f"(WP: {page['wp_on_page']})" if page.get("wp_on_page") else "(No WP)"
            url = page.get('url', 'URL not available')
            logging.info(f"- {page['title']} {wp_status}: {url}")
        if self.all_created_pages:
            main_url = self.all_created_pages[0].get('url', 'N/A')
            logging.info(f"\nTo test, add the Main Test Page URL to input.xlsx: {main_url}")

    def _generate_jira_macro_html(self, jira_key: str) -> str:
        """Generates the Confluence storage format for a Jira macro."""
        return f"""<p><ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
            <ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>
            <ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>
            <ac:parameter ac:name="key">{jira_key}</ac:parameter>
        </ac:structured-macro></p>"""

    def _generate_task_html(self, summary: str, status: str = "incomplete", due_date: Optional[date] = None) -> str:
        """Generates the Confluence storage format for a single task item."""
        self.task_counter += 1
        assignee_html = f'<ri:user ri:userkey="{self.assignee_userkey}"/>' if self.assignee_userkey else ""
        date_html = f'<time datetime="{due_date.strftime("%Y-%m-%d")}"/>' if due_date else ""
        task_id = f"task-{uuid.uuid4().hex[:4]}-{self.task_counter}"
        return f"""<ac:task><ac:task-id>{task_id}</ac:task-id>
            <ac:task-status>{status}</ac:task-status><ac:task-body><span>{summary} {assignee_html}{date_html}</span></ac:task-body></ac:task>"""


    def _wrap_in_task_list(self, tasks: List[str]) -> str:
        return f"<ac:task-list>{''.join(tasks)}</ac:task-list>"

    def _generate_panel_html(self, panel_type: str, title: str, content: str) -> str:
        return f"""<ac:structured-macro ac:name="{panel_type}"><ac:parameter ac:name="title">{title}</ac:parameter><ac:rich-text-body>{content}</ac:rich-text-body></ac:structured-macro>"""

    def _generate_layout_html(self, sections: List[str]) -> str:
        layout_cells = ''.join([f'<ac:layout-cell>{s}</ac:layout-cell>' for s in sections])
        return f"<ac:layout><ac:layout-section ac:type='two_equal'>{layout_cells}</ac:layout-section></ac:layout>"

    def _generate_table_html(self, rows: List[List[str]]) -> str:
        table_rows = ''.join(['<tr>' + ''.join([f'<td><p>{cell}</p></td>' for cell in r]) + '</tr>' for r in rows])
        return f"<table><tbody>{table_rows}</tbody></table>"

    def _create_page_body(self, **kwargs: Any) -> str:
        return f"""<h1>{kwargs['title']}</h1><p>{kwargs['description']}</p>{kwargs.get('jira_macro_html', '')}{kwargs.get('main_content_html', '')}"""

if __name__ == "__main__":

    if config.BASE_PARENT_CONFLUENCE_PAGE_ID == "YOUR_BASE_PARENT_PAGE_ID_HERE":
        logging.error("Please update BASE_PARENT_CONFLUENCE_PAGE_ID in config.py")
    else:
        # Use new config variables
        wp_keys_to_use = config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE[:config.DEFAULT_NUM_WORK_PACKAGES]
        # 1. Initialize raw clients
        jira_client = Jira(url=config.JIRA_URL, token=config.JIRA_API_TOKEN, cloud=False, verify_ssl=False)
        confluence_client = Confluence(url=config.CONFLUENCE_URL, token=config.CONFLUENCE_API_TOKEN, cloud=False, verify_ssl=False)
        
        # 2. Instantiate the low-level API handlers
        safe_jira_api = SafeJiraApi(jira_client)
        safe_confluence_api = SafeConfluenceApi(confluence_client)
        
        # 3. Instantiate the high-level service implementation
        confluence_service = ConfluenceService(safe_confluence_api)

        # 4. Inject the service into the generator
        generator = TestDataGenerator(confluence_service)
        generator.run(
            base_parent_id=config.BASE_PARENT_CONFLUENCE_PAGE_ID,
            wp_keys=wp_keys_to_use,
            max_depth=config.DEFAULT_MAX_DEPTH,
            tasks_per_page=config.DEFAULT_TASKS_PER_PAGE
        )
