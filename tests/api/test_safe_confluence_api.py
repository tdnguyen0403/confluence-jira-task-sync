import pytest
import requests
import logging
import re
from unittest.mock import MagicMock, call

from atlassian import Confluence
from bs4 import BeautifulSoup

# Adjust path to import from src
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.api.safe_confluence_api import SafeConfluenceApi
from src.config import config
from src.models.data_models import ConfluenceTask

# --- Fixtures ---


@pytest.fixture
def mock_confluence_client(mocker):
    """Fixture for a mocked atlassian.Confluence client."""
    mock_client = mocker.MagicMock(spec=Confluence)
    return mock_client


@pytest.fixture
def mock_config_values(monkeypatch):
    """Fixture for patching config values that SafeConfluenceApi directly accesses."""
    monkeypatch.setattr(config, "CONFLUENCE_URL", "https://mock.confluence.com")
    monkeypatch.setattr(config, "CONFLUENCE_API_TOKEN", "mock_confluence_token")
    monkeypatch.setattr(config, "JIRA_MACRO_SERVER_NAME", "Mock Jira Server")
    monkeypatch.setattr(config, "JIRA_MACRO_SERVER_ID", "mock-jira-server-id")
    monkeypatch.setattr(
        config, "AGGREGATION_CONFLUENCE_MACRO", ["jira-issues"]
    )  # Example macro
    monkeypatch.setattr(config, "DEFAULT_DUE_DATE", "2025-01-01")
    monkeypatch.setattr(config, "VERIFY_SSL", False)  # Test with SSL verification off
    # CONFLUENCE_HEAD_REQUEST_TIMEOUT is now hardcoded in source, so no need to patch here.


@pytest.fixture
def mock_make_request(mocker):
    """Fixture for mocking the make_request helper function."""
    # Patch where make_request is *used* in safe_confluence_api.py
    return mocker.patch("src.api.safe_confluence_api.make_request")


@pytest.fixture
def safe_confluence_api_instance(mock_confluence_client, mock_config_values):
    """Fixture to provide an instance of SafeConfluenceApi with mocked dependencies."""
    return SafeConfluenceApi(
        confluence_client=mock_confluence_client,
        jira_macro_server_name=config.JIRA_MACRO_SERVER_NAME,
        jira_macro_server_id=config.JIRA_MACRO_SERVER_ID,
    )


@pytest.fixture
def mock_requests_head(mocker):
    """Fixture for mocking requests.head."""
    return mocker.patch("src.api.safe_confluence_api.requests.head")


@pytest.fixture
def mock_uuid_uuid4(mocker):
    """Fixture for mocking uuid.uuid4() for deterministic macro IDs."""
    mock_uuid_obj = MagicMock()
    mock_uuid_obj.__str__.return_value = "test-macro-uuid"
    mocker.patch("src.api.safe_confluence_api.uuid.uuid4", return_value=mock_uuid_obj)


@pytest.fixture
def mock_get_task_context(mocker):
    """Fixture for mocking get_task_context helper."""
    return mocker.patch(
        "src.api.safe_confluence_api.get_task_context", return_value="Test Context"
    )


# --- Tests for SafeConfluenceApi ---


def test_safe_confluence_api_init(safe_confluence_api_instance, mock_confluence_client):
    """Test SafeConfluenceApi initialization."""
    assert safe_confluence_api_instance.client is mock_confluence_client
    assert safe_confluence_api_instance.base_url == "https://mock.confluence.com"
    assert "Authorization" in safe_confluence_api_instance.headers
    assert "Content-Type" in safe_confluence_api_instance.headers
    assert (
        safe_confluence_api_instance.jira_macro_server_name
        == config.JIRA_MACRO_SERVER_NAME
    )
    assert (
        safe_confluence_api_instance.jira_macro_server_id == config.JIRA_MACRO_SERVER_ID
    )


