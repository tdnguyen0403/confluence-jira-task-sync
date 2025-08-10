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

from bs4 import BeautifulSoup, Tag

from src.config import config
from src.exceptions import ConfluenceApiError, InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.api_models import SinglePageResult

logger = logging.getLogger(__name__)


class SyncProjectService:
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

    async def sync_project_to_confluence(
        self,
        project_page_url: str,
        project_key: str,
    ) -> List[SinglePageResult]:
        """
        Updates Jira issue macros on a Confluence page hierarchy concurrently.
        """
        logger.info(
            f"Starting Confluence update for hierarchy from: {project_page_url}"
        )

        root_page_id = await self.confluence_api.get_page_id_from_url(project_page_url)
        if not root_page_id:
            raise InvalidInputError(
                f"Could not find page ID for URL: {project_page_url}. Aborting."
            )

        all_page_ids = [root_page_id] + await self.confluence_api.get_all_descendants(
            root_page_id
        )
        logger.info(f"Found {len(all_page_ids)} total page(s) to scan.")

        target_ids_raw = {
            config.JIRA_PHASE_ISSUE_TYPE_ID,
            config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID,
            config.JIRA_WORK_CONTAINER_ISSUE_TYPE_ID,
        }
        target_ids = {t_id for t_id in target_ids_raw if t_id is not None}
        candidate_issues = await self._get_project_issues(project_key, target_ids)

        if not candidate_issues:
            logger.warning(
                f"No suitable candidate issues found under '{project_key}'. "
                "No replacements can be made."
            )
            return []

        tasks = [
            self._process_page(page_id, candidate_issues, target_ids, project_key)
            for page_id in all_page_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        updated_summary: List[SinglePageResult] = []
        for res in results:
            if isinstance(res, SinglePageResult):
                updated_summary.append(res)
            elif isinstance(res, Exception):
                logger.error(f"Error during page processing: {res}", exc_info=res)

        logger.info("Finished Confluence issue update process.")
        return updated_summary

    async def _process_page(
        self,
        page_id: str,
        candidate_new_issues: List[Dict[str, Any]],
        target_issue_type_ids: Set[str],
        project_key: str,
    ) -> SinglePageResult:
        """
        Processes a single Confluence page to find and replace Jira macros.
        """
        try:
            page_details = await self.confluence_api.get_page_by_id(
                page_id, expand="body.storage,version"
            )
            if not page_details or not page_details.get("body", {}).get(
                "storage", {}
            ).get("value"):
                logger.info(f"Page '{page_id}' has no content or could not be fetched.")
                return SinglePageResult(
                    page_id=page_id,
                    page_title=f"Unknown Title (ID: {page_id})",
                    status="Failed - No Content retreived",
                    new_jira_keys=[],
                    project_linked=project_key,
                )

            page_title = page_details.get("title", page_id)
            original_html = page_details["body"]["storage"]["value"]
            (
                modified_html,
                did_modify,
            ) = await self._replace_macros_on_page(
                page_title, original_html, candidate_new_issues, target_issue_type_ids
            )

            if not did_modify:
                logger.info(f"No relevant macros found to replace on '{page_title}'.")
                return SinglePageResult(
                    page_id=page_id,
                    page_title=page_title,
                    status="Skipped - No relevant macros found",
                    new_jira_keys=[],
                    project_linked=project_key,
                )

            logger.info(f"Updating page '{page_title}' (ID: {page_id}).")
            success = await self.confluence_api.update_page_content(
                page_id, page_details["title"], modified_html
            )

            if success:
                new_keys = [
                    issue_key
                    for issue in candidate_new_issues
                    if (issue_key := issue.get("key"))
                    and isinstance(issue_key, str)
                    and issue_key in modified_html
                ]
                return SinglePageResult(
                    page_id=page_id,
                    page_title=page_details.get("title", "N/A"),
                    new_jira_keys=new_keys,
                    project_linked=project_key,
                    status="Success",
                )
            else:
                return SinglePageResult(
                    page_id=page_id,
                    page_title="Page with ID: {page_id}",
                    status="Failed - updating failed unexpectedly",
                    new_jira_keys=[],
                    project_linked=project_key,
                )
        except ConfluenceApiError as e:
            # Catch the API error from the update call, can be due to permission
            logger.error(
                f"An API error occurred while processing page '{page_id}': {e}",
                exc_info=True,
            )
            return SinglePageResult(
                page_id=page_id,
                page_title="Page with ID: {page_id}",
                status=f"Failed - API Error ({e.status_code})",
                new_jira_keys=[],
                project_linked=project_key,
            )

        except Exception as e:
            # Catch any other unexpected errors during processing
            logger.error(
                f"An unexpected error occurred while processing page '{page_id}': {e}",
                exc_info=True,
            )
            return SinglePageResult(
                page_id=page_id,
                page_title="Page with ID: {page_id}",
                status="Failed - Unexpected Error",
                new_jira_keys=[],
                project_linked=project_key,
            )

    async def _get_project_issues(
        self, root_key: str, target_issue_type_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Fetches all Jira issues of target types under a given root project.
        """
        if not target_issue_type_ids:
            logger.warning("No target issue type IDs provided for JQL search.")
            return []

        type_ids_str = ", ".join(sorted(list(target_issue_type_ids)))
        jql = (
            f"issuetype in ({type_ids_str}) "
            f"AND issue in relation('{root_key}', 'Project Children', 'all')"
        )
        logger.info(f"Searching Jira with JQL: {jql}")

        fields_to_get = "key,issuetype,summary"
        return await self.jira_api.search_issues_by_jql(jql, fields=fields_to_get)

    async def _get_macro_issue_details(
        self, soup: BeautifulSoup
    ) -> Dict[str, Dict[str, Any]]:
        """Finds all Jira macro keys on a page and fetches their details in bulk."""
        keys_on_page = set()
        for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            if not isinstance(macro, Tag):
                continue
            key_param = macro.find("ac:parameter", {"ac:name": "key"})
            if isinstance(key_param, Tag):
                keys_on_page.add(key_param.get_text(strip=True))

        if not keys_on_page:
            return {}

        jql = f"issue in ({','.join(sorted(keys_on_page))})"
        fields_to_get = "issuetype,summary"
        issues = await self.jira_api.search_issues_by_jql(jql, fields=fields_to_get)
        return {issue["key"]: issue for issue in issues}

    async def _replace_macros_on_page(
        self,
        page_title: str,
        html_content: str,
        candidate_new_issues: List[Dict[str, Any]],
        target_issue_type_ids: Set[str],
    ) -> Tuple[str, bool]:
        """
        Parses HTML, finds Jira macros, and replaces them with the best match.
        """
        soup = await asyncio.to_thread(BeautifulSoup, html_content, "html.parser")
        modified = False

        try:
            old_issues_map = await self._get_macro_issue_details(soup)
        except Exception as e:
            logger.error(
                f"Could not fetch Jira macro details for page '{page_title}': {e}"
            )
            return str(soup), False

        for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
            if not isinstance(macro, Tag):  # Ensure macro is a Tag
                continue
            key_param = macro.find("ac:parameter", {"ac:name": "key"})
            if not isinstance(key_param, Tag) or not (
                current_key := key_param.get_text(strip=True)
            ):  # Ensure key_param is a Tag
                continue

            old_issue = old_issues_map.get(current_key)
            if not old_issue:
                logger.warning(
                    f"No details for '{current_key}' on page '{page_title}'."
                )
                continue

            issue_type = old_issue.get("fields", {}).get("issuetype", {}).get("id")
            if issue_type not in target_issue_type_ids:
                continue

            best_match = self._find_best_match(old_issue, candidate_new_issues)
            if best_match and (new_key := best_match.get("key")):
                logger.info(
                    f"On page '{page_title}', replacing '{current_key}' "
                    f"with '{new_key}'"
                )
                new_macro_html = self.confluence_api.generate_jira_macro(
                    new_key, with_summary=True
                )
                macro.replace_with(BeautifulSoup(new_macro_html, "html.parser"))
                modified = True

        return str(soup), modified

    def _find_best_match(
        self,
        old_issue_details: Dict[str, Any],
        candidate_new_issues: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the best matching new issue from candidates for a given old issue.
        """
        old_type = old_issue_details.get("fields", {}).get("issuetype", {}).get("id")
        old_summary = old_issue_details.get("fields", {}).get("summary", "")

        best_match, highest_similarity = None, -1.0

        for candidate in candidate_new_issues:
            cand_type = candidate.get("fields", {}).get("issuetype", {}).get("id")
            cand_summary = candidate.get("fields", {}).get("summary")

            if cand_type != old_type or cand_summary is None:
                continue

            similarity = difflib.SequenceMatcher(
                None, old_summary.lower(), cand_summary.lower()
            ).ratio()

            if (
                similarity >= config.FUZZY_MATCH_THRESHOLD
                and similarity > highest_similarity
            ):
                highest_similarity, best_match = similarity, candidate

        return best_match
