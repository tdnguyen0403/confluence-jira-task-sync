import logging
from unittest.mock import AsyncMock, call, patch, MagicMock

import httpx
import pytest
from bs4 import BeautifulSoup
import uuid

from src.api.https_helper import HTTPSHelper, HTTPXClientError, HTTPXCustomError
from src.api.safe_confluence_api import SafeConfluenceApi
from src.config import config
from src.exceptions import ConfluenceApiError

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
    # Ensure all relevant config values are patched for isolated testing
    with (
        patch.object(config, "CONFLUENCE_API_TOKEN", "test_token"),
        patch.object(config, "CONFLUENCE_URL", "http://confluence.example.com"),
        patch.object(config, "JIRA_MACRO_SERVER_NAME", "TestJiraServer"),
        patch.object(config, "JIRA_MACRO_SERVER_ID", "server-123"),
        patch.object(config, "AGGREGATION_CONFLUENCE_MACRO", ["jira", "info"]),
    ):  # This line is crucial
        return SafeConfluenceApi(
            base_url="http://confluence.example.com",
            https_helper=mock_https_helper,
            jira_macro_server_name="TestJira",  # These are passed to init, but internal uses config directly
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

    mock_response_step1 = AsyncMock(spec=httpx.Response)
    mock_response_step1.status_code = 302
    mock_response_step1.headers = {"Location": redirect_url_step1}
    mock_response_step1.url = httpx.URL(short_url)

    mock_response_step2 = AsyncMock(spec=httpx.Response)
    mock_response_step2.status_code = 200
    mock_response_step2.url = httpx.URL(final_resolved_url)

    mock_https_helper._make_request.side_effect = [mock_response_step2]

    page_id = await safe_confluence_api.get_page_id_from_url(short_url)
    assert page_id == "67890"

    mock_https_helper._make_request.assert_awaited_once_with(
        "HEAD",
        short_url,
        headers=safe_confluence_api.headers,
        timeout=5,
        follow_redirects=True,
    )
    assert mock_https_helper._make_request.call_count == 1


@pytest.mark.asyncio
async def test_get_page_by_id_success(safe_confluence_api, mock_https_helper):
    """Tests successful retrieval of a Confluence page by ID."""
    mock_page_data = {"id": "123", "title": "Test Page"}
    mock_https_helper.get.return_value = mock_page_data

    page = await safe_confluence_api.get_page_by_id("123", expand="body.storage")

    assert page["id"] == "123"
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/content/123",
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
        "http://confluence.example.com/rest/api/content/123",
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
    mock_https_helper.get.return_value = {
        "id": "123",
        "title": "Old Title",
        "version": {"number": 1},
    }
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
async def test_get_user_by_username_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful retrieval of user details by username."""
    mock_user_details = {"username": "testuser", "displayName": "Test User"}
    mock_https_helper.get.return_value = mock_user_details

    user_details = await safe_confluence_api.get_user_by_username("testuser")

    assert user_details == mock_user_details
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/user?username=testuser",
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
        "http://confluence.example.com/rest/api/user?key=user123",
        headers=safe_confluence_api.headers,
    )


@pytest.mark.asyncio
async def test_get_all_descendants_success(safe_confluence_api, mock_https_helper):
    """Tests successful retrieval of all descendants."""
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
    assert mock_https_helper.get.call_count == 4


@pytest.mark.asyncio
async def test_update_page_with_jira_links_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful replacement of tasks with Jira links."""
    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]

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
    mock_https_helper.put.return_value = {"id": page_id, "version": {"number": 2}}

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    assert mock_https_helper.put.called
    put_args, put_kwargs = mock_https_helper.put.call_args
    assert "json_data" in put_kwargs

    updated_body = put_kwargs["json_data"]["body"]["storage"]["value"]
    assert '<ac:parameter ac:name="key">PROJ-1</ac:parameter>' in updated_body
    assert "Task 1 Summary" in updated_body
    assert "<ac:task-list>" not in updated_body  # The empty list should be removed


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


# --- New Test Cases for Increased Coverage ---


