import pytest
import requests
import logging  # Needed for caplog.at_level
from atlassian import Jira
from unittest.mock import MagicMock, Mock

# Adjust path as necessary based on your project structure
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.api.safe_jira_api import SafeJiraApi
from src.config import config  # Needed for patching config values
# Import default_make_request for the fixture, as per DIP change 3

# --- Fixtures for SafeJiraApi Tests ---


@pytest.fixture
def mock_jira_client(mocker):
    """Fixture for a mocked atlassian.Jira client."""
    mock_client = mocker.MagicMock(spec=Jira)
    return mock_client


@pytest.fixture
def mock_config_values(monkeypatch):
    """Fixture for patching config values that SafeJiraApi directly accesses."""
    monkeypatch.setattr(config, "JIRA_URL", "https://mock.jira.com")
    monkeypatch.setattr(config, "JIRA_API_TOKEN", "mock_token")
    # New config variable name: VERIFY_SSL
    monkeypatch.setattr(
        config, "VERIFY_SSL", False
    )  # Set to False for test consistency


@pytest.fixture
def mock_make_request(mocker):
    return mocker.patch("src.api.safe_jira_api.make_request")


@pytest.fixture
def safe_jira_api_instance(mock_jira_client, mock_config_values):
    """Fixture to provide an instance of SafeJiraApi with mocked dependencies."""
    # Pass mock_make_request as request_maker due to DIP (Change 3)
    return SafeJiraApi(jira_client=mock_jira_client)


# --- Tests for SafeJiraApi ---


def test_safe_jira_api_init(safe_jira_api_instance, mock_jira_client):
    """Test SafeJiraApi initialization."""
    assert safe_jira_api_instance.client is mock_jira_client
    assert safe_jira_api_instance.base_url == "https://mock.jira.com"
    assert "Authorization" in safe_jira_api_instance.headers
    assert "Content-Type" in safe_jira_api_instance.headers


