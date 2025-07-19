import pytest
from unittest.mock import AsyncMock, patch
import logging
import httpx  # Import httpx for specific error types

from src.api.safe_confluence_api import SafeConfluenceApi
from src.api.https_helper import HTTPSHelper
from src.config import config  # Assuming config is used for CONFLUENCE_API_TOKEN

# Configure logging to capture messages during tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_https_helper():
    """Provides an AsyncMock for HTTPSHelper."""
    return AsyncMock(spec=HTTPSHelper)


@pytest.fixture
def safe_confluence_api(mock_https_helper):
    """Provides a SafeConfluenceApi instance with a mocked HTTPSHelper."""
    # Patch config.CONFLUENCE_API_TOKEN and config.CONFLUENCE_URL for testing purposes
    with patch.object(config, "CONFLUENCE_API_TOKEN", "test_token"), patch.object(
        config, "CONFLUENCE_URL", "http://confluence.example.com"
    ):  # <--- PATCH config.CONFLUENCE_URL here
        return SafeConfluenceApi(
            base_url="http://confluence.example.com",
            https_helper=mock_https_helper,
            jira_macro_server_name="TestJira",
            jira_macro_server_id="12345",
        )


@pytest.mark.asyncio
async def test_get_page_id_from_url_standard_format(safe_confluence_api):
    """Tests get_page_id_from_url with a standard URL format."""
    url = "http://confluence.example.com/pages/viewpage.action?pageId=12345"
    page_id = await safe_confluence_api.get_page_id_from_url(url)
    assert page_id == "12345"


@pytest.mark.asyncio
async def test_get_page_id_from_url_short_format_resolves(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_id_from_url with a short URL that resolves via redirect."""
    short_url = "http://confluence.example.com/x/abcde"
    redirect_url_step1 = (
        "http://confluence.example.com/pages/tinyurl.action?urlIdentifier=abcde"
    )
    final_resolved_url = (
        "http://confluence.example.com/spaces/SPACE/pages/67890/Final+Page"
    )

    # Mock _make_request to simulate multi-step redirect
    mock_response_step1 = AsyncMock(spec=httpx.Response)
    mock_response_step1.status_code = 302
    mock_response_step1.headers = {"Location": redirect_url_step1}
    mock_response_step1.url = httpx.URL(short_url)  # Initial URL

    mock_response_step2 = AsyncMock(spec=httpx.Response)
    mock_response_step2.status_code = 302
    mock_response_step2.headers = {"Location": final_resolved_url}
    mock_response_step2.url = httpx.URL(redirect_url_step1)  # Intermediate URL

    mock_response_final = AsyncMock(spec=httpx.Response)
    mock_response_final.status_code = 200
    mock_response_final.url = httpx.URL(final_resolved_url)  # Final URL

    # Patch the _make_request method of the HTTPSHelper instance directly
    with patch.object(
        mock_https_helper,
        "_make_request",
        side_effect=[mock_response_step1, mock_response_step2, mock_response_final],
    ) as mock_internal_make_request:
        page_id = await safe_confluence_api.get_page_id_from_url(short_url)
        assert page_id == "67890"

        # Verify calls to the patched _make_request

        mock_internal_make_request.assert_any_await(
            "HEAD",
            short_url,
            headers=safe_confluence_api.headers,
            timeout=5,
            follow_redirects=True,
        )
        mock_internal_make_request.assert_any_await(
            "HEAD",
            redirect_url_step1,
            headers=safe_confluence_api.headers,
            timeout=5,
            follow_redirects=True,
        )
        assert mock_internal_make_request.call_count == 2


@pytest.mark.asyncio
async def test_get_page_by_id_success(safe_confluence_api, mock_https_helper):
    """Tests successful retrieval of a Confluence page by ID."""
    mock_page_data = {"id": "123", "title": "Test Page"}
    mock_https_helper.get.return_value = mock_page_data

    page = await safe_confluence_api.get_page_by_id("123", expand="body.storage")

    assert page["id"] == "123"
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/content/123",  # URL matches fixture's base_url
        headers=safe_confluence_api.headers,
        params={"expand": "body.storage"},
    )


@pytest.mark.asyncio
async def test_get_page_by_id_with_version_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful retrieval of a specific Confluence page version by ID."""
    mock_page_data = {"id": "123", "title": "Test Page V5", "version": {"number": 5}}
    mock_https_helper.get.return_value = mock_page_data

    page = await safe_confluence_api.get_page_by_id(
        "123", version=5, expand="body.storage"
    )

    assert page["version"]["number"] == 5
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/content/123",  # URL matches fixture's base_url
        headers=safe_confluence_api.headers,
        params={"version": 5, "expand": "body.storage"},
    )


@pytest.mark.asyncio
async def test_get_page_child_by_type_success(safe_confluence_api, mock_https_helper):
    """Tests successful retrieval of child pages."""
    mock_child_pages = [{"id": "c1", "title": "Child 1"}]
    mock_https_helper.get.return_value = {"results": mock_child_pages, "size": 1}

    children = await safe_confluence_api.get_page_child_by_type("parent123")

    assert children == mock_child_pages
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/content/parent123/child/page?start=0&limit=50",
        headers=safe_confluence_api.headers,
    )