# Test get_page_id_from_url
@pytest.mark.parametrize(
    "url, head_response_url, head_side_effect, expected_id, expected_log_msg",
    [
        (
            "https://mock.confluence.com/pages/viewpage.action?pageId=12345",
            None,
            None,
            "12345",
            None,
        ),
        ("https://mock.confluence.com/pages/54321", None, None, "54321", None),
        (
            "https://mock.confluence.com/x/abcde",
            "https://mock.confluence.com/pages/viewpage.action?pageId=67890",
            None,
            "67890",
            "Attempting to resolve short URL: https://mock.confluence.com/x/abcde",
        ),
        (
            "https://mock.confluence.com/x/no-id",
            "https://mock.confluence.com/some/other/path",
            None,
            None,
            "Could not extract page ID from the final resolved URL: https://mock.confluence.com/some/other/path",
        ),
        (
            "https://mock.confluence.com/x/fail",
            None,
            requests.exceptions.RequestException("Network issue"),
            None,
            "Could not resolve the short URL 'https://mock.confluence.com/x/fail'. Details: Network issue",
        ),
        (
            "https://mock.confluence.com/x/fail-gen",
            None,
            Exception("Generic error"),
            None,
            "Could not resolve the short URL 'https://mock.confluence.com/x/fail-gen'. Details: Generic error",
        ),
    ],
)
def test_get_page_id_from_url(
    safe_confluence_api_instance,
    mock_requests_head,
    caplog,
    url,
    head_response_url,
    head_side_effect,
    expected_id,
    expected_log_msg,
):
    mock_response = MagicMock()
    mock_response.url = head_response_url
    mock_response.raise_for_status.return_value = None

    if head_side_effect:
        mock_requests_head.side_effect = head_side_effect
    else:
        mock_requests_head.return_value = mock_response

    with caplog.at_level(logging.INFO):
        result = safe_confluence_api_instance.get_page_id_from_url(url)

        assert result == expected_id

        called_head = True
        if re.search(r"pageId=(\d+)", url) or re.search(r"/pages/(\d+)", url):
            called_head = False

        if not called_head:
            mock_requests_head.assert_not_called()
            assert not caplog.records
        else:
            mock_requests_head.assert_called_once_with(
                url,
                headers=safe_confluence_api_instance.headers,
                allow_redirects=True,
                timeout=5,
                verify=config.VERIFY_SSL,
            )
            assert "Attempting to resolve short URL" in caplog.text
            assert caplog.records[0].levelname == "INFO"

            if head_side_effect:
                assert expected_log_msg in caplog.text
                assert caplog.records[-1].levelname == "ERROR"
            elif expected_id is None:
                assert expected_log_msg in caplog.text
                assert caplog.records[-1].levelname == "ERROR"
            else:
                assert expected_log_msg in caplog.text
                assert caplog.records[1].levelname == "INFO"