# Test get_issue and its fallbacks
@pytest.mark.parametrize(
    "issue_key, client_side_effect, make_request_return_value, expected_log_msg_fragment, expected_return",
    [
        # issue_key, client_side_effect, make_request_return_value, expected_log_msg_fragment, expected_return
        ("TEST-1", None, None, None, {"key": "TEST-1", "id": "10001"}),
        (
            "TEST-2",
            requests.exceptions.RequestException("Network error"),
            MagicMock(json=lambda: {"key": "FB-2"}, status_code=200),
            "A network error occurred while getting issue 'TEST-2'",
            {"key": "FB-2"},
        ),
        (
            "TEST-3",
            Exception("Generic library error"),
            MagicMock(json=lambda: {"key": "FB-3"}, status_code=200),
            "Library get_issue for 'TEST-3' failed",
            {"key": "FB-3"},
        ),
        (
            "TEST-4",
            requests.exceptions.RequestException("Network error"),
            None,
            "A network error occurred while getting issue 'TEST-4'",
            None,
        ),
        (
            "TEST-5",
            Exception("Generic library error"),
            None,
            "Library get_issue for 'TEST-5' failed",
            None,
        ),
    ],
)
def test_get_issue_resilience(
    safe_jira_api_instance,
    mock_jira_client,
    mock_make_request,
    caplog,
    issue_key,  # Corrected: now a direct parameter
    client_side_effect,
    make_request_return_value,
    expected_log_msg_fragment,
    expected_return,
):
    fields = "*all"

    if client_side_effect:
        mock_jira_client.get_issue.side_effect = client_side_effect
    else:
        mock_jira_client.get_issue.return_value = expected_return

    mock_make_request.return_value = make_request_return_value

    with caplog.at_level(logging.WARNING):
        result = safe_jira_api_instance.get_issue(issue_key, fields=fields)

        assert result == expected_return
        mock_jira_client.get_issue.assert_called_once_with(issue_key, fields=fields)

        if client_side_effect:
            mock_make_request.assert_called_once_with(
                "GET",
                f"{safe_jira_api_instance.base_url}/rest/api/2/issue/{issue_key}?fields=*all",
                headers=safe_jira_api_instance.headers,
                verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
            )
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# Test create_issue resilience
@pytest.mark.parametrize(
    "client_side_effect, make_request_return_value, expected_return_value, expected_log_msg_fragment",
    [
        (None, None, {"key": "NEW-1"}, None),
        (
            requests.exceptions.RequestException("Network error"),
            MagicMock(json=lambda: {"key": "FB-NEW-2"}, status_code=200),
            {"key": "FB-NEW-2"},
            "A network error occurred while creating issue",
        ),
        (
            Exception("Generic error"),
            MagicMock(json=lambda: {"key": "FB-NEW-3"}, status_code=200),
            {"key": "FB-NEW-3"},
            "Library create_issue failed",
        ),
        (
            requests.exceptions.RequestException("Network error"),
            None,
            None,
            "A network error occurred while creating issue",
        ),
        (Exception("Generic error"), None, None, "Library create_issue failed"),
    ],
)
def test_create_issue_resilience(
    safe_jira_api_instance,
    mock_jira_client,
    mock_make_request,
    caplog,
    client_side_effect,
    make_request_return_value,
    expected_return_value,
    expected_log_msg_fragment,
):
    issue_fields_payload = {"fields": {"summary": "Test Issue"}}

    if client_side_effect:
        mock_jira_client.issue_create.side_effect = client_side_effect
    else:
        mock_jira_client.issue_create.return_value = expected_return_value

    mock_make_request.return_value = make_request_return_value

    with caplog.at_level(logging.WARNING):
        result = safe_jira_api_instance.create_issue(issue_fields_payload)

        assert result == expected_return_value
        mock_jira_client.issue_create.assert_called_once_with(
            fields=issue_fields_payload["fields"]
        )

        if client_side_effect:
            mock_make_request.assert_called_once_with(
                "POST",
                f"{safe_jira_api_instance.base_url}/rest/api/2/issue",
                headers=safe_jira_api_instance.headers,
                json_data=issue_fields_payload,
                verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
            )
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# New Tests for find_transition_id_by_name
def test_find_transition_id_by_name_success(safe_jira_api_instance, mock_make_request):
    """Test finding transition ID successfully."""
    mock_make_request.return_value = MagicMock(
        json=lambda: {
            "transitions": [
                {"id": "1", "name": "Open", "to": {"name": "Open"}},
                {"id": "2", "name": "In Progress", "to": {"name": "In Progress"}},
                {"id": "3", "name": "Done", "to": {"name": "Done"}},
            ]
        },
        status_code=200,
    )

    assert safe_jira_api_instance.find_transition_id_by_name("ISSUE-1", "done") == "3"
    assert (
        safe_jira_api_instance.find_transition_id_by_name("ISSUE-1", "In PRogress")
        == "2"
    )
    assert mock_make_request.call_count == 2  # Called twice for two checks


def test_find_transition_id_by_name_not_found(
    safe_jira_api_instance, mock_make_request, caplog
):
    """Test finding transition ID when target status is not available."""
    mock_make_request.return_value = MagicMock(
        json=lambda: {
            "transitions": [{"id": "1", "name": "Open", "to": {"name": "Open"}}]
        },
        status_code=200,
    )

    with caplog.at_level(logging.ERROR):
        assert (
            safe_jira_api_instance.find_transition_id_by_name("ISSUE-2", "Closed")
            is None
        )
        assert (
            "Transition to status 'Closed' not available for issue 'ISSUE-2'."
            in caplog.text
        )
        assert caplog.records[0].levelname == "ERROR"