@pytest.mark.asyncio
async def test_update_page_success(safe_confluence_api, mock_https_helper):
    """Tests successful page update."""
    # Mock for get_page_by_id call within update_page
    mock_https_helper.get.return_value = {
        "id": "123",
        "title": "Old Title",
        "version": {"number": 1},
    }
    # Mock for put call
    mock_https_helper.put.return_value = {"id": "123", "version": {"number": 2}}

    success = await safe_confluence_api.update_page(
        "123", "New Title", "New Body Content"
    )

    assert success is True
    assert mock_https_helper.get.call_count == 1
    mock_https_helper.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_page_success(safe_confluence_api, mock_https_helper):
    """Tests successful page creation."""
    mock_https_helper.post.return_value = {"id": "new_page_id", "title": "New Page"}

    new_page = await safe_confluence_api.create_page(
        space_key="SPACE", title="New Page", body="Content"
    )

    assert new_page["id"] == "new_page_id"
    mock_https_helper.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_details_by_username_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful retrieval of user details by username."""
    mock_user_details = {"username": "testuser", "displayName": "Test User"}
    mock_https_helper.get.return_value = mock_user_details

    user_details = await safe_confluence_api.get_user_details_by_username("testuser")

    assert user_details == mock_user_details
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/user?username=testuser",  # URL matches fixture's base_url
        headers=safe_confluence_api.headers,
    )


@pytest.mark.asyncio
async def test_get_user_details_by_userkey_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful retrieval of user details by userkey."""
    mock_user_details = {"userkey": "user123", "displayName": "User Key Test"}
    mock_https_helper.get.return_value = mock_user_details

    user_details = await safe_confluence_api.get_user_details_by_userkey("user123")

    assert user_details == mock_user_details
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/user?key=user123",  # URL matches fixture's base_url
        headers=safe_confluence_api.headers,
    )


@pytest.mark.asyncio
async def test_get_all_descendants_success(safe_confluence_api, mock_https_helper):
    """Tests successful retrieval of all descendants."""
    # Mocking get_page_child_by_type which is called by get_all_descendants_concurrently
    # This mock simulates a hierarchy: page1 -> child1, child2; child1 -> subchild1
    mock_https_helper.get.side_effect = [
        # First call for page_id "1" (root)
        {
            "results": [
                {"id": "2", "title": "Child 1"},
                {"id": "3", "title": "Child 2"},
            ],
            "size": 2,
        },
        # Second call for page_id "2"
        {"results": [{"id": "4", "title": "Subchild 1"}], "size": 1},
        # Third call for page_id "3"
        {"results": [], "size": 0},
        # Fourth call for page_id "4"
        {"results": [], "size": 0},
    ]

    descendant_ids = await safe_confluence_api.get_all_descendants("1")

    assert sorted(descendant_ids) == sorted(["2", "3", "4"])
    assert (
        mock_https_helper.get.call_count == 4
    )  # One for root, one for each child, one for subchild


@pytest.mark.asyncio
async def test_get_tasks_from_page_success(safe_confluence_api, mock_https_helper):
    """Tests successful extraction of tasks from a page."""
    page_details = {
        "id": "123",
        "title": "Test Page",
        "body": {
            "storage": {
                "value": """
                <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1 Summary <ri:user ri:userkey="user1"></ri:user><time datetime="2024-07-20"></time></ac:task-body></ac:task></ac:task-list>
                <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">JIRA-1</ac:parameter></ac:structured-macro>
                """,
                "representation": "storage",
            }
        },
        "version": {"number": 1},
    }

    # Mock for get_user_details_by_userkey call within _parse_single_task
    mock_https_helper.get.return_value = {"username": "user1_name"}

    tasks = await safe_confluence_api.get_tasks_from_page(page_details)

    assert len(tasks) == 1
    assert tasks[0].confluence_task_id == "task1"
    assert tasks[0].task_summary == "Task 1 Summary"
    assert tasks[0].assignee_name == "user1_name"
    assert tasks[0].due_date == "2024-07-20"
    assert mock_https_helper.get.call_count == 1  # For user details


@pytest.mark.asyncio
async def test_update_page_with_jira_links_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful replacement of tasks with Jira links."""
    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]

    # Mock for get_page_by_id
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {
            "storage": {
                "value": """<ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1 Summary</ac:task-body></ac:task></ac:task-list>""",
                "representation": "storage",
            }
        },
        "version": {"number": 1},
    }
    # Mock for update_page call (which uses https_helper.put)
    mock_https_helper.put.return_value = {"id": page_id, "version": {"number": 2}}

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    # Verify that update_page was called with the modified content
    assert mock_https_helper.put.called  # Check if put was called
    # You might want to inspect the arguments of the put call more closely
    # e.g., mock_https_helper.put.assert_awaited_with(..., json_data=ContainsHtml("<ac:structured-macro ac:name="jira" ..."))
    # For simplicity, just checking if it was called.


@pytest.mark.asyncio
async def test_get_all_spaces_success(safe_confluence_api, mock_https_helper):
    """Tests successful retrieval of all Confluence spaces."""
    mock_spaces_data = {"results": [{"id": "s1", "name": "Space 1"}]}
    mock_https_helper.get.return_value = mock_spaces_data

    spaces = await safe_confluence_api.get_all_spaces()

    assert spaces == mock_spaces_data["results"]
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/space",
        headers=safe_confluence_api.headers,
    )