# Test get_page_by_id and its fallbacks
@pytest.mark.parametrize(
    "page_id, client_side_effect, make_request_return_value, expected_log_msg_fragment, expected_return",
    [
        ("PAGE-1", None, None, None, {"id": "PAGE-1", "title": "Page 1"}),
        (
            "PAGE-2",
            requests.exceptions.RequestException("Net error"),
            MagicMock(json=lambda: {"id": "FB-2"}, status_code=200),
            "A network error occurred while get page 'PAGE-2'",
            {"id": "FB-2"},
        ),
        (
            "PAGE-3",
            Exception("Lib error"),
            MagicMock(json=lambda: {"id": "FB-3"}, status_code=200),
            "Library call get_page_by_id for 'PAGE-3' failed",
            {"id": "FB-3"},
        ),
        (
            "PAGE-4",
            requests.exceptions.RequestException("Net error"),
            None,
            "A network error occurred while get page 'PAGE-4'",
            None,
        ),
    ],
)
def test_get_page_by_id_resilience(
    safe_confluence_api_instance,
    mock_confluence_client,
    mock_make_request,
    caplog,
    page_id,
    client_side_effect,
    make_request_return_value,
    expected_log_msg_fragment,
    expected_return,
):
    expand_param = "body"

    if client_side_effect:
        mock_confluence_client.get_page_by_id.side_effect = client_side_effect
    else:
        mock_confluence_client.get_page_by_id.return_value = expected_return

    mock_make_request.return_value = make_request_return_value

    with caplog.at_level(logging.WARNING):
        result = safe_confluence_api_instance.get_page_by_id(
            page_id, expand=expand_param
        )

        assert result == expected_return
        mock_confluence_client.get_page_by_id.assert_called_once_with(
            page_id, expand=expand_param
        )

        if client_side_effect:
            mock_make_request.assert_called_once_with(
                "GET",
                f"{safe_confluence_api_instance.base_url}/rest/api/content/{page_id}",
                headers=safe_confluence_api_instance.headers,
                params={"expand": expand_param},
                verify_ssl=config.VERIFY_SSL,
            )
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# Test get_page_child_by_type and its fallbacks with pagination
@pytest.mark.parametrize(
    "parent_id, client_side_effect, make_request_responses, expected_log_msg_fragment, expected_return_ids",
    [
        ("PARENT-1", None, None, None, [{"id": "CHILD-1"}]),
        (
            "PARENT-2",
            Exception("Lib error"),
            [
                MagicMock(
                    json=MagicMock(return_value={"results": [{"id": "FB-CHILD-1"}]}),
                    status_code=200,
                )
            ],
            "Library get_page_child_by_type for 'PARENT-2' failed",
            [{"id": "FB-CHILD-1"}],
        ),
        (
            "PARENT-3",
            Exception("Lib error"),
            [
                MagicMock(
                    json=MagicMock(
                        return_value={
                            "results": [{"id": "FB-CHILD-A"}, {"id": "FB-CHILD-B"}],
                            "_links": {"next": True},
                        }
                    ),
                    status_code=200,
                ),
                MagicMock(
                    json=MagicMock(
                        return_value={"results": [{"id": "FB-CHILD-C"}], "_links": {}}
                    ),
                    status_code=200,
                ),  # Last page
            ],
            "Library get_page_child_by_type for 'PARENT-3' failed",
            [{"id": "FB-CHILD-A"}, {"id": "FB-CHILD-B"}, {"id": "FB-CHILD-C"}],
        ),
        (
            "PARENT-4",
            Exception("Lib error"),
            [None],
            "Failed to retrieve child pages for 'PARENT-4'",
            [],
        ),
    ],
)
def test_get_page_child_by_type_resilience(
    safe_confluence_api_instance,
    mock_confluence_client,
    mock_make_request,
    caplog,
    parent_id,
    client_side_effect,
    make_request_responses,
    expected_log_msg_fragment,
    expected_return_ids,
):
    page_type = "page"

    if client_side_effect:
        mock_confluence_client.get_page_child_by_type.side_effect = client_side_effect
    else:
        mock_confluence_client.get_page_child_by_type.return_value = expected_return_ids

    if make_request_responses:
        mock_make_request.side_effect = make_request_responses
    else:
        pass

    with caplog.at_level(logging.WARNING):
        result = safe_confluence_api_instance.get_page_child_by_type(
            parent_id, page_type
        )

        assert result == expected_return_ids
        mock_confluence_client.get_page_child_by_type.assert_called_once_with(
            parent_id, type=page_type
        )

        if client_side_effect:
            expected_calls = []
            current_start = 0
            for response_mock_or_none in make_request_responses:
                limit = 50
                url = (
                    f"{safe_confluence_api_instance.base_url}/rest/api/content/{parent_id}/child/{page_type}"
                    f"?start={current_start}&limit={limit}"
                )
                expected_calls.append(
                    call(
                        "GET",
                        url,
                        headers=safe_confluence_api_instance.headers,
                        verify_ssl=config.VERIFY_SSL,
                    )
                )

                if response_mock_or_none is None:
                    break

                data_from_mock = (
                    response_mock_or_none.json.return_value
                    if hasattr(response_mock_or_none, "json")
                    and isinstance(response_mock_or_none.json, MagicMock)
                    else response_mock_or_none.json
                )

                current_results_len = len(data_from_mock.get("results", []))

                if not current_results_len and "next" not in data_from_mock.get(
                    "_links", {}
                ):
                    break

                if current_results_len > 0 and "next" not in data_from_mock.get(
                    "_links", {}
                ):
                    pass

                current_start += current_results_len

            mock_make_request.assert_has_calls(expected_calls, any_order=False)
            assert mock_make_request.call_count == len(expected_calls)

            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
            if make_request_responses and make_request_responses[0] is None:
                assert caplog.records[-1].levelname == "ERROR"

        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# Test update_page and its fallbacks (including the bug fix)
