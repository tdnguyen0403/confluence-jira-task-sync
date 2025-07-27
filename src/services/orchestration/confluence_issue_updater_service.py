import asyncio
import difflib
import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

from bs4 import BeautifulSoup

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import SinglePageResult

logger = logging.getLogger(__name__)


class ConfluenceIssueUpdaterService:
    """
    A service to update Confluence pages by replacing embedded Jira issue macros.
    """

    def __init__(
        self,
        confluence_api: ConfluenceApiServiceInterface,
        jira_api: JiraApiServiceInterface,
        issue_finder_service: Any,
    ):
        self.confluence_api = confluence_api
        self.jira_api = jira_api
        self.issue_finder_service = issue_finder_service

    async def update_confluence_hierarchy_with_new_jira_project(
        self,
        project_page_url: str,
        project_key: str,
    ) -> List[SinglePageResult]:
        """
        Updates Jira issue macros on a Confluence page hierarchy concurrently.
        """
        logger.info(
            f"Starting Confluence issue update for hierarchy from: {project_page_url}"
        )

        root_page_id = await self.confluence_api.get_page_id_from_url(project_page_url)
        if not root_page_id:
            raise InvalidInputError(
                f"Could not find page ID for URL: {project_page_url}. Aborting update."
            )

        all_page_ids = [root_page_id] + await self.confluence_api.get_all_descendants(
            root_page_id
        )
        logger.info(
            f"Found {len(all_page_ids)} total page(s) in the hierarchy to scan."
        )

        target_issue_type_ids = {
            config.JIRA_PROJECT_ISSUE_TYPE_ID,
            config.JIRA_PHASE_ISSUE_TYPE_ID,
            config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID,
        }

        candidate_new_issues = await self._get_relevant_jira_issues_under_root(
            project_key, target_issue_type_ids
        )

        if not candidate_new_issues:
            logger.warning(
                f"No suitable candidate issues found under root project '"
                f"{project_key}'. No replacements can be made."
            )
            return []

        # Create a coroutine for each page to be processed
        processing_tasks = [
            self._process_page(
                page_id,
                candidate_new_issues,
                target_issue_type_ids,
                project_key,
            )
            for page_id in all_page_ids
        ]

        # Execute all page processing tasks concurrently
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)

        # Filter out None results and log any exceptions
        updated_pages_summary = []
        for result in results:
            if isinstance(result, SinglePageResult):
                updated_pages_summary.append(result)
            elif isinstance(result, Exception):
                logger.error(
                    f"An error occurred during page processing: {result}",
                    exc_info=result,
                )

        logger.info("Finished Confluence issue update process.")
        return updated_pages_summary

    async def _process_page(
        self,
        page_id: str,
        candidate_new_issues: List[Dict[str, Any]],
        target_issue_type_ids: Set[str],
        project_key: str,
    ) -> Optional[SinglePageResult]:
        """
        Processes a single Confluence page to find and replace Jira macros.
        Returns a summary object if the page was successfully updated.
        """
        page_details = await self.confluence_api.get_page_by_id(
            page_id, expand="body.storage,version"
        )
        if not page_details:
            logger.warning(
                f"Could not retrieve content for page ID '{page_id}'. Skipping."
            )
            return None

        original_html = page_details.get("body", {}).get("storage", {}).get("value", "")
        if not original_html:
            logger.info(f"Page ID '{page_id}' has no content. Skipping.")
            return None

        modified_html, did_modify = await self._find_and_replace_jira_macros_on_page(
            page_details=page_details,
            html_content=original_html,
            candidate_new_issues=candidate_new_issues,
            target_issue_type_ids=target_issue_type_ids,
        )

        if did_modify:
            logger.info(
                f"Updating page '{page_details.get('title', page_id)}' "
                f"(ID: {page_id}) with new Jira links."
            )
            success = await self.confluence_api.update_page(
                page_id, page_details["title"], modified_html
            )
            if success:
                return SinglePageResult(
                    page_id=page_id,
                    page_title=page_details.get("title", "N/A"),
                    new_jira_keys=[
                        issue.get("key")
                        for issue in candidate_new_issues
                        if issue.get("key") in modified_html
                    ],
                    project_linked=project_key,
                )
            else:
                logger.error(
                    f"Failed to update page '{page_details.get('title', page_id)}' "
                    f"(ID: {page_id})."
                )
        else:
            logger.info(
                f"No relevant Jira macros found or replaced on page '"
                f"{page_details.get('title', page_id)}'. Skipping."
            )

        return None

    async def _get_relevant_jira_issues_under_root(
        self, root_key: str, target_issue_type_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Fetches all Jira issues of target types under a given root project issue.
        """
        # Concurrently fetch names for all issue type IDs
        name_tasks = [
            self.jira_api.get_issue_type_details_by_id(type_id)
            for type_id in target_issue_type_ids
        ]
        name_details_list = await asyncio.gather(*name_tasks)

        issue_type_names = [
            f'"{details.get("name")}"'
            for details in name_details_list
            if details and details.get("name")
        ]

        if not issue_type_names:
            logger.warning(
                "No valid issue type names found for JQL. Returning empty list."
            )
            return []

        issue_type_names_sorted = sorted(issue_type_names)
        jql_query = (
            f"issuetype in ({', '.join(issue_type_names_sorted)}) "
            f"AND issue in relation('{root_key}', '', 'all')"
        )
        logger.info(f"Searching Jira with JQL: {jql_query}")

        relevant_issues = await self.jira_api.search_issues(
            jql_query, fields=["key", "issuetype", "summary"]
        )

        filtered_issues = [
            issue
            for issue in relevant_issues.get("issues", [])
            if issue.get("fields", {}).get("issuetype", {}).get("id")
            in target_issue_type_ids
        ]

        logger.info(
            f"Found {len(filtered_issues)} relevant candidate issues under '"
            f"{root_key}' after filtering."
        )
        return filtered_issues

    def _find_best_new_issue_match(
        self,
        old_issue_details: Dict[str, Any],
        candidate_new_issues: List[Dict[str, Any]],
        FUZZY_MATCH_THRESHOLD: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the best matching new issue from candidates for a given old issue.
        """
        old_issue_type_id = (
            old_issue_details.get("fields", {}).get("issuetype", {}).get("id")
        )
        old_issue_summary = old_issue_details.get("fields", {}).get("summary", "")

        best_match = None
        highest_similarity = -1.0

        for candidate in candidate_new_issues:
            candidate_type_id = (
                candidate.get("fields", {}).get("issuetype", {}).get("id")
            )
            candidate_summary = candidate.get("fields", {}).get("summary", "")

            if candidate_type_id != old_issue_type_id:
                continue

            if old_issue_summary and candidate_summary:
                similarity_ratio = difflib.SequenceMatcher(
                    None, old_issue_summary.lower(), candidate_summary.lower()
                ).ratio()

                if (
                    similarity_ratio >= FUZZY_MATCH_THRESHOLD
                    and similarity_ratio > highest_similarity
                ):
                    highest_similarity = similarity_ratio
                    best_match = candidate
            elif (
                not old_issue_summary
                and not candidate_summary
                and highest_similarity < 1.0
            ):
                highest_similarity = 1.0
                best_match = candidate

        return best_match

    async def _find_and_replace_jira_macros_on_page(
        self,
        page_details: Dict[str, Any],
        html_content: str,
        candidate_new_issues: List[Dict[str, Any]],
        target_issue_type_ids: Set[str],
    ) -> Tuple[str, bool]:
        """
        Parses HTML, finds specific Jira macros, finds replacements, and replaces.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        modified = False
        FUZZY_MATCH_THRESHOLD = config.FUZZY_MATCH_THRESHOLD

        current_jira_keys_on_page = {
            key_param.get_text(strip=True)
            for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"})
            if (key_param := macro.find("ac:parameter", {"ac:name": "key"}))
        }

        fetched_old_issues_map: Dict[str, Dict[str, Any]] = {}
        if current_jira_keys_on_page:
            jql_query = f"issue in ({','.join(current_jira_keys_on_page)})"
            try:
                bulk_response = await self.jira_api.search_issues(
                    jql_query, fields=["issuetype", "summary"]
                )
                for issue_data in bulk_response.get("issues", []):
                    fetched_old_issues_map[issue_data["key"]] = issue_data
            except Exception as e:
                logger.error(
                    f"Error fetching existing Jira issues in bulk for page "
                    f"{page_details.get('id')}: {e}",
                    exc_info=True,
                )

        for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            key_param = macro.find("ac:parameter", {"ac:name": "key"})
            if not key_param or not (current_key := key_param.get_text(strip=True)):
                continue

            try:
                old_issue = fetched_old_issues_map.get(current_key)
                if not old_issue:
                    logger.warning(
                        f"Could not get details for Jira issue "
                        f"'{current_key}' on page '"
                        f"{page_details.get('title', page_details.get('id'))}'. "
                        f"Skipping it."
                    )
                    continue

                if (
                    old_issue.get("fields", {}).get("issuetype", {}).get("id")
                    not in target_issue_type_ids
                ):
                    continue

                best_match = self._find_best_new_issue_match(
                    old_issue_details=old_issue,
                    candidate_new_issues=candidate_new_issues,
                    FUZZY_MATCH_THRESHOLD=FUZZY_MATCH_THRESHOLD,
                )

                if best_match and (new_key := best_match.get("key")):
                    logger.info(
                        f"On page '{page_details.get('title')}', replacing "
                        f"'{current_key}' with '{new_key}'"
                    )
                    new_macro_html = self.confluence_api._generate_jira_macro_html(
                        new_key
                    )
                    macro.replace_with(BeautifulSoup(new_macro_html, "html.parser"))
                    modified = True
                else:
                    logger.info(
                        f"No suitable replacement found for '{current_key}' on page '"
                        f"{page_details.get('title')}'. Skipping."
                    )
            except Exception as e:
                logger.warning(
                    f"Error processing macro for '{current_key}' on page '"
                    f"{page_details.get('title')}': {e}",
                    exc_info=True,
                )

        return str(soup), modified