@pytest.mark.asyncio
async def test_get_page_id_from_url_clean_path_format(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_id_from_url with a clean /pages/<id> format."""
    url = "http://confluence.example.com/pages/123456"
    mock_https_helper._make_request.assert_not_called()
    page_id = await safe_confluence_api.get_page_id_from_url(url)
    assert page_id == "123456"


@pytest.mark.asyncio
async def test_get_page_id_from_url_short_url_http_error(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_id_from_url when _make_request raises an HTTP error."""
    short_url = "http://confluence.example.com/x/error"
    mock_https_helper._make_request.side_effect = HTTPXClientError(
        "Not Found",
        request=httpx.Request("HEAD", short_url),
        response=httpx.Response(404),
    )

    with pytest.raises(ConfluenceApiError) as excinfo: # Expect ConfluenceApiError
        await safe_confluence_api.get_page_id_from_url(short_url)

    assert "API call failed in SafeConfluenceApi.get_page_id_from_url" in str(excinfo.value)
    assert excinfo.value.status_code == 404
    mock_https_helper._make_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_page_id_from_url_short_url_unexpected_status(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_id_from_url when _make_request returns an unexpected status code."""
    short_url = "http://confluence.example.com/x/badstatus"
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.url = httpx.URL(short_url)
    mock_https_helper._make_request.return_value = mock_response

    page_id = await safe_confluence_api.get_page_id_from_url(short_url)
    assert page_id is None
    mock_https_helper._make_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_page_by_id_http_error(safe_confluence_api, mock_https_helper):
    """Tests get_page_by_id when https_helper.get raises an HTTP error."""
    page_id = "999"
    mock_https_helper.get.side_effect = HTTPXClientError(
        "Not Found", request=httpx.Request("GET", "url"), response=httpx.Response(404)
    )

    with pytest.raises(ConfluenceApiError) as excinfo: # Expect ConfluenceApiError
        await safe_confluence_api.get_page_by_id(page_id)

    assert "API call failed in SafeConfluenceApi.get_page_by_id" in str(excinfo.value)
    assert excinfo.value.status_code == 404
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_page_child_by_type_pagination(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_child_by_type with multiple pages of results."""
    mock_https_helper.get.side_effect = [
        {"results": [{"id": f"c{i}"} for i in range(50)], "size": 100},
        {"results": [{"id": f"c{i}"} for i in range(50, 100)], "size": 100},
        {"results": [], "size": 100},
    ]

    children = await safe_confluence_api.get_page_child_by_type("parent123")

    assert len(children) == 100
    assert mock_https_helper.get.call_count == 3
    mock_https_helper.get.assert_any_await(
        "http://confluence.example.com/rest/api/content/parent123/child/page?start=0&limit=50",
        headers=safe_confluence_api.headers,
    )
    mock_https_helper.get.assert_any_await(
        "http://confluence.example.com/rest/api/content/parent123/child/page?start=50&limit=50",
        headers=safe_confluence_api.headers,
    )


@pytest.mark.asyncio
async def test_get_page_child_by_type_http_error(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_child_by_type when https_helper.get raises an error."""
    mock_https_helper.get.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("GET", "url")
    )

    with pytest.raises(ConfluenceApiError) as excinfo: # Expect ConfluenceApiError
        await safe_confluence_api.get_page_child_by_type("parent123")

    assert "API call failed in SafeConfluenceApi.get_page_child_by_type" in str(excinfo.value)
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_page_child_by_type_no_results_key(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_child_by_type when response data is missing 'results' key."""
    mock_https_helper.get.return_value = {"not_results": []}

    children = await safe_confluence_api.get_page_child_by_type("parent123")
    assert children == []
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_page_page_not_found(safe_confluence_api, mock_https_helper):
    """Tests update_page when get_page_by_id returns None."""
    mock_https_helper.get.return_value = None

    success = await safe_confluence_api.update_page(
        "nonexistent_id", "New Title", "New Body"
    )
    assert success is False
    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_page_http_error(safe_confluence_api, mock_https_helper):
    """Tests update_page when https_helper.put raises an error."""
    mock_https_helper.get.return_value = {
        "id": "123",
        "title": "Old Title",
        "version": {"number": 1},
    }
    mock_https_helper.put.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("PUT", "url")
    )
    mock_https_helper.put.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("PUT", "url"),
        response=httpx.Response(500, request=httpx.Request("PUT", "url"))
    )
    with pytest.raises(ConfluenceApiError):
        await safe_confluence_api.update_page("123", "New Title", "New Body")
    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_page_with_parent_id_success(
    safe_confluence_api, mock_https_helper
):
    """Tests successful page creation with a parent ID."""
    mock_https_helper.post.return_value = {"id": "child_page_id", "title": "Child Page"}

    new_page = await safe_confluence_api.create_page(
        space_key="SPACE",
        title="Child Page",
        body="Child Content",
        parent_id="parent123",
    )

    assert new_page["id"] == "child_page_id"
    mock_https_helper.post.assert_awaited_once()
    post_args, post_kwargs = mock_https_helper.post.call_args
    assert "json_data" in post_kwargs
    assert post_kwargs["json_data"]["ancestors"] == [{"id": "parent123"}]


@pytest.mark.asyncio
async def test_create_page_http_error(safe_confluence_api, mock_https_helper):
    """Tests create_page when https_helper.post raises an error."""
    mock_https_helper.post.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("POST", "url")
    )

    with pytest.raises(ConfluenceApiError):
        await safe_confluence_api.create_page(
            space_key="SPACE", title="Failing Page", body="Content"
        )
    mock_https_helper.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_by_username_http_error(
    safe_confluence_api, mock_https_helper
):
    """Tests get_user_by_username when https_helper.get raises an error."""
    mock_https_helper.get.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("GET", "url")
    )

    with pytest.raises(ConfluenceApiError):
        await safe_confluence_api.get_user_by_username(
            "nonexistent_user"
        )
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_details_by_userkey_http_error(
    safe_confluence_api, mock_https_helper
):
    """Tests get_user_details_by_userkey when https_helper.get raises an error."""
    mock_https_helper.get.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("GET", "url")
    )

    with pytest.raises(ConfluenceApiError):
        await safe_confluence_api.get_user_details_by_userkey(
            "nonexistent_key"
        )
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_all_descendants_concurrently_error_handling(
    safe_confluence_api, mock_https_helper
):
    """
    Tests get_all_descendants_concurrently when one of the child fetches fails.
    The list of all_pages returned should only include pages successfully retrieved.
    """
    mock_https_helper.get.side_effect = [
        # Call 1: for page_id "1" (root). This call is successful and returns children "2" and "3".
        {
            "results": [
                {"id": "2", "title": "Child 2"},
                {"id": "3", "title": "Child 3"},
            ],
            "size": 2,
        },
        # Call 2: for page_id "2". This simulates an error. get_page_child_by_type will return [].
        HTTPXCustomError(
            "Simulated connection error for page 2",
            request=httpx.Request("GET", "url_page_2"),
        ),
        # Call 3: for page_id "3". This is successful but returns no children.
        {"results": [], "size": 0},
    ]

    descendant_pages = await safe_confluence_api.get_all_descendants_concurrently("1")

    assert len(descendant_pages) == 2
    assert {"id": "2", "title": "Child 2"} in descendant_pages
    assert {"id": "3", "title": "Child 3"} in descendant_pages
    assert mock_https_helper.get.call_count == 3