@pytest.mark.parametrize(
    "page_id, title, body, client_side_effect, get_page_by_id_return_config, make_request_update_response, expected_return, expected_log_msg_fragment, expected_fallback_error_log",
    [
        ("UPD-1", "New Title", "New Body", None, None, None, True, None, None),
        (
            "UPD-2",
            "New Title",
            "New Body",
            requests.exceptions.RequestException("Net error"),
            {"id": "UPD-2", "title": "Page Title", "version": {"number": 1}},
            MagicMock(status_code=200),
            True,
            "A network error occurred while update page 'UPD-2'",
            None,
        ),
        (
            "UPD-3",
            "New Title",
            "New Body",
            Exception("Lib error"),
            {"id": "UPD-3", "title": "Page Title", "version": {"number": 1}},
            MagicMock(status_code=200),
            True,
            "Library update_page for 'UPD-3' failed",
            None,
        ),
        (
            "UPD-4",
            "New Title",
            "New Body",
            Exception("Lib error"),
            None,
            None,
            False,
            "Library update_page for 'UPD-4' failed",
            "Could not retrieve page 'UPD-4' for update (during fallback).",
        ),
        (
            "UPD-5",
            "New Title",
            "New Body",
            Exception("Lib error"),
            {"id": "UPD-5", "title": "Page Title", "version": {"number": 1}},
            None,
            False,
            "Library update_page for 'UPD-5' failed",
            None,
        ),
    ],
)
def test_update_page_resilience(
    safe_confluence_api_instance,
    mock_confluence_client,
    mock_make_request,
    caplog,
    mocker,
    page_id,
    title,
    body,
    client_side_effect,
    get_page_by_id_return_config,
    make_request_update_response,
    expected_return,
    expected_log_msg_fragment,
    expected_fallback_error_log,
):
    # Mock internal get_page_by_id call within _fallback_update_page
    mocker.patch.object(
        safe_confluence_api_instance,
        "get_page_by_id",
        return_value=get_page_by_id_return_config,
    )

    if client_side_effect:
        mock_confluence_client.update_page.side_effect = client_side_effect
    else:
        mock_confluence_client.update_page.return_value = expected_return

    mock_make_request.return_value = make_request_update_response

    with caplog.at_level(logging.INFO):  # Watch for INFO, WARNING, ERROR
        result = safe_confluence_api_instance.update_page(page_id, title, body)

        assert result == expected_return
        mock_confluence_client.update_page.assert_called_once_with(
            page_id=page_id, title=title, body=body
        )

        if client_side_effect:  # This path covers fallback scenarios
            # Verify get_page_by_id was called within fallback
            safe_confluence_api_instance.get_page_by_id.assert_called_once_with(
                page_id, expand="version"
            )

            if expected_fallback_error_log:  # Check for the specific fallback error log
                found_log = False
                for record in caplog.records:
                    if (
                        expected_fallback_error_log in record.message
                        and record.levelname == "ERROR"
                    ):
                        found_log = True
                        break
                assert found_log, f"Expected ERROR log '{expected_fallback_error_log}' not found in logs: {caplog.text}"
                mock_make_request.assert_not_called()  # No PUT request if get_page_by_id fails in fallback
            elif get_page_by_id_return_config:  # If current_page was retrieved successfully (and no specific fallback error)
                mock_make_request.assert_called_once_with(
                    "PUT",
                    f"{safe_confluence_api_instance.base_url}/rest/api/content/{page_id}",
                    headers=safe_confluence_api_instance.headers,
                    json_data={
                        "version": {
                            "number": get_page_by_id_return_config["version"]["number"]
                            + 1
                        },
                        "type": "page",
                        "title": title,
                        "body": {
                            "storage": {"value": body, "representation": "storage"}
                        },
                    },
                    verify_ssl=config.VERIFY_SSL,
                )
            else:  # get_page_by_id failed within fallback, and no specific error log (shouldn't happen with updated logic)
                mock_make_request.assert_not_called()

            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:  # Happy path (primary client success)
            safe_confluence_api_instance.get_page_by_id.assert_not_called()
            mock_make_request.assert_not_called()
            # Assert for the specific INFO log on success
            assert (
                f"Successfully updated page {page_id} via library call." in caplog.text
            )
            # The level should be INFO for success log
            assert caplog.records[0].levelname == "INFO"


