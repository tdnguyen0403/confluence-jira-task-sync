import pytest
from unittest.mock import MagicMock, call
from src.services.business_logic.issue_finder_service import IssueFinderService
from src.config import config
import logging

logger = logging.getLogger(__name__)


@pytest.fixture  # Restored fixture decorator
def mock_confluence_api():
    mock = MagicMock()
    # Default mock page with multiple Jira macros
    mock.get_page_by_id.return_value = {
        "body": {
            "storage": {
                "value": (
                    "<p>Some content with a Jira macro:</p>"
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    '<ac:parameter ac:name="key">JIRA-TEST-WP</ac:parameter>'
                    "</ac:structured-macro>"
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    '<ac:parameter ac:name="key">JIRA-TEST-TASK</ac:parameter>'
                    "</ac:structured-macro>"
                )
            }
        }
    }
    return mock


@pytest.fixture  # Restored fixture decorator
def mock_jira_api():
    mock = MagicMock()

    # Define side_effect to handle different calls to get_issue
    def get_issue_side_effect(key, fields=None):
        # print(f"Mock Jira API called with key={key}, fields={fields}") # Debugging
        if key == "JIRA-TEST-WP":
            if fields == "issuetype":
                return {
                    "key": "JIRA-TEST-WP",
                    "fields": {
                        "issuetype": {
                            "id": config.PARENT_ISSUES_TYPE_ID["Work Package"],
                            "name": "Work Package",
                        }
                    },
                }
            else:  # For the full issue details call
                return {
                    "key": "JIRA-TEST-WP",
                    "fields": {
                        "issuetype": {
                            "id": config.PARENT_ISSUES_TYPE_ID["Work Package"],
                            "name": "Work Package",
                        },
                        "summary": "Test Work Package Summary",
                    },
                }
        elif key == "JIRA-TEST-TASK":
            if fields == "issuetype":
                return {
                    "key": "JIRA-TEST-TASK",
                    "fields": {"issuetype": {"id": "10002", "name": "Task"}},
                }
            else:
                return {
                    "key": "JIRA-TEST-TASK",
                    "fields": {
                        "issuetype": {"id": "10002", "name": "Task"},
                        "summary": "Test Task Summary",
                    },
                }
        elif key == "JIRA-ANOTHER-TYPE":
            if fields == "issuetype":
                return {
                    "key": "JIRA-ANOTHER-TYPE",
                    "fields": {"issuetype": {"id": "99999", "name": "Another Type"}},
                }
            else:
                return {
                    "key": "JIRA-ANOTHER-TYPE",
                    "fields": {
                        "issuetype": {"id": "99999", "name": "Another Type"},
                        "summary": "Another Type Summary",
                    },
                }
        elif key == "JIRA-NESTED":
            if fields == "issuetype":
                return {
                    "key": "JIRA-NESTED",
                    "fields": {
                        "issuetype": {
                            "id": config.PARENT_ISSUES_TYPE_ID["Work Package"],
                            "name": "Work Package",
                        }
                    },
                }
            else:
                return {
                    "key": "JIRA-NESTED",
                    "fields": {
                        "issuetype": {
                            "id": config.PARENT_ISSUES_TYPE_ID["Work Package"],
                            "name": "Work Package",
                        },
                        "summary": "Nested WP Summary",
                    },
                }
        elif key == "JIRA-VALID":
            if fields == "issuetype":
                return {
                    "key": "JIRA-VALID",
                    "fields": {
                        "issuetype": {
                            "id": config.PARENT_ISSUES_TYPE_ID["Work Package"],
                            "name": "Work Package",
                        }
                    },
                }
            else:
                return {
                    "key": "JIRA-VALID",
                    "fields": {
                        "issuetype": {
                            "id": config.PARENT_ISSUES_TYPE_ID["Work Package"],
                            "name": "Work Package",
                        },
                        "summary": "Valid WP Summary",
                    },
                }
        return None

    mock.get_issue.side_effect = get_issue_side_effect
    return mock


@pytest.fixture
def issue_finder_service(mock_confluence_api, mock_jira_api):
    # This fixture provides the service, but in the test_find_issue_on_page_success,
    # we will explicitly create the service instance to ensure mocks are correctly injected.
    return IssueFinderService(
        confluence_api=mock_confluence_api, jira_api=mock_jira_api
    )


@pytest.fixture
def test_find_issue_on_page_success(
    mock_confluence_api, mock_jira_api
):  # Now takes mocks as arguments from fixtures
    # Explicitly instantiate the service here to ensure it uses the mocks from fixtures
    issue_finder_service = IssueFinderService(
        confluence_api=mock_confluence_api, jira_api=mock_jira_api
    )

    # Ensure mock call lists are clean before the test action
    mock_confluence_api.reset_mock()  # Reset both mocks
    mock_jira_api.reset_mock()

    page_id = "test_page_id"
    issue_type_map = config.PARENT_ISSUES_TYPE_ID  # e.g., {"Work Package": "10100"}

    # Debugging: Print initial state of mocks
    # print(f"\nBefore find_issue_on_page: mock_confluence_api.call_args_list={mock_confluence_api.call_args_list}")
    # print(f"Before find_issue_on_page: mock_jira_api.call_args_list={mock_jira_api.call_args_list}")

    result = issue_finder_service.find_issue_on_page(page_id, issue_type_map)

    # Assert that the correct Jira issue (Work Package) is returned
    assert result is not None
    assert result["key"] == "JIRA-TEST-WP"
    mock_confluence_api.get_page_by_id.assert_called_once_with(
        page_id, expand="body.storage"
    )

    # Check individual calls for robustness.
    actual_calls = mock_jira_api.call_args_list
    # print(f"Actual Jira API calls after find_issue_on_page: {actual_calls}") # Debugging

    expected_call_1 = call("JIRA-TEST-WP", fields="issuetype")
    expected_call_2 = call("JIRA-TEST-WP", fields="key,issuetype,assignee,reporter")

    assert expected_call_1 in actual_calls
    assert expected_call_2 in actual_calls

    # Optionally, assert no other unexpected calls were made if strictly needed:
    # assert len(actual_calls) == 2