@pytest.mark.asyncio
async def test_get_tasks_from_page_empty_html(safe_confluence_api):
    """Tests get_tasks_from_page with empty HTML content."""
    page_details = {
        "id": "123",
        "title": "Empty Page",
        "body": {"storage": {"value": "", "representation": "storage"}},
        "version": {"number": 1},
    }
    tasks = await safe_confluence_api.get_tasks_from_page(page_details)
    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_get_tasks_from_page_no_body_key(safe_confluence_api):
    """Tests get_tasks_from_page with page_details missing 'body' key."""
    page_details = {
        "id": "123",
        "title": "No Body Page",
        "version": {"number": 1},
    }
    tasks = await safe_confluence_api.get_tasks_from_page(page_details)
    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_get_tasks_from_page_with_aggregation_macro(
    safe_confluence_api, mock_https_helper
):
    """Tests get_tasks_from_page skips tasks within aggregation macros.
    The fix is to properly patch config.AGGREGATION_CONFLUENCE_MACRO
    for the SafeConfluenceApi instance being tested.
    """
    page_details = {
        "id": "123",
        "title": "Test Page",
        "body": {
            "storage": {
                "value": """
                <ac:task-list>
                    <ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Standalone Task</ac:task-body></ac:task>
                </ac:task-list>
                <ac:structured-macro ac:name="jira">
                    <ac:task-list><ac:task><ac:task-id>task_in_jira</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task in Jira macro</ac:task-body></ac:task></ac:task-list>
                </ac:structured-macro>
                <ac:structured-macro ac:name="info">
                    <ac:task-list><ac:task><ac:task-id>task_in_info</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task in Info macro</ac:task-body></ac:task></ac:task-list>
                </ac:structured-macro>
                """,
                "representation": "storage",
            }
        },
        "version": {"number": 1},
    }
    mock_https_helper.get.return_value = {"username": "user1_name"}

    # Re-patch config.AGGREGATION_CONFLUENCE_MACRO specifically for this test,
    # to ensure it's active when the method is called.
    with patch.object(config, "AGGREGATION_CONFLUENCE_MACRO", ["jira", "info"]):
        tasks = await safe_confluence_api.get_tasks_from_page(page_details)
        assert len(tasks) == 1
        assert tasks[0].confluence_task_id == "task1"
        assert "Task in Jira macro" not in tasks[0].task_summary
        assert "Task in Info macro" not in tasks[0].task_summary
        mock_https_helper.get.assert_not_called()  # No user in task1, so get_user_details_by_userkey should not be called.


@pytest.mark.asyncio
async def test_get_tasks_from_page_with_nested_tasks(
    safe_confluence_api, mock_https_helper
):
    """Tests get_tasks_from_page skips nested tasks."""
    page_details = {
        "id": "123",
        "title": "Test Page",
        "body": {
            "storage": {
                "value": """
                <ac:task-list>
                    <ac:task><ac:task-id>parent_task</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Parent Task
                        <ac:task-list>
                            <ac:task><ac:task-id>nested_task</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Nested Task</ac:task-body></ac:task>
                        </ac:task-list>
                    </ac:task-body></ac:task>
                </ac:task-list>
                """,
                "representation": "storage",
            }
        },
        "version": {"number": 1},
    }
    mock_https_helper.get.return_value = {"username": "user1_name"}

    tasks = await safe_confluence_api.get_tasks_from_page(page_details)
    assert len(tasks) == 1
    assert tasks[0].confluence_task_id == "parent_task"
    assert "Nested Task" not in tasks[0].task_summary
    mock_https_helper.get.assert_not_called()


@pytest.mark.asyncio
async def test_parse_single_task_malformed_elements(safe_confluence_api):
    """Tests _parse_single_task with malformed task elements."""
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}

    malformed_task1 = BeautifulSoup(
        "<ac:task><ac:task-id>t1</ac:task-id><ac:task-status>inc</ac:task-status></ac:task>",
        "html.parser",
    ).find("ac:task")
    assert (
        await safe_confluence_api._parse_single_task(malformed_task1, page_details)
        is None
    )

    malformed_task2 = BeautifulSoup(
        "<ac:task><ac:task-body>Body</ac:task-body><ac:task-status>inc</ac:task-status></ac:task>",
        "html.parser",
    ).find("ac:task")
    assert (
        await safe_confluence_api._parse_single_task(malformed_task2, page_details)
        is None
    )

    malformed_task3 = BeautifulSoup(
        "<ac:task><ac:task-id>t3</ac:task-id><ac:task-body>Body</ac:task-body></ac:task>",
        "html.parser",
    ).find("ac:task")
    assert (
        await safe_confluence_api._parse_single_task(malformed_task3, page_details)
        is None
    )


