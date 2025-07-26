import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.api.https_helper import HTTPSHelper, HTTPXCustomError
from src.api.safe_jira_api import SafeJiraApi
from src.config import config  # Assuming config is used for JIRA_API_TOKEN
from src.exceptions import JiraApiError

# Configure logging to capture messages during tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_https_helper():
    """Provides an AsyncMock for HTTPSHelper."""
    return AsyncMock(spec=HTTPSHelper)


@pytest.fixture
def safe_jira_api(mock_https_helper):
    """Provides a SafeJiraApi instance with a mocked HTTPSHelper."""
    # Patch config.JIRA_API_TOKEN and config.JIRA_URL for testing purposes
    with (
        patch.object(config, "JIRA_API_TOKEN", "test_token"),
        patch.object(config, "JIRA_URL", "http://jira.example.com"),
    ):
        return SafeJiraApi(
            base_url="http://jira.example.com", https_helper=mock_https_helper
        )


@pytest.mark.asyncio
async def test_get_issue_success(safe_jira_api, mock_https_helper):
    """Tests successful retrieval of a Jira issue."""
    mock_https_helper.get.return_value = {
        "id": "1",
        "key": "PROJ-1",
        "fields": {"summary": "Test Issue"},
    }

    issue = await safe_jira_api.get_issue("PROJ-1", fields=["summary"])

    assert issue["key"] == "PROJ-1"
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issue/PROJ-1",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
        params={"fields": "summary"},
    )


@pytest.mark.asyncio
async def test_create_issue_success(safe_jira_api, mock_https_helper):
    """Tests successful creation of a Jira issue."""
    mock_https_helper.post.return_value = {"id": "2", "key": "PROJ-2"}

    fields = {"project": {"key": "PROJ"}, "summary": "New Task"}
    new_issue = await safe_jira_api.create_issue(fields)

    assert new_issue["key"] == "PROJ-2"
    mock_https_helper.post.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issue",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
        json_data={"fields": fields},
    )


@pytest.mark.asyncio
async def test_get_available_transitions_success(safe_jira_api, mock_https_helper):
    """Tests successful retrieval of available transitions."""
    mock_transitions = [{"id": "1", "name": "To Do"}, {"id": "2", "name": "Done"}]
    mock_https_helper.get.return_value = {"transitions": mock_transitions}

    transitions = await safe_jira_api.get_available_transitions("PROJ-1")

    assert transitions == mock_transitions
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issue/PROJ-1/transitions",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
    )


@pytest.mark.asyncio
async def test_find_transition_id_by_name_found(safe_jira_api, mocker):
    """Tests finding transition ID by name when found."""
    mock_transitions = [{"id": "1", "name": "To Do"}, {"id": "2", "name": "Done"}]

    # Use mocker to patch the 'get_available_transitions' method directly
    # on the instance provided by the fixture. This is the most reliable way.
    mocked_method = mocker.patch.object(
        safe_jira_api,
        "get_available_transitions",
        new_callable=AsyncMock,
        return_value=mock_transitions,
    )

    # Now, when the method under test is called, it will use our mock.
    transition_id = await safe_jira_api.find_transition_id_by_name("PROJ-1", "Done")

    assert transition_id == "2"
    # Verify the mocked method was called correctly.
    mocked_method.assert_awaited_once_with("PROJ-1")


@pytest.mark.asyncio
async def test_find_transition_id_by_name_not_found(safe_jira_api, mock_https_helper):
    """Tests finding transition ID by name when not found."""
    mock_transitions = [{"id": "1", "name": "To Do"}]
    mock_https_helper.get.return_value = {"transitions": mock_transitions}

    transition_id = await safe_jira_api.find_transition_id_by_name(
        "PROJ-1", "In Progress"
    )

    assert transition_id is None
    mock_https_helper.get.assert_awaited_once()  # Call count is 1, URL is internal to the method


@pytest.mark.asyncio
async def test_transition_issue_success(safe_jira_api, mock_https_helper):
    """Tests successful issue transition."""
    # Mock for get_available_transitions (called by find_transition_id_by_name)
    mock_https_helper.get.return_value = {"transitions": [{"id": "1", "name": "Done"}]}
    # Mock for post (transition execution)
    mock_https_helper.post.return_value = {}  # 204 No Content

    response = await safe_jira_api.transition_issue("PROJ-1", "Done")

    assert response == {}
    assert mock_https_helper.get.call_count == 1  # Called by find_transition_id_by_name
    mock_https_helper.post.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issue/PROJ-1/transitions",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
        json_data={"transition": {"id": "1"}},
    )