@pytest.fixture
def test_find_issue_on_page_no_content(issue_finder_service, mock_confluence_api):
    mock_confluence_api.get_page_by_id.return_value = None  # No content found

    result = issue_finder_service.find_issue_on_page(
        "test_page_id", config.PARENT_ISSUES_TYPE_ID
    )
    assert result is None
    mock_confluence_api.get_page_by_id.assert_called_once()


@pytest.fixture
def test_find_issue_on_page_no_jira_macros(issue_finder_service, mock_confluence_api):
    mock_confluence_api.get_page_by_id.return_value = {
        "body": {"storage": {"value": "<p>Content without Jira macros.</p>"}}
    }
    result = issue_finder_service.find_issue_on_page(
        "test_page_id", config.PARENT_ISSUES_TYPE_ID
    )
    assert result is None


@pytest.fixture
def test_find_issue_on_page_jira_macro_no_key(
    issue_finder_service, mock_confluence_api
):
    mock_confluence_api.get_page_by_id.return_value = {
        "body": {
            "storage": {
                "value": (
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    "</ac:structured-macro>"  # Missing key parameter
                )
            }
        }
    }
    result = issue_finder_service.find_issue_on_page(
        "test_page_id", config.PARENT_ISSUES_TYPE_ID
    )
    assert result is None


@pytest.fixture
def test_find_issue_on_page_jira_api_fails(
    issue_finder_service, mock_jira_api, mock_confluence_api
):
    # Ensure all calls to get_issue return None within this specific test
    mock_jira_api.get_issue.side_effect = lambda key, fields=None: None

    # Use a page content that has Jira macros to ensure the calls happen
    mock_confluence_api.get_page_by_id.return_value = {
        "body": {
            "storage": {
                "value": (
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    '<ac:parameter ac:name="key">JIRA-FAIL-TEST</ac:parameter>'
                    "</ac:structured-macro>"
                )
            }
        }
    }

    result = issue_finder_service.find_issue_on_page(
        "test_page_id", config.PARENT_ISSUES_TYPE_ID
    )
    assert result is None


@pytest.fixture
def test_find_issue_on_page_no_matching_issue_type(issue_finder_service, mock_jira_api):
    # The fixture's side_effect already handles "JIRA-ANOTHER-TYPE"
    # Ensure page has this specific type
    mock_confluence_api = MagicMock()
    mock_confluence_api.get_page_by_id.return_value = {
        "body": {
            "storage": {
                "value": (
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    '<ac:parameter ac:name="key">JIRA-ANOTHER-TYPE</ac:parameter>'
                    "</ac:structured-macro>"
                )
            }
        }
    }

    service = IssueFinderService(
        confluence_api=mock_confluence_api, jira_api=mock_jira_api
    )
    result = service.find_issue_on_page("test_page_id", config.PARENT_ISSUES_TYPE_ID)
    assert result is None


@pytest.fixture
def test_find_issue_on_page_nested_macro_ignored(
    issue_finder_service, mock_confluence_api, mock_jira_api, monkeypatch
):
    # Mock page content with a Jira macro nested inside an ignored aggregation macro
    # This specifically tests the 'find_parent' logic
    mock_confluence_api.get_page_by_id.return_value = {
        "body": {
            "storage": {
                "value": (
                    '<ac:structured-macro ac:name="jira-issues" ac:schema-version="1">'  # An aggregation macro (from config.AGGREGATION_CONFLUENCE_MACRO)
                    '<ac:parameter ac:name="jql">project = ABC</ac:parameter>'
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    '<ac:parameter ac:name="key">JIRA-NESTED</ac:parameter>'  # This one should be ignored
                    "</ac:structured-macro>"
                    "</ac:structured-macro>"
                    '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
                    '<ac:parameter ac:name="key">JIRA-VALID</ac:parameter>'  # This one should be found
                    "</ac:structured-macro>"
                )
            }
        }
    }
    # AGGREGATION_CONFLUENCE_MACRO needs to be properly set in config for this test
    # Use the monkeypatch fixture provided by pytest
    monkeypatch.setattr(config, "AGGREGATION_CONFLUENCE_MACRO", {"jira-issues"})

    result = issue_finder_service.find_issue_on_page(
        "test_page_id", config.PARENT_ISSUES_TYPE_ID
    )
    assert result is not None
    assert result["key"] == "JIRA-VALID"  # Should find the non-nested one
