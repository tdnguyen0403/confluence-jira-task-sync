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

# Ensured all types are imported
from bs4 import BeautifulSoup

from src.config import config
from src.exceptions import InvalidInputError
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.models.data_models import (
    SyncProjectPageDetail,
)

logger = logging.getLogger(__name__)


class ConfluenceIssueUpdaterService:
    """
    A service to update Confluence pages by replacing embedded Jira issue macros.
    It finds suitable replacement issues from a given root project based on
    issue type and fuzzy summary matching.
    """

    # This service directly interacts with SafeConfluenceApi and SafeJiraApi
    # as it needs low-level control over page updates and macro generation.
    def __init__(
        self,
        confluence_api: ConfluenceApiServiceInterface,  # Renamed
        jira_api: JiraApiServiceInterface,  # Renamed
        issue_finder_service: Any,
    ):
        self.confluence_api = confluence_api
        self.jira_api = jira_api
        self.issue_finder_service = issue_finder_service

    async def update_confluence_hierarchy_with_new_jira_project(
        self,
        root_confluence_page_url: str,
        root_project_issue_key: str,
        project_issue_type_id: Optional[str] = None,
        phase_issue_type_id: Optional[str] = None,
    ) -> List[SyncProjectPageDetail]:
        """
        Updates Jira issue macros on a Confluence page hierarchy asynchronously.

        Args:
            root_confluence_page_url (str): The URL of the root Confluence page.
            root_project_issue_key (str): The Jira key of the root project/portfolio
                issue to find replacement candidates under.
            project_issue_type_id (Optional[str]): The Jira issue type ID for
                'Project'. Defaults to config.
            phase_issue_type_id (Optional[str]): The Jira issue type ID for
                'Phase'. Defaults to config.

        Returns:
            List[SyncProjectPageDetail]: A list of SyncProjectPageDetail objects
                summarizing the updates made.

        Raises:
            InvalidInputError: If the root Confluence page ID cannot be resolved.
            SyncError: For other errors during the update process.
        """
        logger.info(
            "Starting Confluence issue update for hierarchy from: "
            f"{root_confluence_page_url}"
        )

        root_page_id = await self.confluence_api.get_page_id_from_url(
            root_confluence_page_url
        )
        if not root_page_id:
            error_msg = (
                f"Could not find page ID for URL: {root_confluence_page_url}. "
                "Aborting update."
            )
            logger.error(error_msg)
            raise InvalidInputError(error_msg)

        all_page_ids = [root_page_id] + await self.confluence_api.get_all_descendants(
            root_page_id
        )
        logger.info(
            f"Found {len(all_page_ids)} total page(s) in the hierarchy to scan."
        )

        actual_project_type_id = (
            project_issue_type_id
            if project_issue_type_id
            else config.JIRA_PROJECT_ISSUE_TYPE_ID
        )
        actual_phase_type_id = (
            phase_issue_type_id
            if phase_issue_type_id
            else config.JIRA_PHASE_ISSUE_TYPE_ID
        )
        actual_work_package_type_id = config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID

        target_issue_type_ids_set = {
            actual_project_type_id,
            actual_phase_type_id,
            actual_work_package_type_id,
        }

        candidate_new_issues = await self._get_relevant_jira_issues_under_root(
            root_project_issue_key, target_issue_type_ids_set
        )
        if not candidate_new_issues:
            logger.warning(
                f"No suitable candidate issues found under root project "
                f"'{root_project_issue_key}'. No replacements can be made."
            )
            return []

        updated_pages_summary = []
        for page_id in all_page_ids:
            try:
                page_details = await self.confluence_api.get_page_by_id(
                    page_id, expand="body.storage,version"
                )
                if not page_details:
                    logger.warning(
                        f"Could not retrieve content for page ID '{page_id}'. Skipping."
                    )
                    continue

                original_html = (
                    page_details.get("body", {}).get("storage", {}).get("value", "")
                )
                if not original_html:
                    logger.info(f"Page ID '{page_id}' has no content. Skipping.")
                    continue

                (
                    modified_html,
                    did_modify,
                ) = await self._find_and_replace_jira_macros_on_page(
                    page_details=page_details,
                    html_content=original_html,
                    candidate_new_issues=candidate_new_issues,
                    target_issue_type_ids=target_issue_type_ids_set,
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
                        updated_pages_summary.append(
                            SyncProjectPageDetail(
                                page_id=page_id,
                                page_title=page_details.get("title", "N/A"),
                                new_jira_keys=[
                                    issue.get("key")
                                    for issue in candidate_new_issues
                                    if issue.get("key") in modified_html
                                ],
                                root_project_linked=root_project_issue_key,
                            )
                        )
                    else:
                        logger.error(
                            f"Failed to update page "
                            f"'{page_details.get('title', page_id)}' "
                            f"(ID: {page_id})."
                        )
                else:
                    logger.info(
                        f"No relevant Jira macros found or replaced on page "
                        f"'{page_details.get('title', page_id)}'. Skipping."
                    )
            except Exception as e:
                logger.error(
                    f"An error occurred while processing page {page_id}: {e}",
                    exc_info=True,
                )

        logger.info("Finished Confluence issue update process.")
        return updated_pages_summary

    async def _get_relevant_jira_issues_under_root(
        self, root_key: str, target_issue_type_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Fetches all Jira issues of target types under a given root project issue.

        Uses JQL to query for issues whose 'Root Parent' custom field points
        to the root_key, and whose issue type is one of the target types.
        """
        issue_type_names = []
        for type_id in target_issue_type_ids:
            name_details = await self.jira_api.get_issue_type_details_by_id(type_id)
            if name_details and name_details.get("name"):
                issue_type_names.append(f'"{name_details.get("name")}"')
            else:
                logger.warning(
                    f"Could not get name for issue type ID '{type_id}'. "
                    "This type will be excluded from JQL search."
                )

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

        fields_to_retrieve = ["key", "issuetype", "summary"]
        relevant_issues = await self.jira_api.search_issues(
            jql_query, fields=fields_to_retrieve
        )

        filtered_issues = [
            issue
            for issue in relevant_issues.get("issues", [])
            if issue.get("fields", {}).get("issuetype", {}).get("id")
            in target_issue_type_ids
        ]

        logger.info(
            f"Found {len(filtered_issues)} relevant candidate issues under "
            f"'{root_key}' after filtering."
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

        A 'best' match is one that has the same issue type and the highest
        summary similarity above a given threshold.
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

                if similarity_ratio >= FUZZY_MATCH_THRESHOLD:
                    if similarity_ratio > highest_similarity:
                        highest_similarity = similarity_ratio
                        best_match = candidate
            elif not old_issue_summary and not candidate_summary:
                if highest_similarity < 1.0:
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

        Args:
            page_details (Dict[str, Any]): The details of the Confluence page.
            html_content (str): The Confluence page content in storage format.
            candidate_new_issues (List[Dict[str, Any]]): A list of Jira issues
                to consider as replacements.
            target_issue_type_ids (Set[str]): The set of Jira issue type IDs
                that are eligible for replacement.

        Returns:
            Tuple[str, bool]: The modified HTML and a boolean indicating
                if any modifications were made.
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
                        f"Could not get details for Jira issue '{current_key}' on page "
                        f"'{page_details.get('title', page_details.get('id'))}'. "
                        "Skipping it."
                    )
                    continue

                issue_type_id = (
                    old_issue.get("fields", {}).get("issuetype", {}).get("id")
                )  # noqa: E501
                if issue_type_id not in target_issue_type_ids:
                    continue

                best_match = self._find_best_new_issue_match(
                    old_issue_details=old_issue,
                    candidate_new_issues=candidate_new_issues,
                    FUZZY_MATCH_THRESHOLD=FUZZY_MATCH_THRESHOLD,
                )

                if best_match and (new_key := best_match.get("key")):
                    old_summary = old_issue.get("fields", {}).get("summary", "")
                    new_summary = best_match.get("fields", {}).get("summary", "")
                    logger.info(
                        f"On page '{page_details.get('title')}', "
                        f"replacing '{current_key}' "
                        f"(Summary: '{old_summary}') with '{new_key}' "
                        f"(Summary: '{new_summary}')"
                    )
                    new_macro_html = self.confluence_api._generate_jira_macro_html(
                        new_key
                    )  # noqa: E501
                    macro.replace_with(BeautifulSoup(new_macro_html, "html.parser"))
                    modified = True
                else:
                    old_summary = old_issue.get("fields", {}).get("summary", "")
                    logger.info(
                        f"No suitable replacement found for '{current_key}' "
                        f"(Summary: '{old_summary}') on page "
                        f"'{page_details.get('title')}'. "
                        "Skipping."
                    )
            except Exception as e:
                logger.warning(
                    f"Error processing macro for '{current_key}' on page "
                    f"'{page_details.get('title')}': {e}",
                    exc_info=True,
                )

        return str(soup), modified