@pytest.mark.asyncio
async def test_transition_issue_no_transition_found(safe_jira_api, mock_https_helper):
    """Tests transition_issue when target transition is not found."""
    mock_https_helper.get.return_value = {
        "transitions": [{"id": "1", "name": "To Do"}]
    }  # Only one transition

    with pytest.raises(
        ValueError, match="Transition 'NonExistent' not found for issue PROJ-1"
    ):
        await safe_jira_api.transition_issue("PROJ-1", "NonExistent")

    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.post.assert_not_awaited()  # Should not attempt to post


@pytest.mark.asyncio
async def test_get_current_user_success(safe_jira_api, mock_https_helper):
    """Tests successful retrieval of current user details."""
    mock_user_data = {"accountId": "123", "displayName": "Test User"}
    mock_https_helper.get.return_value = mock_user_data

    user_details = await safe_jira_api.get_current_user()

    assert user_details == mock_user_data
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/myself",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
    )


@pytest.mark.asyncio
async def test_search_issues_success(safe_jira_api, mock_https_helper):
    """Tests successful JQL search for issues."""
    mock_search_results = {
        "issues": [{"key": "PROJ-1", "fields": {"summary": "Issue 1"}}]
    }
    mock_https_helper.get.return_value = mock_search_results

    results = await safe_jira_api.search_issues("project = PROJ", fields=["summary"])

    assert results == mock_search_results
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/search",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
        params={"jql": "project = PROJ", "fields": "summary"},
    )


@pytest.mark.asyncio
async def test_get_issue_type_details_by_id_success(safe_jira_api, mock_https_helper):
    """Tests successful retrieval of issue type details."""
    mock_issue_type_details = {"id": "10001", "name": "Task"}
    mock_https_helper.get.return_value = mock_issue_type_details

    details = await safe_jira_api.get_issue_type_details_by_id("10001")

    assert details == mock_issue_type_details
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issuetype/10001",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
    )


@pytest.mark.asyncio
async def test_update_issue_description_success(safe_jira_api, mock_https_helper):
    """Tests successful update of issue description."""
    mock_https_helper.put.return_value = {}  # 204 No Content

    new_description = "Updated description text."
    response = await safe_jira_api.update_issue_description("PROJ-1", new_description)

    assert response == {}
    mock_https_helper.put.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issue/PROJ-1",  # URL matches fixture's base_url
        headers=safe_jira_api.headers,
        json_data={"fields": {"description": new_description}},
    )


@pytest.mark.asyncio
async def test_get_issue_error_handling(safe_jira_api, mock_https_helper):
    """Tests get_issue when https_helper.get raises an exception."""
    mock_https_helper.get.side_effect = Exception("Simulated network error")
    with pytest.raises(Exception, match="Simulated network error"):
        await safe_jira_api.get_issue("PROJ-FAIL")
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_issue_error_handling(safe_jira_api, mock_https_helper):
    """Tests create_issue when https_helper.post raises an exception."""
    mock_https_helper.post.side_effect = Exception("Failed to connect")
    fields = {"project": {"key": "PROJ"}, "summary": "Error Issue"}
    with pytest.raises(Exception, match="Failed to connect"):
        await safe_jira_api.create_issue(fields)
    mock_https_helper.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_available_transitions_error_handling(
    safe_jira_api, mock_https_helper
):
    """Tests get_available_transitions when https_helper.get raises an exception."""
    mock_https_helper.get.side_effect = Exception("API unavailable")
    with pytest.raises(Exception, match="API unavailable"):
        await safe_jira_api.get_available_transitions("PROJ-ERR")
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_transition_issue_error_handling(safe_jira_api, mock_https_helper):
    """Tests transition_issue when https_helper.post raises an exception."""
    # First, find_transition_id_by_name will call get, which should succeed
    mock_https_helper.get.return_value = {"transitions": [{"id": "1", "name": "Done"}]}
    # Then, the post call for transition_issue should fail
    mock_https_helper.post.side_effect = Exception("Transition failed on server")

    with pytest.raises(Exception, match="Transition failed on server"):
        await safe_jira_api.transition_issue("PROJ-TRANSITION-FAIL", "Done")
    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_error_handling(safe_jira_api, mock_https_helper):
    """Tests get_current_user when https_helper.get raises an exception."""
    mock_https_helper.get.side_effect = Exception("Authentication error")
    with pytest.raises(Exception, match="Authentication error"):
        await safe_jira_api.get_current_user()
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_issues_no_fields(safe_jira_api, mock_https_helper):
    """Tests search_issues without providing fields parameter."""
    mock_search_results = {
        "issues": [{"key": "PROJ-2", "fields": {"summary": "Issue 2"}}]
    }
    mock_https_helper.get.return_value = mock_search_results

    results = await safe_jira_api.search_issues("project = PROJ AND status = Done")

    assert results == mock_search_results
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/search",
        headers=safe_jira_api.headers,
        params={
            "jql": "project = PROJ AND status = Done"
        },  # No 'fields' parameter should be here
    )