@pytest.mark.asyncio
async def test_parse_single_task_no_assignee_or_due_date(
    safe_confluence_api, mock_https_helper
):
    """Tests _parse_single_task when assignee and due date are missing."""
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}
    task_html = """
    <ac:task-list><ac:task><ac:task-id>task_no_assignee_date</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Simple Task</ac:task-body></ac:task></ac:task-list>
    """
    task_element = BeautifulSoup(task_html, "html.parser").find("ac:task")

    mock_https_helper.get.assert_not_awaited()

    task = await safe_confluence_api._parse_single_task(task_element, page_details)
    assert task is not None
    assert task.assignee_name is None
    assert task.due_date is None
    mock_https_helper.get.assert_not_called()


@pytest.mark.asyncio
async def test_parse_single_task_assignee_userkey_no_details(
    safe_confluence_api, mock_https_helper
):
    """Tests _parse_single_task when assignee userkey is present but no user details found."""
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}
    task_html = """
    <ac:task-list><ac:task><ac:task-id>task_no_user_details</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task <ri:user ri:userkey="unknown"></ri:user></ac:task-body></ac:task></ac:task-list>
    """
    task_element = BeautifulSoup(task_html, "html.parser").find("ac:task")

    mock_https_helper.get.return_value = None

    task = await safe_confluence_api._parse_single_task(task_element, page_details)
    assert task is not None
    assert task.assignee_name is None
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/user?key=unknown",
        headers=safe_confluence_api.headers,
    )


@pytest.mark.asyncio
async def test_parse_single_task_assignee_userkey_no_username(
    safe_confluence_api, mock_https_helper
):
    """Tests _parse_single_task when assignee userkey is present, user details found but no username."""
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}
    task_html = """
    <ac:task-list><ac:task><ac:task-id>task_no_username</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task <ri:user ri:userkey="somekey"></ri:user></ac:task-body></ac:task></ac:task-list>
    """
    task_element = BeautifulSoup(task_html, "html.parser").find("ac:task")

    mock_https_helper.get.return_value = {"displayName": "User Name Only"}

    task = await safe_confluence_api._parse_single_task(task_element, page_details)
    assert task is not None
    assert task.assignee_name is None
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_page_with_jira_links_page_not_found(
    safe_confluence_api, mock_https_helper
):
    """Tests update_page_with_jira_links when get_page_by_id returns None."""
    mock_https_helper.get.return_value = None

    await safe_confluence_api.update_page_with_jira_links("nonexistent_id", [])
    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_page_with_jira_links_no_tasks_to_replace(
    safe_confluence_api, mock_https_helper
):
    """Tests update_page_with_jira_links when no tasks match mappings."""
    page_id = "123"
    mappings = [{"confluence_task_id": "non_existent_task", "jira_key": "PROJ-2"}]

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
    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_page_with_jira_links_multiple_tasks_and_lists(
    safe_confluence_api, mock_https_helper
):
    """Tests update_page_with_jira_links with multiple tasks and task lists."""
    page_id = "123"
    mappings = [
        {"confluence_task_id": "task1", "jira_key": "PROJ-1"},
        {"confluence_task_id": "task3", "jira_key": "PROJ-3"},
    ]
    initial_body = """
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1 Summary</ac:task-body></ac:task></ac:task-list>
    <p>Some content</p>
    <ac:task-list><ac:task><ac:task-id>task2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 2 Summary</ac:task-body></ac:task>
    <ac:task><ac:task-id>task3</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 3 Summary</ac:task-body></ac:task></ac:task-list>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }
    mock_https_helper.put.return_value = {"id": page_id, "version": {"number": 2}}

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    mock_https_helper.put.assert_awaited_once()
    put_args, put_kwargs = mock_https_helper.put.call_args
    updated_body = put_kwargs["json_data"]["body"]["storage"]["value"]

    # The replaced tasks should be gone
    assert "<ac:task-id>task1</ac:task-id>" not in updated_body
    assert "<ac:task-id>task3</ac:task-id>" not in updated_body
    # The remaining task should still be there
    assert "<ac:task-id>task2</ac:task-id>" in updated_body

    # The new Jira macros and text should be present
    assert '<ac:parameter ac:name="key">PROJ-1</ac:parameter>' in updated_body
    assert "Task 1 Summary" in updated_body
    assert '<ac:parameter ac:name="key">PROJ-3</ac:parameter>' in updated_body
    assert "Task 3 Summary" in updated_body


@pytest.mark.asyncio
async def test_update_page_with_jira_links_empty_task_list_cleanup(
    safe_confluence_api, mock_https_helper
):
    """Tests that empty task lists are cleaned up after replacement."""
    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]
    initial_body = """
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1 Summary</ac:task-body></ac:task></ac:task-list>
    <p>Another paragraph</p>
    <ac:task-list><ac:task><ac:task-id>task2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 2 Summary</ac:task-body></ac:task></ac:task-list>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }
    mock_https_helper.put.return_value = {"id": page_id, "version": {"number": 2}}

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    put_args, put_kwargs = mock_https_helper.put.call_args
    updated_body = put_kwargs["json_data"]["body"]["storage"]["value"]

    soup_result = BeautifulSoup(updated_body, "html.parser")
    assert soup_result.find_all("ac:task-list")
    assert len(soup_result.find_all("ac:task-list")) == 1
    assert soup_result.find("ac:task-id", string="task2") is not None
    assert soup_result.find("ac:task-id", string="task1") is None