# Test create_page and its fallbacks
@pytest.mark.parametrize(
    "client_side_effect, make_request_return_value, expected_return_value, expected_log_msg_fragment",
    [
        (None, None, {"id": "NEW-1"}, None),  # Primary success
        (
            requests.exceptions.RequestException("Net error"),
            MagicMock(json=lambda: {"id": "FB-NEW-1"}, status_code=201),
            {"id": "FB-NEW-1"},
            "A network error occurred while create page.",
        ),  # Lib net error, fallback success
        (
            Exception("Lib error"),
            MagicMock(json=lambda: {"id": "FB-NEW-2"}, status_code=201),
            {"id": "FB-NEW-2"},
            "Library create_page failed.",
        ),  # Lib generic error, fallback success
        (
            requests.exceptions.RequestException("Net error"),
            None,
            None,
            "A network error occurred while create page.",
        ),  # Total failure
    ],
)
def test_create_page_resilience(
    safe_confluence_api_instance,
    mock_confluence_client,
    mock_make_request,
    caplog,
    client_side_effect,
    make_request_return_value,
    expected_return_value,
    expected_log_msg_fragment,
):
    kwargs_payload = {
        "space": "SPACE",
        "title": "New Page",
        "body": "Page content",
        "parent_id": "PARENT-1",
    }

    if client_side_effect:
        mock_confluence_client.create_page.side_effect = client_side_effect
    else:
        mock_confluence_client.create_page.return_value = expected_return_value

    mock_make_request.return_value = make_request_return_value

    with caplog.at_level(logging.WARNING):
        result = safe_confluence_api_instance.create_page(**kwargs_payload)

        assert result == expected_return_value
        mock_confluence_client.create_page.assert_called_once_with(**kwargs_payload)

        if client_side_effect:
            expected_payload = {
                "type": "page",
                "title": kwargs_payload["title"],
                "space": {"key": kwargs_payload["space"]},
                "body": {
                    "storage": {
                        "value": kwargs_payload["body"],
                        "representation": "storage",
                    }
                },
                "ancestors": [{"id": kwargs_payload["parent_id"]}],
            }
            mock_make_request.assert_called_once_with(
                "POST",
                f"{safe_confluence_api_instance.base_url}/rest/api/content",
                headers=safe_confluence_api_instance.headers,
                json_data=expected_payload,
                verify_ssl=config.VERIFY_SSL,
            )
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# Test user details methods and their fallbacks
@pytest.mark.parametrize(
    "method_name, identifier_type, identifier_value, client_side_effect, make_request_return_value, expected_log_msg_fragment, expected_return",
    [
        (
            "get_user_details_by_username",
            "username",
            "testuser",
            None,
            None,
            None,
            {"username": "testuser", "displayName": "Test User"},
        ),
        (
            "get_user_details_by_username",
            "username",
            "testuser",
            requests.exceptions.RequestException("Net error"),
            MagicMock(json=lambda: {"username": "fb_user"}, status_code=200),
            "Library get_user_details_by_username failed.",
            {"username": "fb_user"},
        ),
        (
            "get_user_details_by_username",
            "username",
            "testuser",
            Exception("Lib error"),
            None,
            "Library get_user_details_by_username failed.",
            None,
        ),
        (
            "get_user_details_by_userkey",
            "key",
            "testkey",
            None,
            None,
            None,
            {"key": "testkey", "displayName": "Test User Key"},
        ),
        (
            "get_user_details_by_userkey",
            "key",
            "testkey",
            requests.exceptions.RequestException("Net error"),
            MagicMock(json=lambda: {"key": "fb_key"}, status_code=200),
            "Library get_user_details_by_userkey failed.",
            {"key": "fb_key"},
        ),
        (
            "get_user_details_by_userkey",
            "key",
            "testkey",
            Exception("Lib error"),
            None,
            "Library get_user_details_by_userkey failed.",
            None,
        ),
    ],
)
def test_get_user_details_resilience(
    safe_confluence_api_instance,
    mock_confluence_client,
    mock_make_request,
    caplog,
    method_name,
    identifier_type,
    identifier_value,
    client_side_effect,
    make_request_return_value,
    expected_log_msg_fragment,
    expected_return,
):
    client_method = getattr(mock_confluence_client, method_name)

    if client_side_effect:
        client_method.side_effect = client_side_effect
    else:
        client_method.return_value = expected_return

    mock_make_request.return_value = make_request_return_value

    with caplog.at_level(logging.WARNING):
        api_method = getattr(safe_confluence_api_instance, method_name)
        result = api_method(identifier_value)

        assert result == expected_return
        client_method.assert_called_once_with(identifier_value)

        if client_side_effect:
            mock_make_request.assert_called_once_with(
                "GET",
                f"{safe_confluence_api_instance.base_url}/rest/api/user?{identifier_type}={identifier_value}",
                headers=safe_confluence_api_instance.headers,
                verify_ssl=config.VERIFY_SSL,
            )
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"
        else:
            mock_make_request.assert_not_called()
            assert not caplog.records


# Test get_all_descendants (recursive)
def test_get_all_descendants(safe_confluence_api_instance, mocker):
    """Test recursive retrieval of all descendant page IDs."""
    # Mock get_page_child_by_type to control recursion
    mocker.patch.object(
        safe_confluence_api_instance,
        "get_page_child_by_type",
        side_effect=[
            # First call for PARENT-1
            [{"id": "CHILD-A"}, {"id": "CHILD-B"}],
            # Second call for CHILD-A
            [{"id": "GRANDCHILD-A1"}],
            # Third call for GRANDCHILD-A1
            [],  # No further children
            # Fourth call for CHILD-B
            [{"id": "GRANDCHILD-B1"}, {"id": "GRANDCHILD-B2"}],
            # Fifth call for GRANDCHILD-B1
            [],
            # Sixth call for GRANDCHILD-B2
            [],
        ],
    )

    expected_descendants = [
        "CHILD-A",
        "GRANDCHILD-A1",
        "CHILD-B",
        "GRANDCHILD-B1",
        "GRANDCHILD-B2",
    ]
    result = safe_confluence_api_instance.get_all_descendants("PARENT-1")

    assert result == expected_descendants
    # Verify calls to get_page_child_by_type
    assert safe_confluence_api_instance.get_page_child_by_type.call_count == 6
    safe_confluence_api_instance.get_page_child_by_type.assert_has_calls(
        [
            call("PARENT-1", page_type="page"),
            call("CHILD-A", page_type="page"),
            call("GRANDCHILD-A1", page_type="page"),
            call("CHILD-B", page_type="page"),
            call("GRANDCHILD-B1", page_type="page"),
            call("GRANDCHILD-B2", page_type="page"),
        ]
    )


