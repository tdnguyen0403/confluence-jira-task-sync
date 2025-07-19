import pytest
from unittest.mock import AsyncMock, patch
import logging

from src.api.safe_jira_api import SafeJiraApi
from src.api.https_helper import HTTPSHelper
from src.config import config  # Assuming config is used for JIRA_API_TOKEN

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
    with patch.object(config, "JIRA_API_TOKEN", "test_token"), patch.object(
        config, "JIRA_URL", "http://jira.example.com"
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
async def test_find_transition_id_by_name_found(safe_jira_api, mock_https_helper):
    """Tests finding transition ID by name when found."""
    mock_transitions = [{"id": "1", "name": "To Do"}, {"id": "2", "name": "Done"}]
    mock_https_helper.get.return_value = {"transitions": mock_transitions}

    transition_id = await safe_jira_api.find_transition_id_by_name("PROJ-1", "Done")

    assert transition_id == "2"
    mock_https_helper.get.assert_awaited_once()  # Call count is 1, URL is internal to the method


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