def test_find_transition_id_by_name_no_transitions_api_failure(
    safe_jira_api_instance, mock_make_request, caplog
):
    """Test finding transition ID when no transitions are available due to API failure."""
    mock_make_request.return_value = None  # Simulate make_request returning None

    with caplog.at_level(logging.ERROR):
        assert (
            safe_jira_api_instance.find_transition_id_by_name("ISSUE-3", "Done") is None
        )
        assert (
            "Transition to status 'Done' not available for issue 'ISSUE-3'."
            in caplog.text
        )


# Test get_available_transitions failure directly
def test_get_available_transitions_api_failure(
    safe_jira_api_instance, mock_make_request
):
    """Test get_available_transitions returns empty list on API failure."""
    mock_make_request.return_value = None
    transitions = safe_jira_api_instance.get_available_transitions("TEST-FAIL")
    assert transitions == []
    mock_make_request.assert_called_once_with(
        "GET",
        f"{safe_jira_api_instance.base_url}/rest/api/2/issue/TEST-FAIL/transitions",
        headers=safe_jira_api_instance.headers,
        verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
    )


# Test transition_issue (Change 1: Bug Fix Verification & Change 2: verify_ssl assertion)
@pytest.mark.parametrize(
    "issue_key, client_side_effect, find_transition_id_return, make_request_return_value, expected_return_value, expected_log_msg_fragment",
    [
        ("TEST-1", None, "31", True, True, None),  # Primary success
        (
            "TEST-2",
            requests.exceptions.RequestException("Network error"),
            "31",
            MagicMock(raise_for_status=Mock(), status_code=204),
            True,
            "A network error occurred while transitioning issue",
        ),  # Library network error, fallback success
        (
            "TEST-3",
            Exception("Generic lib error"),
            "31",
            MagicMock(raise_for_status=Mock(), status_code=204),
            True,
            "Library transition for 'TEST-3' failed",
        ),  # Change 1: Verifies bug fix
        (
            "TEST-4",
            requests.exceptions.RequestException("Network error"),
            "31",
            None,
            False,
            "A network error occurred while transitioning issue",
        ),  # Library network error, fallback failure
        (
            "TEST-5",
            Exception("Generic lib error"),
            "31",
            None,
            False,
            "Library transition for 'TEST-5' failed",
        ),  # Change 1: Verifies bug fix, total failure
        (
            "TEST-6",
            None,
            None,
            None,
            False,
            None,
        ),  # No transition ID found (handled by `if not find_transition_id_return`)
    ],
)
def test_transition_issue_resilience(
    safe_jira_api_instance,
    mock_jira_client,
    mock_make_request,
    caplog,
    issue_key,  # Corrected: now a direct parameter
    client_side_effect,
    find_transition_id_return,
    make_request_return_value,
    expected_return_value,
    expected_log_msg_fragment,
):
    target_status = "Done"

    # Mock find_transition_id_by_name for all scenarios
    safe_jira_api_instance.find_transition_id_by_name = Mock(
        return_value=find_transition_id_return
    )

    if not find_transition_id_return:  # If no transition ID found, early exit
        result = safe_jira_api_instance.transition_issue(issue_key, target_status)
        assert result == expected_return_value
        safe_jira_api_instance.find_transition_id_by_name.assert_called_once_with(
            issue_key, target_status
        )
        mock_jira_client.issue_transition.assert_not_called()
        mock_make_request.assert_not_called()
        return  # End test here for this scenario

    # Continue with scenarios where transition_id is found
    if client_side_effect:
        mock_jira_client.issue_transition.side_effect = client_side_effect
    else:
        mock_jira_client.issue_transition.return_value = expected_return_value

    mock_make_request.return_value = make_request_return_value

    with caplog.at_level(logging.WARNING):
        result = safe_jira_api_instance.transition_issue(issue_key, target_status)

        assert result == expected_return_value
        safe_jira_api_instance.find_transition_id_by_name.assert_called_once_with(
            issue_key, target_status
        )
        mock_jira_client.issue_transition.assert_called_once_with(
            issue_key, target_status
        )

        if client_side_effect:  # This block covers fallback scenarios
            mock_make_request.assert_called_once_with(
                "POST",
                f"{safe_jira_api_instance.base_url}/rest/api/2/issue/{issue_key}/transitions",
                headers=safe_jira_api_instance.headers,
                json_data={"transition": {"id": find_transition_id_return}},
                verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
            )
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# Test search_issues (Change 6: Direct API Only & Change 2: verify_ssl assertion)
@pytest.mark.parametrize(
    "make_request_return_value, expected_return_value",
    [
        (
            MagicMock(
                json=lambda: {
                    "issues": [
                        {
                            "key": "SEARCH-1",
                            "id": "100",
                            "fields": {"summary": "Issue 1"},
                        }
                    ]
                },
                status_code=200,
            ),
            [{"key": "SEARCH-1", "id": "100", "fields": {"summary": "Issue 1"}}],
        ),
        (
            MagicMock(json=lambda: {"issues": []}, status_code=200),
            [],
        ),  # No issues found
        (None, []),  # make_request fails (returns None)
    ],
)
def test_search_issues_direct_api_call(
    safe_jira_api_instance,
    mock_make_request,
    make_request_return_value,
    expected_return_value,
):
    jql_query = "project = TEST AND status = Open"
    fields = "key,id,fields.summary"

    mock_make_request.return_value = make_request_return_value

    result = safe_jira_api_instance.search_issues(jql_query, fields=fields)

    assert result == expected_return_value
    # Change 6: Verify that the Jira client's jql method was NOT called
    safe_jira_api_instance.client.jql.assert_not_called()
    # Verify make_request was called correctly for the direct API
    quoted_jql = requests.utils.quote(jql_query)
    mock_make_request.assert_called_once_with(
        "GET",
        f"{safe_jira_api_instance.base_url}/rest/api/2/search?jql={quoted_jql}&fields={fields}",
        headers=safe_jira_api_instance.headers,
        verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
    )