# Test HTML Parsing: get_tasks_from_page and _parse_single_task
@pytest.mark.parametrize(
    "page_html, page_details_input, aggregation_macros, user_details_return, expected_tasks",
    [
        # No tasks
        ("<p>No tasks here</p>", {"id": "1", "title": "Page"}, [], None, []),
        # Single incomplete task, no assignee, no due date
        (
            "<ac:task-list><ac:task><ac:task-id>t1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task Summary</ac:task-body></ac:task></ac:task-list>",
            {
                "id": "1",
                "title": "Page",
                "_links": {"webui": "http://page.url"},
                "version": {"number": 1, "by": {"displayName": "User"}, "when": "now"},
            },
            [],
            None,
            [
                ConfluenceTask(
                    confluence_page_id="1",
                    confluence_page_title="Page",
                    confluence_page_url="http://page.url",
                    confluence_task_id="t1",
                    task_summary="Task Summary",
                    status="incomplete",
                    assignee_name=None,
                    due_date="2025-01-01",
                    original_page_version=1,
                    original_page_version_by="User",
                    original_page_version_when="now",
                    context="Test Context",
                )
            ],
        ),
        # Complete task with assignee and due date
        (
            """<ac:task-list><ac:task>
        <ac:task-id>t2</ac:task-id>
        <ac:task-status>complete</ac:task-status>
        <ac:task-body>Another Task <ri:user ri:userkey="userkey123"/></ac:task-body>
        <time datetime="2025-06-30"></time>
       </ac:task></ac:task-list>""",
            {
                "id": "2",
                "title": "Page2",
                "_links": {"webui": "http://page2.url"},
                "version": {
                    "number": 2,
                    "by": {"displayName": "User2"},
                    "when": "now2",
                },
            },
            [],
            {"username": "assignee_user"},
            [
                ConfluenceTask(
                    confluence_page_id="2",
                    confluence_page_title="Page2",
                    confluence_page_url="http://page2.url",
                    confluence_task_id="t2",
                    task_summary="Another Task",
                    status="complete",
                    assignee_name="assignee_user",
                    due_date="2025-06-30",
                    original_page_version=2,
                    original_page_version_by="User2",
                    original_page_version_when="now2",
                    context="Test Context",
                )
            ],
        ),
        # Task inside aggregation macro (should be skipped)
        (
            """<ac:structured-macro ac:name="jira-issues"><ac:rich-text-body>
        <ac:task-list><ac:task><ac:task-id>t3</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Aggregated Task</ac:task-body></ac:task></ac:task-list>
       </ac:rich-text-body></ac:structured-macro>""",
            {"id": "3", "title": "Page3"},
            ["jira-issues"],
            None,
            [],
        ),
        # Malformed task (missing task-body)
        (
            "<ac:task-list><ac:task><ac:task-id>t4</ac:task-id><ac:task-status>incomplete</ac:task-status></ac:task></ac:task-list>",
            {"id": "4", "title": "Page4"},
            [],
            None,
            [],
        ),
        # Task with nested task list (should be removed from summary)
        (
            """<ac:task-list><ac:task><ac:task-id>t5</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Parent task
        <ac:task-list><ac:task><ac:task-id>t6</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Nested task</ac:task-body></ac:task></ac:task-list>
       </ac:task-body></ac:task></ac:task-list>""",
            {
                "id": "5",
                "title": "Page5",
                "_links": {"webui": "http://page5.url"},
                "version": {
                    "number": 5,
                    "by": {"displayName": "Page Author"},
                    "when": "2024-07-13T12:00:00.000Z",
                },
            },
            [],
            None,
            [
                ConfluenceTask(
                    confluence_page_id="5",
                    confluence_page_title="Page5",
                    confluence_page_url="http://page5.url",
                    confluence_task_id="t5",
                    task_summary="Parent task",
                    status="incomplete",
                    assignee_name=None,
                    due_date="2025-01-01",
                    original_page_version=5,
                    original_page_version_by="Page Author",
                    original_page_version_when="2024-07-13T12:00:00.000Z",
                    context="Test Context",
                )
            ],
        ),
    ],
)
def test_get_tasks_from_page(
    safe_confluence_api_instance,
    mock_config_values,
    mock_get_task_context,
    mocker,
    page_html,
    page_details_input,
    aggregation_macros,
    user_details_return,
    expected_tasks,
):
    # Patch config.AGGREGATION_CONFLUENCE_MACRO for test specific aggregation macros
    mocker.patch.object(config, "AGGREGATION_CONFLUENCE_MACRO", new=aggregation_macros)

    # Mock get_user_details_by_userkey if user_details_return is provided
    # The SafeConfluenceApi.get_user_details_by_userkey method is called by _parse_single_task
    if user_details_return is not None:
        mocker.patch.object(
            safe_confluence_api_instance,
            "get_user_details_by_userkey",
            return_value=user_details_return,
        )
    else:
        # Ensure it returns None if not mocked for success (e.g., assignee_name=None tests)
        mocker.patch.object(
            safe_confluence_api_instance,
            "get_user_details_by_userkey",
            return_value=None,
        )

    page_details_input_with_body = page_details_input.copy()
    page_details_input_with_body["body"] = {"storage": {"value": page_html}}

    # The actual test
    tasks = safe_confluence_api_instance.get_tasks_from_page(
        page_details_input_with_body
    )

    assert tasks == expected_tasks

    # Assert get_user_details_by_userkey calls if an assignee was in the HTML
    if "ri:userkey" in page_html:  # Check if ri:userkey tag is present in the HTML
        safe_confluence_api_instance.get_user_details_by_userkey.assert_called_once()
    else:
        safe_confluence_api_instance.get_user_details_by_userkey.assert_not_called()