@pytest.mark.asyncio
async def test_get_all_spaces_http_error(safe_confluence_api, mock_https_helper):
    """Tests get_all_spaces when https_helper.get raises an error."""
    mock_https_helper.get.side_effect = HTTPXCustomError(
        "Connection error", request=httpx.Request("GET", "url")
    )

    with pytest.raises(ConfluenceApiError):
        await safe_confluence_api.get_all_spaces()
    mock_https_helper.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_page_by_id_expand_only(safe_confluence_api, mock_https_helper):
    """Tests get_page_by_id with only expand parameter (no version)."""
    mock_page_data = {
        "id": "123",
        "title": "Test Page",
        "body": {"storage": {"value": "content"}},
    }
    mock_https_helper.get.return_value = mock_page_data

    page = await safe_confluence_api.get_page_by_id("123", expand="body.storage")

    assert page["id"] == "123"
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/content/123",
        headers=safe_confluence_api.headers,
        params={"expand": "body.storage"},
    )


@pytest.mark.asyncio
async def test_get_page_id_from_url_short_url_unresolvable_no_id(
    safe_confluence_api, mock_https_helper
):
    """Tests get_page_id_from_url when short URL resolves but no ID is found."""
    short_url = "http://confluence.example.com/x/invalid"
    resolved_url = "http://confluence.example.com/some/random/path"

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.url = httpx.URL(resolved_url)
    mock_https_helper._make_request.return_value = mock_response

    page_id = await safe_confluence_api.get_page_id_from_url(short_url)
    assert page_id is None
    mock_https_helper._make_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_page_with_jira_links_aggregation_macro(
    safe_confluence_api, mock_https_helper
):
    """
    Tests that tasks inside aggregation macros are SKIPPED during replacement.
    """
    page_id = "123"
    mappings = [{"confluence_task_id": "task_in_jira", "jira_key": "PROJ-2"}]
    initial_body = """
    <ac:structured-macro ac:name="jira">
        <ac:task-list>
            <ac:task><ac:task-id>task_in_jira</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task in Jira macro</ac:task-body></ac:task>
        </ac:task-list>
    </ac:structured-macro>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    mock_https_helper.get.assert_awaited_once()
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_page_with_jira_links_empty_mappings(
    safe_confluence_api, mock_https_helper
):
    """Test update_page_with_jira_links with empty mappings."""
    page_id = "123"
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {
            "storage": {
                "value": "<ac:task-list></ac:task-list>",
                "representation": "storage",
            }
        },
        "version": {"number": 1},
    }
    await safe_confluence_api.update_page_with_jira_links(page_id, [])
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_parse_single_task_multiple_assignees_and_due_dates(
    safe_confluence_api, mock_https_helper
):
    """Test _parse_single_task with multiple assignees and due dates."""
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}
    task_html = """
    <ac:task-list>
        <ac:task>
            <ac:task-id>task_multi</ac:task-id>
            <ac:task-status>incomplete</ac:task-status>
            <ac:task-body>
                Multi Task
                <ri:user ri:userkey="user1"></ri:user>
                <ri:user ri:userkey="user2"></ri:user>
                <time datetime="2024-07-20"></time>
                <time datetime="2024-08-01"></time>
            </ac:task-body>
        </ac:task>
    </ac:task-list>
    """
    task_element = BeautifulSoup(task_html, "html.parser").find("ac:task")
    mock_https_helper.get.return_value = {"username": "user1_name"}
    task = await safe_confluence_api._parse_single_task(task_element, page_details)
    assert task is not None
    assert task.assignee_name == "user1_name"
    assert task.due_date == "2024-07-20"


@pytest.mark.asyncio
async def test_get_tasks_from_page_with_no_task_lists(safe_confluence_api):
    """Test get_tasks_from_page with no <ac:task-list> present."""
    page_details = {
        "id": "123",
        "title": "No Task List Page",
        "body": {
            "storage": {"value": "<p>No tasks here.</p>", "representation": "storage"}
        },
        "version": {"number": 1},
    }
    tasks = await safe_confluence_api.get_tasks_from_page(page_details)
    assert tasks == []


@pytest.mark.asyncio
async def test_get_page_id_from_url_with_redirect(
    safe_confluence_api, mock_https_helper
):
    """
    Tests get_page_id_from_url's recursive call when a 3xx redirect is encountered.
    This specifically covers the 'if 300 <= response.status_code < 400' branch.
    """
    short_url = "http://confluence.example.com/x/abcde"
    redirect_url = "http://confluence.example.com/pages/viewpage.action?pageId=54321"

    # Mock the first response as a redirect
    mock_redirect_response = AsyncMock(spec=httpx.Response)
    mock_redirect_response.status_code = 302
    mock_redirect_response.headers = {"Location": redirect_url}

    # Set up the side_effect for _make_request
    # The first call gets the redirect, the second call (recursive) will be implicitly handled
    # by the logic that finds the pageId in the redirect_url.
    mock_https_helper._make_request.return_value = mock_redirect_response

    # To test the full recursive path, we can mock a second call if needed,
    # but the current implementation directly re-calls get_page_id_from_url with the new URL,
    # which will then be parsed by the regex without a new request.
    # We can simplify the test to ensure the redirect is followed.

    page_id = await safe_confluence_api.get_page_id_from_url(short_url)

    # Assertions
    assert page_id == "54321"
    # This verifies that the initial HEAD request was made
    mock_https_helper._make_request.assert_awaited_once_with(
        "HEAD",
        short_url,
        headers=safe_confluence_api.headers,
        timeout=5,
        follow_redirects=True,  # The helper is configured to follow, but the code handles manual cases too
    )


@pytest.mark.asyncio
async def test_get_all_descendants_concurrently_handles_exceptions(
    safe_confluence_api,
):
    """
    Tests that get_all_descendants_concurrently handles exceptions raised by child tasks.
    This covers the `isinstance(res, Exception)` branch.
    """
    # We patch `get_page_child_by_type` directly on the instance for this test
    # to simulate a failure that `asyncio.gather` will capture as an exception.
    with patch.object(
        safe_confluence_api, "get_page_child_by_type", new_callable=AsyncMock
    ) as mock_get_children:
        mock_get_children.side_effect = [
            # First call for the root page '1' is successful
            [{"id": "2"}, {"id": "3"}],
            # Subsequent calls (for pages '2' and '3') will be gathered
            # Let's make the call for page '2' fail and '3' succeed
            RuntimeError("Simulated API failure"),  # Exception for page '2'
            [{"id": "4"}],  # Successful result for page '3'
            [],  # Successful result for page '4'
        ]

        # Expected call sequence:
        # 1. get_page_child_by_type("1") -> returns [{"id": "2"}, {"id": "3"}]
        # 2. asyncio.gather(get_page_child_by_type("2"), get_page_child_by_type("3"))
        # 3. asyncio.gather(get_page_child_by_type("4"))

        all_descendants = await safe_confluence_api.get_all_descendants_concurrently(
            "1"
        )

        # Assert that the successfully fetched descendants are returned despite one error
        descendant_ids = {page["id"] for page in all_descendants}
        assert descendant_ids == {"2", "3", "4"}

        # Verify the calls were made as expected
        expected_calls = [
            call("1"),
            call("2"),
            call("3"),
            call("4"),
        ]
        mock_get_children.assert_has_calls(expected_calls, any_order=True)


@pytest.mark.asyncio
async def test_get_page_id_from_url_resolves_to_query_param_format(
    safe_confluence_api, mock_https_helper
):
    """
    Tests get_page_id_from_url when a short URL resolves to a URL with a 'pageId' query param.
    This covers the `resolved_page_id_query_match` branch after a successful redirect.
    """
    short_url = "http://confluence.example.com/x/fghij"
    final_url = "http://confluence.example.com/pages/viewpage.action?pageId=98765"

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.url = httpx.URL(final_url)
    mock_https_helper._make_request.return_value = mock_response

    page_id = await safe_confluence_api.get_page_id_from_url(short_url)

    assert page_id == "98765"
    mock_https_helper._make_request.assert_awaited_once_with(
        "HEAD",
        short_url,
        headers=safe_confluence_api.headers,
        timeout=5,
        follow_redirects=True,
    )

@pytest.mark.asyncio
async def test_get_page_child_by_type_fails_on_second_page(
    safe_confluence_api, mock_https_helper
):
    """
    Tests that get_page_child_by_type returns partial results if pagination fails mid-way.
    This covers the `except Exception` block inside the `while` loop.
    """
    # First page of results is successful
    first_page_results = {"results": [{"id": f"c{i}"} for i in range(50)], "size": 51}
    # Second call fails
    second_page_error = HTTPXCustomError(
        "Connection failed", request=httpx.Request("GET", "url")
    )

    mock_https_helper.get.side_effect = [
        first_page_results,
        second_page_error,
    ]

    with pytest.raises(ConfluenceApiError) as excinfo:
        await safe_confluence_api.get_page_child_by_type("parent123")

    assert "API call failed in SafeConfluenceApi.get_page_child_by_type" in str(excinfo.value)
    assert mock_https_helper.get.call_count == 2 # First successful call + second failing call


@pytest.mark.asyncio
async def test_update_page_with_jira_links_fails_on_final_update(
    safe_confluence_api, mock_https_helper, caplog
):
    """
    Tests the failure path when replacing tasks succeeds but the final page update fails.
    This ensures the error within the final `update_page` call is handled.
    """
    # Explicitly set the log level for this test to ensure ERROR logs are caught
    caplog.set_level(logging.ERROR)

    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]
    initial_body = """
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1 Summary</ac:task-body></ac:task></ac:task-list>
    """
    # Mock the initial page fetch and the subsequent fetch inside update_page
    page_data = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }
    mock_https_helper.get.return_value = page_data

    # Mock the final PUT call to fail
    mock_https_helper.put.side_effect = HTTPXClientError(
        "Forbidden", request=httpx.Request("PUT", "url"), response=httpx.Response(403)
    )

    with pytest.raises(ConfluenceApiError): # Expect ConfluenceApiError
        await safe_confluence_api.update_page_with_jira_links(page_id, mappings)
    assert "API call failed in SafeConfluenceApi.update_page" in caplog.text

    # The first GET is for the initial fetch, the second is inside the `update_page` call
    assert mock_https_helper.get.call_count == 2
    mock_https_helper.put.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_page_by_id_no_version_no_expand(
    safe_confluence_api, mock_https_helper
):
    """
    Tests the get_page_by_id branch where both version and expand are None.
    This covers the `else` path of `if version is not None` and the `else` path of
    the ternary `if expand else {}`.
    """
    mock_page_data = {"id": "123", "title": "Test Page"}
    mock_https_helper.get.return_value = mock_page_data

    # Call with no version and no expand
    page = await safe_confluence_api.get_page_by_id("123")

    assert page["id"] == "123"
    mock_https_helper.get.assert_awaited_once_with(
        "http://confluence.example.com/rest/api/content/123",
        headers=safe_confluence_api.headers,
        params={},  # Ensure params is an empty dict
    )

@pytest.mark.asyncio
async def test_generate_jira_macro_html_with_summary(safe_confluence_api):
    """
    Tests that the generated Jira macro HTML is correctly formatted to show a summary.
    """
    jira_key = "PROJ-456"

    # Mock uuid.uuid4() to have a predictable macro ID
    with patch.object(uuid, 'uuid4', return_value=MagicMock(hex='mock-macro-id')):
        macro_html = safe_confluence_api._generate_jira_macro_html_with_summary(
            jira_key
        )

        # Use BeautifulSoup to parse and inspect the generated HTML
        soup = BeautifulSoup(macro_html, "html.parser")

        # Verify the root macro element
        macro_element = soup.find("ac:structured-macro")
        assert macro_element is not None, "The root ac:structured-macro element was not found."
        assert macro_element.get("ac:name") == "jira"

        # Find all parameter tags
        params = {
            param.get("ac:name"): param.get_text(strip=True)
            for param in macro_element.find_all("ac:parameter")
        }

        # Assert that the correct parameters are present
        assert params.get("key") == jira_key
        assert params.get("server") == "TestJira"  # From fixture
        assert params.get("serverId") == "12345"    # From fixture

        # Crucially, assert that 'showSummary' is NOT 'false'
        assert "showSummary" not in params, "showSummary should not be present to default to showing the summary."

@pytest.mark.asyncio
async def test_create_page_no_parent_id(safe_confluence_api, mock_https_helper):
    """Tests create_page without a parent_id."""
    mock_https_helper.post.return_value = {"id": "new_page_id", "title": "New Page"}

    await safe_confluence_api.create_page(
        space_key="SPACE", title="New Page", body="Content"
    )

    _, post_kwargs = mock_https_helper.post.call_args
    assert "json_data" in post_kwargs
    assert post_kwargs["json_data"]["ancestors"] == []


@pytest.mark.asyncio
async def test_update_page_no_version_in_response(
    safe_confluence_api, mock_https_helper
):
    """
    Tests the update_page failure path when the initial GET lacks version info.
    This covers the `except KeyError` branch in `update_page`.
    """
    mock_https_helper.get.return_value = {
        "id": "123",
        "title": "Old Title",
        # The "version" key is intentionally missing
    }

    success = await safe_confluence_api.update_page("123", "New Title", "New Body")

    assert success is False
    mock_https_helper.get.assert_awaited_once()
    # The PUT call should not be made if version info is missing
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_get_page_id_from_url_no_redirect_location(
    safe_confluence_api, mock_https_helper
):
    """
    Tests get_page_id_from_url when a 3xx response lacks a 'Location' header.
    This covers the `else` path of the `response.headers.get("Location")` check.
    """
    short_url = "http://confluence.example.com/x/brokenredirect"
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 301
    mock_response.headers = {}  # No "Location" header
    mock_response.url = httpx.URL(short_url)
    mock_https_helper._make_request.return_value = mock_response

    page_id = await safe_confluence_api.get_page_id_from_url(short_url)

    assert page_id is None
    mock_https_helper._make_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_single_task_user_mention_no_userkey(
    safe_confluence_api, mock_https_helper
):
    """
    Tests _parse_single_task when a <ri:user> tag is present but lacks a 'ri:userkey'.
    This covers the `else` branch for the `if user_key := ...` assignment.
    """
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}
    task_html = """
    <ac:task>
        <ac:task-id>task1</ac:task-id>
        <ac:task-status>incomplete</ac:task-status>
        <ac:task-body>Task with malformed user <ri:user some-other-attr="foo"></ri:user></ac:task-body>
    </ac:task>
    """
    task_element = BeautifulSoup(task_html, "html.parser").find("ac:task")

    task = await safe_confluence_api._parse_single_task(task_element, page_details)

    assert task is not None
    assert task.assignee_name is None, "Assignee should be None if userkey is missing"
    # Ensure no API call was made to get user details
    mock_https_helper.get.assert_not_called()


@pytest.mark.asyncio
async def test_parse_single_task_missing_datetime_attr(safe_confluence_api):
    """
    Tests _parse_single_task when a <time> tag exists but is missing the 'datetime' attribute.
    This specifically covers the 'else' branch of the due_date assignment.
    """
    page_details = {"id": "123", "title": "Test Page", "version": {"number": 1}}
    task_html = """
    <ac:task>
        <ac:task-id>task1</ac:task-id>
        <ac:task-status>incomplete</ac:task-status>
        <ac:task-body>Task with malformed time <time some-other-attr="value"></time></ac:task-body>
    </ac:task>
    """
    task_element = BeautifulSoup(task_html, "html.parser").find("ac:task")

    task = await safe_confluence_api._parse_single_task(task_element, page_details)

    assert task is not None
    assert task.due_date is None, (
        "Due date should be None when datetime attribute is missing"
    )

@pytest.mark.asyncio
async def test_update_page_with_jira_links_no_parent_task_list(
    safe_confluence_api, mock_https_helper
):
    """
    Tests that a task not within a <ac:task-list> is skipped during replacement.
    This covers the `if not parent_task_list:` branch.
    """
    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]
    # This task is not nested inside a <ac:task-list>
    initial_body = """
    <p>Some text</p>
    <ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Orphan Task</ac:task-body></ac:task>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    # The page should not be updated because the task was not in a valid list
    mock_https_helper.put.assert_not_called()