# Test get_myself (Change 2: verify_ssl assertion)
@pytest.mark.parametrize(
    "make_request_return_value, expected_return_value",
    [
        (
            MagicMock(
                json=lambda: {"displayName": "Test User", "accountId": "123"},
                status_code=200,
            ),
            {"displayName": "Test User", "accountId": "123"},
        ),
        (None, None),  # Simulate failure
    ],
)
def test_get_myself(
    safe_jira_api_instance,
    mock_make_request,
    make_request_return_value,
    expected_return_value,
):
    mock_make_request.return_value = make_request_return_value
    result = safe_jira_api_instance.get_myself()
    assert result == expected_return_value
    mock_make_request.assert_called_once_with(
        "GET",
        f"{safe_jira_api_instance.base_url}/rest/api/2/myself",
        headers=safe_jira_api_instance.headers,
        verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
    )


# Test get_issue_type_details_by_id (Change 2: verify_ssl assertion)
@pytest.mark.parametrize(
    "make_request_return_value, expected_return_value",
    [
        (
            MagicMock(json=lambda: {"id": "1", "name": "Task"}, status_code=200),
            {"id": "1", "name": "Task"},
        ),
        (None, None),
    ],
)
def test_get_issue_type_details_by_id(
    safe_jira_api_instance,
    mock_make_request,
    make_request_return_value,
    expected_return_value,
    caplog,
):
    issue_type_id = "999"
    mock_make_request.return_value = make_request_return_value
    result = safe_jira_api_instance.get_issue_type_details_by_id(issue_type_id)
    assert result == expected_return_value
    mock_make_request.assert_called_once_with(
        "GET",
        f"{safe_jira_api_instance.base_url}/rest/api/2/issuetype/{issue_type_id}",
        headers=safe_jira_api_instance.headers,
        verify_ssl=config.VERIFY_SSL,  # Change 2: Assert verify_ssl
    )
    assert not caplog.records  # Should be no logs from this method
