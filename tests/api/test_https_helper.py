import pytest
import httpx
from unittest.mock import AsyncMock, patch, Mock  # Import Mock
import logging

from src.api.https_helper import HTTPSHelper

# Configure logging to capture messages during tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def https_helper_instance():
    """Provides an HTTPSHelper instance for testing."""
    return HTTPSHelper(verify_ssl=True)


# Use a fixture to patch the httpx.AsyncClient.send (AsyncMock) and build_request (Mock) methods.
# build_request is synchronous, so it should be a regular Mock.
@pytest.fixture(autouse=True)
def mock_httpx_client_methods(https_helper_instance):
    # Patch the 'send' method as AsyncMock (it's an async method)
    with patch.object(
        https_helper_instance.client, "send", new_callable=AsyncMock
    ) as mock_send, patch.object(
        https_helper_instance.client, "build_request", new_callable=Mock
    ) as mock_build_request:
        yield mock_send, mock_build_request


@pytest.mark.asyncio
async def test_make_request_success(https_helper_instance, mock_httpx_client_methods):
    """Tests successful _make_request call."""
    mock_send, mock_build_request = mock_httpx_client_methods

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_send.return_value = mock_response

    # Ensure build_request returns a httpx.Request object (it's a synchronous method)
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    # Explicitly pass follow_redirects=False to _make_request to match assertion
    # Use timeout=5 to match the default in HTTPSHelper._make_request
    response = await https_helper_instance._make_request(
        "GET", "http://test.com", timeout=5
    )

    # Assert build_request was called correctly
    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=5,
    )
    # Assert send was awaited once
    mock_send.assert_awaited_once_with(
        mock_build_request.return_value
    )  # <--- ADDED AWAIT
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_make_request_http_error(
    https_helper_instance, mock_httpx_client_methods
):
    """Tests _make_request handling of HTTPStatusError."""
    mock_send, mock_build_request = mock_httpx_client_methods

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found",
        request=httpx.Request("GET", "http://test.com"),
        response=mock_response,
    )
    mock_send.return_value = mock_response
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(httpx.HTTPStatusError):
        # Explicitly pass follow_redirects=False and timeout=5 to _make_request
        await https_helper_instance._make_request("GET", "http://test.com", timeout=5)

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=5,
    )
    mock_send.assert_awaited_once_with(
        mock_build_request.return_value
    )  # <--- ADDED AWAIT


@pytest.mark.asyncio
async def test_make_request_request_error(
    https_helper_instance, mock_httpx_client_methods
):
    """Tests _make_request handling of RequestError."""
    mock_send, mock_build_request = mock_httpx_client_methods

    mock_send.side_effect = httpx.RequestError(
        "Connection refused", request=httpx.Request("GET", "http://test.com")
    )
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(httpx.RequestError):
        # Explicitly pass follow_redirects=False and timeout=5 to _make_request
        await https_helper_instance._make_request("GET", "http://test.com", timeout=5)

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=5,
    )
    mock_send.assert_awaited_once_with(
        mock_build_request.return_value
    )  # <--- ADDED AWAIT


@pytest.mark.asyncio
async def test_get_method(https_helper_instance):
    """Tests the get method."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_make_request.return_value = mock_response

        # The get method's default timeout is 5, and follow_redirects is False
        result = await https_helper_instance.get("http://test.com")

        # Assert _make_request was called correctly, including the default timeout=5 and follow_redirects=False
        mock_make_request.assert_awaited_once_with(
            "GET", "http://test.com", headers=None, params=None, timeout=5
        )
        assert result == {"data": "test"}


@pytest.mark.asyncio
async def test_post_method(https_helper_instance):
    """Tests the post method."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "123"}
        mock_make_request.return_value = mock_response

        # The post method's default timeout is 5, and follow_redirects is False
        result = await https_helper_instance.post(
            "http://test.com", json_data={"key": "value"}
        )

        # Assert _make_request was called correctly, including the default timeout=5 and follow_redirects=False
        mock_make_request.assert_awaited_once_with(
            "POST",
            "http://test.com",
            headers=None,
            json_data={"key": "value"},
            params=None,
            timeout=5,
        )
        assert result == {"id": "123"}


@pytest.mark.asyncio
async def test_post_method_204_no_content(https_helper_instance):
    """Tests the post method returns empty dict for 204 No Content."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 204
        mock_response.json.side_effect = httpx.DecodingError("No content to decode")
        mock_make_request.return_value = mock_response

        # The post method's default timeout is 5, and follow_redirects is False
        result = await https_helper_instance.post(
            "http://test.com", json_data={"key": "value"}
        )

        # Assert _make_request was called correctly, including the default timeout=5 and follow_redirects=False
        mock_make_request.assert_awaited_once_with(
            "POST",
            "http://test.com",
            headers=None,
            json_data={"key": "value"},
            params=None,
            timeout=5,
        )
        assert result == {}


@pytest.mark.asyncio
async def test_put_method_204_no_content(https_helper_instance):
    """Tests the put method returns empty dict for 204 No Content."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 204
        mock_response.json.side_effect = httpx.DecodingError("No content to decode")
        mock_make_request.return_value = mock_response

        # The put method's default timeout is 5, and follow_redirects is False
        result = await https_helper_instance.put(
            "http://test.com", json_data={"key": "value"}
        )

        # Assert _make_request was called correctly, including the default timeout=5 and follow_redirects=False
        mock_make_request.assert_awaited_once_with(
            "PUT",
            "http://test.com",
            headers=None,
            json_data={"key": "value"},
            params=None,
            timeout=5,
        )
        assert result == {}