@pytest.mark.asyncio
async def test_search_issues_error_handling(safe_jira_api, mock_https_helper):
    """Tests search_issues when https_helper.get raises an exception."""
    mock_https_helper.get.side_effect = Exception("JQL query invalid")
    with pytest.raises(Exception, match="JQL query invalid"):
        await safe_jira_api.search_issues("invalid JQL")
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_issue_type_details_by_id_error_handling(
    safe_jira_api, mock_https_helper
):
    """Tests get_issue_type_details_by_id when the API call fails."""
    # Simulate a realistic error from the lower layer.
    mock_https_helper.get.side_effect = HTTPXCustomError("API call failed")

    # The correct behavior is now to raise a JiraApiError. We assert this.
    with pytest.raises(JiraApiError) as excinfo:
        await safe_jira_api.get_issue_type_details_by_id("nonexistent_id")

    # Verify the exception contains the original error message.
    assert "API call failed" in str(excinfo.value)


@pytest.mark.asyncio
async def test_update_issue_description_error_handling(
    safe_jira_api, mock_https_helper
):
    """Tests update_issue_description when https_helper.put raises an exception."""
    mock_https_helper.put.side_effect = Exception("Update failed")
    with pytest.raises(Exception, match="Update failed"):
        await safe_jira_api.update_issue_description(
            "PROJ-UPDATE-FAIL", "New description"
        )
    mock_https_helper.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_issue_type_details_by_id_success_empty_response(
    safe_jira_api, mock_https_helper
):
    """Tests get_issue_type_details_by_id with a successful but empty API response."""
    # Simulate a successful call (200 OK) but with an empty dictionary
    mock_https_helper.get.return_value = {}

    details = await safe_jira_api.get_issue_type_details_by_id("10001")

    # The method should return the empty dict without raising an error
    assert details == {}
    mock_https_helper.get.assert_awaited_once_with(
        "http://jira.example.com/rest/api/2/issuetype/10001",
        headers=safe_jira_api.headers,
    )


@pytest.mark.asyncio
async def test_assign_issue_success(safe_jira_api, mock_https_helper):
    """Tests successful assignment of a Jira issue to a user."""
    mock_https_helper.put.return_value = {}  # Jira typically returns 204 No Content

    issue_key = "PROJ-123"
    assignee_name = "test_user"
    response = await safe_jira_api.assign_issue(issue_key, assignee_name)

    assert response == {}
    mock_https_helper.put.assert_awaited_once_with(
        f"http://jira.example.com/rest/api/2/issue/{issue_key}/assignee",
        headers=safe_jira_api.headers,
        json_data={"name": assignee_name},
    )


@pytest.mark.asyncio
async def test_assign_issue_unassign_success(safe_jira_api, mock_https_helper):
    """Tests successful unassignment of a Jira issue."""
    mock_https_helper.put.return_value = {}  # Jira typically returns 204 No Content

    issue_key = "PROJ-456"
    response = await safe_jira_api.assign_issue(issue_key, None)

    assert response == {}
    mock_https_helper.put.assert_awaited_once_with(
        f"http://jira.example.com/rest/api/2/issue/{issue_key}/assignee",
        headers=safe_jira_api.headers,
        json_data={"name": None},
    )


@pytest.mark.asyncio
async def test_assign_issue_error_handling(safe_jira_api, mock_https_helper):
    """Tests assign_issue when https_helper.put raises an exception."""
    mock_https_helper.put.side_effect = Exception("Permission denied")

    issue_key = "PROJ-789"
    assignee_name = "forbidden_user"
    with pytest.raises(Exception, match="Permission denied"):
        await safe_jira_api.assign_issue(issue_key, assignee_name)

    mock_https_helper.put.assert_awaited_once_with(
        f"http://jira.example.com/rest/api/2/issue/{issue_key}/assignee",
        headers=safe_jira_api.headers,
        json_data={"name": assignee_name},
    )
