import argparse
import asyncio
import logging
import sys
import uuid
import warnings
import urllib3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

import httpx

from src.api.https_helper import HTTPSHelper
from src.api.safe_confluence_api import SafeConfluenceAPI
from src.api.safe_jira_api import SafeJiraAPI
from src.config import config
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business.issue_finder import IssueFinderService
from src.utils.logging_config import endpoint_var, request_id_var, setup_logging

# Suppress insecure request warnings for local/dev environments
warnings.filterwarnings(
    "ignore", category=urllib3.exceptions.InsecureRequestWarning
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def resource_manager() -> AsyncIterator[HTTPSHelper]:
    """
    Manages the lifecycle of resources for the script, similar to FastAPI's lifespan.
    Initializes the HTTPSHelper and its client, and ensures it's closed on exit.
    """
    https_helper = HTTPSHelper(verify_ssl=False)
    # Explicitly create and set the client to prevent the warning.
    # The client will be closed by the helper's close() method.
    https_helper.client = httpx.AsyncClient(verify=False)
    try:
        logger.info("Resources initialized for script execution.")
        yield https_helper
    finally:
        await https_helper.close()
        logger.info("Resources cleaned up successfully.")


class ConfluenceTreeGenerator:
    """
    Generates a hierarchy of Confluence pages with embedded tasks for testing.
    """

    def __init__(
        self,
        confluence_service: ConfluenceService,
        jira_service: JiraService,
        issue_finder: IssueFinderService,
        base_parent_page_id: str,
        confluence_space_key: str,
        assignee_username: str,
        test_work_package_keys: List[str],
        max_depth: int,
        tasks_per_page: int,
    ):
        self.confluence = confluence_service
        self.jira = jira_service
        self.issue_finder = issue_finder
        self.base_parent_page_id = base_parent_page_id
        self.confluence_space_key = confluence_space_key
        self.assignee_username = assignee_username
        self.test_work_package_keys = test_work_package_keys
        self.max_depth = max_depth
        self.tasks_per_page = tasks_per_page
        self.generated_page_ids: List[str] = []
        self.assignee_account_id: Optional[str] = None

    async def _initialize_assignee(self) -> None:
        """Asynchronously fetches and sets the assignee's account ID."""
        logger.info(f"Fetching account ID for assignee: {self.assignee_username}")
        user_details = await self.confluence.get_user_by_username(
            self.assignee_username
        )
        if user_details:
            self.assignee_account_id = user_details.get("accountId")
            logger.info(
                f"Assignee '{self.assignee_username}' account ID: "
                f"{self.assignee_account_id}"
            )
        else:
            logger.warning(
                f"Could not find account ID for assignee: {self.assignee_username}."
            )

    async def generate_page_hierarchy(
        self, parent_page_id: str, current_depth: int = 0
    ) -> List[Dict[str, str]]:
        """Recursively generates a hierarchy of pages and adds tasks asynchronously."""
        if current_depth >= self.max_depth:
            return []

        results: List[Dict[str, str]] = []
        num_children = 1

        for i in range(num_children):
            page_title = (
                f"Test Page (Depth {current_depth}-{i}) "
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            logger.info(f"Creating page: '{page_title}' under parent {parent_page_id}")

            wp_key = self.test_work_package_keys[i % len(self.test_work_package_keys)]
            jira_macro_html = (
                f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1">'
                f'<ac:parameter ac:name="server">'
                f"{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>"
                f'<ac:parameter ac:name="serverId">'
                f"{config.JIRA_MACRO_SERVER_ID}</ac:parameter>"
                f'<ac:parameter ac:name="key">{wp_key}</ac:parameter>'
                f"</ac:structured-macro></p>"
            )

            tasks_html_parts = []
            for t_idx in range(self.tasks_per_page):
                task_summary = (
                    f"Generated Task {t_idx} for {wp_key} "
                    f"({datetime.now().strftime('%H%M%S')})"
                )
                assignee_html = (
                    f'<ac:task-assignee ac:account-id="{self.assignee_account_id}">'
                    f"</ac:task-assignee>"
                    if self.assignee_account_id
                    else ""
                )
                due_date_str = (config.DEFAULT_DUE_DATE_FOR_TREE_GENERATION).strftime(
                    "%Y-%m-%d"
                )
                tasks_html_parts.append(
                    f"<ac:task-list><ac:task>"
                    f"<ac:task-id>{uuid.uuid4().hex[:8]}</ac:task-id>"
                    f"<ac:task-status>incomplete</ac:task-status>"
                    f"<ac:task-body><span>{task_summary} {assignee_html}</span>"
                    f'<time datetime="{due_date_str}"></time>'
                    f"</ac:task-body></ac:task></ac:task-list>"
                )

            page_body = f"{jira_macro_html}\n{''.join(tasks_html_parts)}"
            new_page = await self.confluence.create_page(
                space_key=self.confluence_space_key,
                title=page_title,
                body=page_body,
                parent_id=parent_page_id,
            )

            if new_page:
                new_page_id = new_page["id"]
                new_page_url = new_page["_links"]["webui"]
                self.generated_page_ids.append(new_page_id)
                logger.info(f"Created page '{page_title}' (ID: {new_page_id})")
                results.append({"url": new_page_url, "linked_work_package": wp_key})
                child_results = await self.generate_page_hierarchy(
                    new_page_id, current_depth + 1
                )
                results.extend(child_results)
            else:
                logger.error(f"Failed to create page '{page_title}'.")
        return results

    @staticmethod
    def _parse_args() -> argparse.Namespace:
        """Parses command-line arguments."""
        parser = argparse.ArgumentParser(
            description="Generate a Confluence page hierarchy with tasks for testing."
        )
        parser.add_argument(
            "--base-parent-page-id",
            type=str,
            default=config.BASE_PARENT_CONFLUENCE_PAGE_ID,
        )
        parser.add_argument(
            "--confluence-space-key", type=str, default=config.CONFLUENCE_SPACE_KEY
        )
        parser.add_argument(
            "--assignee-username",
            type=str,
            default=config.ASSIGNEE_USERNAME_FOR_GENERATED_TASKS,
        )
        parser.add_argument(
            "--test-work-package-keys",
            nargs="+",
            default=config.TEST_WORK_PACKAGE_KEYS_TO_DISTRIBUTE,
        )
        parser.add_argument("--max-depth", type=int, default=config.DEFAULT_MAX_DEPTH)
        parser.add_argument(
            "--tasks-per-page", type=int, default=config.DEFAULT_TASKS_PER_PAGE
        )
        return parser.parse_args()


async def main_async() -> None:
    # Set up logging for the script
    setup_logging()
    endpoint_var.set("generate_page_tre.py")
    request_id_var.set(uuid.uuid4().hex)

    logger.info("--- Starting Confluence Test Data Generation Script ---")
    args = ConfluenceTreeGenerator._parse_args()

    if (
        not args.base_parent_page_id
        or args.base_parent_page_id == "YOUR_BASE_PARENT_PAGE_ID_HERE"
    ):
        logger.error("Please provide a valid --base-parent-page-id.")
        sys.exit(1)

    try:
        async with resource_manager() as https_helper:
            safe_jira_api = SafeJiraAPI(config.JIRA_URL, https_helper)
            safe_confluence_api = SafeConfluenceAPI(config.CONFLUENCE_URL, https_helper)
            jira_service = JiraService(safe_jira_api)
            confluence_service = ConfluenceService(safe_confluence_api)
            issue_finder = IssueFinderService(
                jira_api=jira_service, confluence_api=confluence_service
            )


            generator = ConfluenceTreeGenerator(
                confluence_service=confluence_service,
                jira_service=jira_service,
                issue_finder=issue_finder,
                base_parent_page_id=args.base_parent_page_id,
                confluence_space_key=args.confluence_space_key,
                assignee_username=args.assignee_username,
                test_work_package_keys=args.test_work_package_keys,
                max_depth=args.max_depth,
                tasks_per_page=args.tasks_per_page,
            )

            await generator._initialize_assignee()
            generated_page_info = await generator.generate_page_hierarchy(
                parent_page_id=args.base_parent_page_id
            )

            if generated_page_info:
                logger.info(f"Successfully generated {len(generated_page_info)} pages.")
            else:
                logger.info("No pages were generated.")

    except Exception as e:
        logger.critical(
            f"A critical error occurred during script execution: {e}", exc_info=True
        )
        sys.exit(1)

    logger.info("--- Confluence Test Data Generation Script Finished ---")


if __name__ == "__main__":
    asyncio.run(main_async())