# ---TO BE REFACTORED OUT ---#


# Test HTML Manipulation: update_page_with_jira_links and _generate_jira_macro_html
@pytest.mark.parametrize(
    "page_html_input, mappings, get_page_return_config, update_page_call_expected, expected_log_msg_fragment, expected_jira_macro_count, expected_unmapped_task_ids, should_task_list_be_removed",
    [
        # No mappings, no update
        (
            "<p>No tasks</p>",
            [],
            {
                "id": "page-to-update",
                "title": "Page Title",
                "body": {"storage": {"value": "<p>No tasks</p>"}},
                "version": {"number": 1},
            },
            False,
            "No tasks were replaced",
            0,
            [],
            True,
        ),
        # Page not found, no update
        (
            "<ac:task-list><ac:task><ac:task-id>t1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task</ac:task-body></ac:task></ac:task-list>",
            [{"confluence_task_id": "t1", "jira_key": "JIRA-1"}],
            None,
            False,
            "Could not retrieve page",
            0,
            [],
            False,
        ),
        # Single task replaced
        (
            """<ac:task-list><ac:task><ac:task-id>t1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task</ac:task-body></ac:task></ac:task-list>""",
            [{"confluence_task_id": "t1", "jira_key": "JIRA-1"}],
            {
                "id": "page-to-update",
                "title": "Page Title",
                "body": {
                    "storage": {
                        "value": """<ac:task-list><ac:task><ac:task-id>t1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task</ac:task-body></ac:task></ac:task-list>"""
                    }
                },
                "version": {"number": 1},
            },
            True,
            "Prepared task 't1' for replacement",
            1,
            [],
            True,
        ),
        # Multiple tasks replaced in same list, one not mapped
        (
            """<ac:task-list>
            <ac:task><ac:task-id>t1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1</ac:task-body></ac:task>
            <ac:task><ac:task-id>t_unmapped</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Unmapped Task</ac:task-body></ac:task>
            <ac:task><ac:task-id>t2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 2</ac:task-body></ac:task>
           </ac:task-list>""",
            [
                {"confluence_task_id": "t1", "jira_key": "JIRA-1"},
                {"confluence_task_id": "t2", "jira_key": "JIRA-2"},
            ],
            {
                "id": "page-to-update",
                "title": "Page Title",
                "body": {
                    "storage": {
                        "value": """<ac:task-list>
            <ac:task><ac:task-id>t1</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 1</ac:task-body></ac:task>
            <ac:task><ac:task-id>t_unmapped</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Unmapped Task</ac:task-body></ac:task>
            <ac:task><ac:task-id>t2</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Task 2</ac:task-body></ac:task>
           </ac:task-list>"""
                    }
                },
                "version": {"number": 1},
            },
            True,
            "Prepared task 't1' for replacement",
            2,
            ["t_unmapped"],
            False,
        ),
    ],
)
def test_update_page_with_jira_links(
    safe_confluence_api_instance,
    mock_config_values,
    mock_uuid_uuid4,
    mocker,
    caplog,
    page_html_input,
    mappings,
    get_page_return_config,
    update_page_call_expected,
    expected_log_msg_fragment,
    expected_jira_macro_count,
    expected_unmapped_task_ids,
    should_task_list_be_removed,
):  # Adjusted parameters
    page_id = "page-to-update"

    mocker.patch.object(
        safe_confluence_api_instance,
        "get_page_by_id",
        return_value=get_page_return_config,
    )
    mocker.patch.object(
        safe_confluence_api_instance,
        "update_page",
        return_value=update_page_call_expected,
    )

    with caplog.at_level(logging.INFO):
        safe_confluence_api_instance.update_page_with_jira_links(page_id, mappings)

        safe_confluence_api_instance.get_page_by_id.assert_called_once_with(
            page_id, expand="body.storage,version"
        )

        if (
            not get_page_return_config
        ):  # Page not retrieved (get_page_by_id returned None)
            assert expected_log_msg_fragment in caplog.text
            assert (
                "Could not retrieve page" in caplog.text
            )  # Specific log message from source code
            safe_confluence_api_instance.update_page.assert_not_called()
        elif not mappings or not any(
            task_id in m["confluence_task_id"]
            for m in mappings
            for task_id in re.findall(
                r"<ac:task-id>(.*?)</ac:task-id>", page_html_input
            )
        ):  # No modifications or unmapped tasks
            safe_confluence_api_instance.update_page.assert_not_called()
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "WARNING"  # "No tasks were replaced"
        else:  # Page retrieved and tasks were mapped and replaced
            safe_confluence_api_instance.update_page.assert_called_once()
            assert expected_log_msg_fragment in caplog.text
            assert caplog.records[0].levelname == "INFO"  # "Prepared task ..."

            called_title = safe_confluence_api_instance.update_page.call_args[0][1]
            called_body_html = safe_confluence_api_instance.update_page.call_args[0][2]

            assert called_title == get_page_return_config["title"]

            actual_soup = BeautifulSoup(called_body_html, "html.parser")

            # Assert number of Jira macros
            jira_macros = actual_soup.find_all(
                "ac:structured-macro", {"ac:name": "jira"}
            )
            assert len(jira_macros) == expected_jira_macro_count

            # Assert content of Jira macros
            actual_macro_keys = []
            for macro in jira_macros:
                assert macro.get("ac:macro-id") == "test-macro-uuid"
                server_param = macro.find("ac:parameter", {"ac:name": "server"})
                serverId_param = macro.find("ac:parameter", {"ac:name": "serverId"})
                key_param = macro.find("ac:parameter", {"ac:name": "key"})

                assert (
                    server_param
                    and server_param.string == config.JIRA_MACRO_SERVER_NAME
                )
                assert (
                    serverId_param
                    and serverId_param.string == config.JIRA_MACRO_SERVER_ID
                )

                if key_param:
                    actual_macro_keys.append(key_param.string)

            # FIX: Use sorted comparison for macro keys to handle order differences
            expected_macro_keys_from_mappings = sorted(
                [m["jira_key"] for m in mappings]
            )
            assert sorted(actual_macro_keys) == expected_macro_keys_from_mappings

            # Assert unmapped tasks remain (if any)
            remaining_tasks = actual_soup.find_all("ac:task")
            remaining_task_ids = [
                t.find("ac:task-id").string
                for t in remaining_tasks
                if t.find("ac:task-id")
            ]
            assert sorted(remaining_task_ids) == sorted(expected_unmapped_task_ids)

            # Assert empty task lists are removed or not based on should_task_list_be_removed
            if should_task_list_be_removed:
                assert not actual_soup.find(
                    "ac:task-list"
                )  # No task lists should remain
            else:
                assert actual_soup.find(
                    "ac:task-list"
                )  # At least one task list should remain


def test_generate_jira_macro_html(
    safe_confluence_api_instance, mock_config_values, mock_uuid_uuid4
):
    """Test _generate_jira_macro_html produces correct HTML."""
    jira_key = "PROJ-123"
    expected_html = (
        f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" '
        f'ac:macro-id="test-macro-uuid">'
        f'<ac:parameter ac:name="server">{config.JIRA_MACRO_SERVER_NAME}</ac:parameter>'
        f'<ac:parameter ac:name="serverId">{config.JIRA_MACRO_SERVER_ID}</ac:parameter>'
        f'<ac:parameter ac:name="key">{jira_key}</ac:parameter>'
        f"</ac:structured-macro></p>"
    )
    result_html = safe_confluence_api_instance._generate_jira_macro_html(jira_key)

    # Compare BeautifulSoup objects to ignore whitespace differences
    soup_expected = BeautifulSoup(expected_html, "html.parser")
    soup_result = BeautifulSoup(result_html, "html.parser")
    assert str(soup_expected) == str(soup_result)
