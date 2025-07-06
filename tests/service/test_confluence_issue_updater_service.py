import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, Mock
import difflib

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.services.confluence_issue_updater_service import ConfluenceIssueUpdaterService
from src.interfaces.confluence_service_interface import ConfluenceApiServiceInterface
from src.interfaces.jira_service_interface import JiraApiServiceInterface
from src.exceptions import InvalidInputError, SyncError
from src.config import config # Import config to directly access patched values


# Disable logging during tests for cleaner output.
logging.disable(logging.CRITICAL)


class TestConfluenceIssueUpdaterService(unittest.TestCase):
    """Tests the ConfluenceIssueUpdaterService and its helper methods."""

    def setUp(self):
        self.mock_confluence_service = MagicMock(spec=ConfluenceApiServiceInterface)
        self.mock_jira_service = MagicMock(spec=JiraApiServiceInterface)
        
        # Patch the entire config module that confluence_issue_updater_service imports
        self.patcher_config = patch('src.services.confluence_issue_updater_service.config')
        self.mock_config = self.patcher_config.start()
        self.addCleanup(self.patcher_config.stop)

        # Set attributes on the mocked config module
        # Removed: self.mock_config.JIRA_ROOT_PARENT_CUSTOM_FIELD_ID = 'customfield_12200'
        self.mock_config.JIRA_PROJECT_ISSUE_TYPE_ID = '10200'
        self.mock_config.JIRA_PHASE_ISSUE_TYPE_ID = '11001'
        self.mock_config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID = '10100'
        #self.mock_config.JIRA_ROOT_PARENT_CUSTOM_FIELD_NAME = 'Root Parent')

        self.service = ConfluenceIssueUpdaterService(self.mock_confluence_service, self.mock_jira_service)

        # Mock SafeConfluenceApi's _generate_jira_macro_html as it's used internally
        self.mock_confluence_service._api = MagicMock()
        self.mock_confluence_service._api._generate_jira_macro_html.side_effect = \
            lambda key: f"<p><ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">{key}</ac:parameter></ac:structured-macro></p>"
        
        # Patch BeautifulSoup globally for tests that operate on HTML strings
        self.mock_beautiful_soup_patcher = patch('src.services.confluence_issue_updater_service.BeautifulSoup')
        self.MockBeautifulSoupClass = self.mock_beautiful_soup_patcher.start()
        self.addCleanup(self.mock_beautiful_soup_patcher.stop)
        
        # This will be the mock instance returned by BeautifulSoup(html_content, "html.parser")
        self.mock_soup_instance = Mock()
        self.MockBeautifulSoupClass.return_value = self.mock_soup_instance
        # Correctly mock __str__ for the BeautifulSoup mock instance
        self.mock_soup_instance.__str__ = Mock(return_value="mocked_initial_html")


    def test_get_relevant_jira_issues_under_root_success(self):
        """Test _get_relevant_jira_issues_under_root correctly fetches and filters issues."""
        root_key = "PROJ-ROOT"
        target_type_ids = {"10200", "11001", "10100"} # Project, Phase, Work Package

        self.mock_jira_service.get_issue_type_name_by_id.side_effect = lambda tid: {
            "10200": "Project", "11001": "Phase", "10100": "Work Package"
        }.get(tid)

        mock_search_results = [
            {"key": "PROJ-1", "fields": {"issuetype": {"id": "10200", "name": "Project"}, "summary": "Project A"}},
            {"key": "PHASE-1", "fields": {"issuetype": {"id": "11001", "name": "Phase"}, "summary": "Phase Alpha"}},
            {"key": "WP-1", "fields": {"issuetype": {"id": "10100", "name": "Work Package"}, "summary": "Work Package Task"}},
            {"key": "TASK-1", "fields": {"issuetype": {"id": "10002", "name": "Task"}, "summary": "Random Task"}} # Should be filtered out
        ]
        self.mock_jira_service.search_issues_by_jql.return_value = mock_search_results

        # Ensure consistent order for JQL assertion by sorting the names
        expected_issue_type_names_sorted = sorted(["Project", "Phase", "Work Package"])
        expected_jql = (
            f'issuetype in ("{expected_issue_type_names_sorted[0]}", "{expected_issue_type_names_sorted[1]}", "{expected_issue_type_names_sorted[2]}") '
            f"AND issue in relation('{root_key}', '', 'all')"
        )
        expected_fields = "key,issuetype,summary"

        relevant_issues = self.service._get_relevant_jira_issues_under_root(root_key, target_type_ids)

        self.mock_jira_service.get_issue_type_name_by_id.assert_any_call("10200")
        self.mock_jira_service.get_issue_type_name_by_id.assert_any_call("11001")
        self.mock_jira_service.get_issue_type_name_by_id.assert_any_call("10100")
        self.mock_jira_service.search_issues_by_jql.assert_called_once_with(expected_jql, fields=expected_fields)
        self.assertEqual(len(relevant_issues), 3)
        self.assertNotIn({"key": "TASK-1", "fields": {"issuetype": {"id": "10002", "name": "Task"}, "summary": "Random Task"}}, relevant_issues)
        self.assertEqual(relevant_issues[0]["key"], "PROJ-1")

    def test_get_relevant_jira_issues_under_root_no_type_names(self):
        """Test _get_relevant_jira_issues_under_root handles no issue type names."""
        root_key = "PROJ-ROOT"
        target_type_ids = {"10200"}
        self.mock_jira_service.get_issue_type_name_by_id.return_value = None # No names found

        relevant_issues = self.service._get_relevant_jira_issues_under_root(root_key, target_type_ids)
        self.assertEqual(relevant_issues, [])
        self.mock_jira_service.search_issues_by_jql.assert_not_called()

    def test_find_best_new_issue_match_exact(self):
        """Test _find_best_new_issue_match with exact match."""
        old_issue = {"key": "OLD-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Exact Summary"}}
        candidates = [
            {"key": "NEW-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Exact Summary"}},
            {"key": "NEW-2", "fields": {"issuetype": {"id": "10100"}, "summary": "Similar Summary"}}
        ]
        match = self.service._find_best_new_issue_match(old_issue, candidates, 0.6)
        self.assertEqual(match["key"], "NEW-1")

    def test_find_best_new_issue_match_fuzzy_above_threshold(self):
        """Test _find_best_new_issue_match with fuzzy match above threshold."""
        old_issue = {"key": "OLD-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Similar Summary Text Here"}}
        candidates = [
            {"key": "NEW-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Slightly Different Summary Text"}},
            {"key": "NEW-2", "fields": {"issuetype": {"id": "10100"}, "summary": "Very Similar Summary Text Here Now"}}
        ]
        with patch('difflib.SequenceMatcher') as mock_seq_matcher:
            mock_instance = Mock()
            mock_seq_matcher.return_value = mock_instance
            mock_instance.ratio.side_effect = [0.5, 0.9]

            match = self.service._find_best_new_issue_match(old_issue, candidates, 0.7)
            self.assertEqual(match["key"], "NEW-2")
            self.assertGreater(mock_instance.ratio.call_count, 0)

    def test_find_best_new_issue_match_fuzzy_below_threshold(self):
        """Test _find_best_new_issue_match with fuzzy match below threshold."""
        old_issue = {"key": "OLD-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Unique Text"}}
        candidates = [
            {"key": "NEW-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Completely Different"}}
        ]
        with patch('difflib.SequenceMatcher') as mock_seq_matcher:
            mock_instance = Mock()
            mock_seq_matcher.return_value = mock_instance
            mock_instance.ratio.return_value = 0.3 # Below threshold

            match = self.service._find_best_new_issue_match(old_issue, candidates, 0.6)
            self.assertIsNone(match)

    def test_find_best_new_issue_match_no_type_match(self):
        """Test _find_best_new_issue_match when issue types don't match."""
        old_issue = {"key": "OLD-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Summary"}}
        candidates = [
            {"key": "NEW-1", "fields": {"issuetype": {"id": "10002"}, "summary": "Summary"}}
        ]
        match = self.service._find_best_new_issue_match(old_issue, candidates, 0.6)
        self.assertIsNone(match)

    def test_find_best_new_issue_match_empty_summaries(self):
        """Test _find_best_new_issue_match with empty summaries."""
        old_issue = {"key": "OLD-1", "fields": {"issuetype": {"id": "10100"}, "summary": ""}}
        candidates = [
            {"key": "NEW-1", "fields": {"issuetype": {"id": "10100"}, "summary": ""}},
            {"key": "NEW-2", "fields": {"issuetype": {"id": "10100"}, "summary": "Not Empty"}}
        ]
        match = self.service._find_best_new_issue_match(old_issue, candidates, 0.6)
        self.assertIsNotNone(match)
        self.assertEqual(match["key"], "NEW-1")


    def test_find_and_replace_jira_macros_on_page_success(self):
        """Test _find_and_replace_jira_macros_on_page successfully replaces a macro."""
        mock_html_content = (
            "<p>Some text with a task:</p>"
            "<p><ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">OLD-1</ac:parameter></ac:structured-macro></p>"
            "<p>More text.</p>"
        )
        mock_page_details = {"id": "page1", "title": "Test Page"}
        candidate_new_issues = [
            {"key": "NEW-1", "fields": {"issuetype": {"id": "10100"}, "summary": "Old Summary"}},
        ]
        target_type_ids = {"10100"}

        # Configure mock_soup_instance for this test
        mock_jira_macro_tag = Mock()
        mock_jira_macro_tag.find.return_value.get_text.return_value = "OLD-1"
        self.mock_soup_instance.find_all.return_value = [mock_jira_macro_tag]
        
        self.mock_soup_instance.__str__ = Mock(return_value= \
            "<p>Some text with a task:</p>" \
            "<p><ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">NEW-1</ac:parameter></ac:structured-macro></p>" \
            "<p>More text.</p>")

        self.mock_jira_service.get_issue.return_value = {
            "key": "OLD-1", 
            "fields": {"issuetype": {"id": "10100", "name": "Work Package"}, "summary": "Old Summary"}
        }
        self.service._find_best_new_issue_match = Mock(return_value=candidate_new_issues[0])

        modified_html, did_modify = self.service._find_and_replace_jira_macros_on_page(
            page_details=mock_page_details,
            html_content=mock_html_content,
            candidate_new_issues=candidate_new_issues,
            target_issue_type_ids=target_type_ids
        )

        self.assertTrue(did_modify)
        mock_jira_macro_tag.replace_with.assert_called_once()
        self.mock_jira_service.get_issue.assert_called_once_with("OLD-1", fields="issuetype,summary")
        self.service._find_best_new_issue_match.assert_called_once()
        
        self.assertIn("NEW-1", modified_html)
        self.assertIn("<ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">NEW-1</ac:parameter></ac:structured-macro>", modified_html)
        self.assertEqual(modified_html, self.mock_soup_instance.__str__.return_value)


    def test_find_and_replace_jira_macros_on_page_no_match(self):
        """Test _find_and_replace_jira_macros_on_page does not modify if no suitable new issue."""
        mock_html_content = (
            "<p><ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">OLD-1</ac:parameter></ac:structured-macro></p>"
        )
        mock_page_details = {"id": "page1", "title": "Test Page"}
        candidate_new_issues = [] # No candidates provided
        target_type_ids = {"10100"}

        # Configure mock_soup_instance for this test
        mock_jira_macro_tag = Mock()
        mock_jira_macro_tag.find.return_value.get_text.return_value = "OLD-1"
        self.mock_soup_instance.find_all.return_value = [mock_jira_macro_tag]
        # Simulate original HTML content being returned by str(soup)
        self.mock_soup_instance.__str__ = Mock(return_value=mock_html_content)
        
        self.mock_jira_service.get_issue.return_value = {
            "key": "OLD-1", 
            "fields": {"issuetype": {"id": "10100", "name": "Work Package"}, "summary": "Old Summary"}
        }
        self.service._find_best_new_issue_match = Mock(return_value=None) # No match returned

        modified_html, did_modify = self.service._find_and_replace_jira_macros_on_page(
            page_details=mock_page_details,
            html_content=mock_html_content,
            candidate_new_issues=candidate_new_issues,
            target_issue_type_ids=target_type_ids
        )

        self.assertFalse(did_modify)
        mock_jira_macro_tag.replace_with.assert_not_called()
        self.assertEqual(modified_html, mock_html_content)
        self.assertIn("OLD-1", modified_html)


    def test_update_confluence_hierarchy_with_new_jira_project_success(self):
        """Test high-level update_confluence_hierarchy_with_new_jira_project success path."""
        root_url = "http://mock.confluence.com/root"
        root_project_key = "PROJ-ROOT"
        
        self.mock_confluence_service.get_page_id_from_url.return_value = "root_page_id"
        self.mock_confluence_service.get_all_descendants.return_value = ["child_page_id"]

        mock_candidate_issues = [{"key": "NEW-PROJ", "fields": {"issuetype": {"id": "10200"}, "summary": "New Project Summary"}}]
        self.service._get_relevant_jira_issues_under_root = Mock(return_value=mock_candidate_issues)

        mock_page_details_root = {"id": "root_page_id", "title": "Root Page", "body": {"storage": {"value": "OLD-1 macro"}}}
        mock_page_details_child = {"id": "child_page_id", "title": "Child Page", "body": {"storage": {"value": "OLD-2 macro"}}}
        self.mock_confluence_service.get_page_by_id.side_effect = [
            mock_page_details_root,
            mock_page_details_child
        ]

        self.service._find_and_replace_jira_macros_on_page = Mock(side_effect=[
            ("MODIFIED_HTML_ROOT", True),
            ("MODIFIED_HTML_CHILD", False)
        ])
        self.mock_confluence_service.update_page_content.return_value = True

        results = self.service.update_confluence_hierarchy_with_new_jira_project(
            root_confluence_page_url=root_url,
            root_project_issue_key=root_project_key,
            project_issue_type_id="10200"
        )

        self.mock_confluence_service.get_page_id_from_url.assert_called_once_with(root_url)
        self.mock_confluence_service.get_all_descendants.assert_called_once_with("root_page_id")
        self.service._get_relevant_jira_issues_under_root.assert_called_once_with(
            root_project_key,
            {"10200", config.JIRA_PHASE_ISSUE_TYPE_ID, config.JIRA_WORK_PACKAGE_ISSUE_TYPE_ID}
        )
        self.assertEqual(self.mock_confluence_service.get_page_by_id.call_count, 2)
        self.assertEqual(self.service._find_and_replace_jira_macros_on_page.call_count, 2)
        self.mock_confluence_service.update_page_content.assert_called_once_with("root_page_id", "Root Page", "MODIFIED_HTML_ROOT")
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["page_id"], "root_page_id")
        self.assertEqual(results[0]["root_project_linked"], root_project_key)

    def test_update_confluence_hierarchy_invalid_url(self):
        """Test update_confluence_hierarchy_with_new_jira_project handles invalid URL."""
        self.mock_confluence_service.get_page_id_from_url.return_value = None
        self.service._get_relevant_jira_issues_under_root = Mock()

        with self.assertRaises(InvalidInputError):
            self.service.update_confluence_hierarchy_with_new_jira_project(
                root_confluence_page_url="invalid_url",
                root_project_issue_key="PROJ-ROOT"
            )
        self.mock_confluence_service.get_all_descendants.assert_not_called()
        self.service._get_relevant_jira_issues_under_root.assert_not_called()


    def test_update_confluence_hierarchy_no_candidates(self):
        """Test update_confluence_hierarchy_with_new_jira_project handles no candidates found."""
        root_url = "http://mock.confluence.com/root"
        root_project_key = "PROJ-ROOT"
        self.mock_confluence_service.get_page_id_from_url.return_value = "root_page_id"
        self.mock_confluence_service.get_all_descendants.return_value = []
        
        self.service._get_relevant_jira_issues_under_root = Mock(return_value=[])

        results = self.service.update_confluence_hierarchy_with_new_jira_project(
            root_confluence_page_url=root_url,
            root_project_issue_key=root_project_key
        )
        self.assertEqual(results, [])
        self.service._get_relevant_jira_issues_under_root.assert_called_once()
        self.mock_confluence_service.get_page_by_id.assert_not_called()

if __name__ == "__main__":
    unittest.main()