@pytest.mark.asyncio
async def test_update_page_with_jira_links_no_task_body(
    safe_confluence_api, mock_https_helper
):
    """
    Tests that a task with no body is skipped during replacement.
    This covers the `if not task_body:` branch.
    """
    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]
    initial_body = """
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status></ac:task></ac:task-list>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    # The page should not be updated as there's no summary to preserve
    mock_https_helper.put.assert_not_called()

@pytest.mark.asyncio
async def test_update_page_with_jira_links_preserves_non_empty_task_lists(
    safe_confluence_api, mock_https_helper
):
    """
    Tests that task lists are NOT removed if they still contain tasks after an update.
    This covers the `False` path for the condition `if not tl.find("ac:task")`.
    """
    page_id = "123"
    mappings = [{"confluence_task_id": "task1", "jira_key": "PROJ-1"}]
    initial_body = """
    <ac:task-list>
        <ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Replace Me</ac:task-body></ac:task>
        <ac:task><ac:task-id>task2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Keep Me</ac:task-body></ac:task>
    </ac:task-list>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }
    mock_https_helper.put.return_value = {"id": page_id, "version": {"number": 2}}

    await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    mock_https_helper.put.assert_awaited_once()
    put_args, put_kwargs = mock_https_helper.put.call_args
    updated_body = put_kwargs["json_data"]["body"]["storage"]["value"]
    soup = BeautifulSoup(updated_body, "html.parser")

    # Assert that the task list still exists
    assert soup.find("ac:task-list") is not None
    # Assert that the remaining task is still inside the list
    assert soup.find("ac:task-list").find("ac:task-id", string="task2") is not None
    # Assert that the replaced task is gone
    assert soup.find("ac:task-id", string="task1") is None

@pytest.mark.asyncio
async def test_update_page_with_jira_links_no_matching_tasks(
    safe_confluence_api, mock_https_helper, caplog
):
    """
    Tests that a warning is logged when update_page_with_jira_links is called
    but no tasks match the provided mappings.
    This covers the `else` branch of `if modified:`.
    """
    caplog.set_level(logging.WARNING)
    page_id = "123"
    # Mapping for a task that does not exist on the page
    mappings = [{"confluence_task_id": "task_xyz", "jira_key": "PROJ-1"}]
    initial_body = """
    <ac:task-list><ac:task><ac:task-id>task1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Some Task</ac:task-body></ac:task></ac:task-list>
    """
    mock_https_helper.get.return_value = {
        "id": page_id,
        "title": "Test Page",
        "body": {"storage": {"value": initial_body, "representation": "storage"}},
        "version": {"number": 1},
    }

    # The method now returns a boolean, we expect False as no update occurred
    result = await safe_confluence_api.update_page_with_jira_links(page_id, mappings)

    assert result is False
    # Assert that no update was attempted
    mock_https_helper.put.assert_not_called()
    # Assert that the warning was logged
    assert f"No tasks were replaced on page {page_id}. Skipping update." in caplog.text

@pytest.mark.asyncio
async def test_get_all_descendants_handles_duplicate_child(
    safe_confluence_api, mock_https_helper
):
    """
    Tests that get_all_descendants handles cases where a child page is a descendant
    of multiple parents in the same hierarchy, ensuring it's processed only once.
    This covers the `if p_id in processed_page_ids:` branch at line 312.
    """
    # page "3" is a child of both "1" and "2"
    mock_https_helper.get.side_effect = [
        # Children for root "root"
        {"results": [{"id": "1"}, {"id": "2"}], "size": 2},
        # Children for "1"
        {"results": [{"id": "3"}], "size": 1},
        # Children for "2"
        {"results": [{"id": "3"}], "size": 1},
        # Children for "3" (the duplicate)
        {"results": [], "size": 0},
    ]

    # The function get_all_descendants uses get_all_descendants_concurrently internally.
    # We call the public method to test the integrated behavior.
    all_ids = await safe_confluence_api.get_all_descendants("root")

    # The final list should not contain duplicates.
    assert sorted(all_ids) == sorted(["1", "2", "3"])

    # get_page_child_by_type (which uses https_helper.get) should have been called
    # for "root", "1", "2", and "3". The duplicate processing of "3" should be skipped.
    assert mock_https_helper.get.call_count == 4
