import logging
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.config import config
from src.api.https_helper import (
    HTTPSHelper,
    HTTPXClientError,
    HTTPXServerError,
    HTTPXCustomError,
)

# Configure logging to capture messages during tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def https_helper_instance() -> HTTPSHelper:
    """Provides an HTTPSHelper instance for testing."""
    return HTTPSHelper(verify_ssl=True)


@pytest.fixture(autouse=True)
def mock_httpx_client(
    https_helper_instance: HTTPSHelper,
) -> AsyncMock:
    """
    Patches the httpx.AsyncClient instance within HTTPSHelper for testing.
    Provides a mock client with mock send, build_request, and aclose methods.
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.send = AsyncMock(spec=httpx.AsyncClient().send)
    mock_client.build_request = Mock(spec=httpx.AsyncClient().build_request)
    mock_client.aclose = AsyncMock(spec=httpx.AsyncClient().aclose)

    with patch.object(https_helper_instance, "_client", new=mock_client):
        yield mock_client


@pytest.mark.asyncio
async def test_make_request_success(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests successful _make_request call."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_send.return_value = mock_response

    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    response = await https_helper_instance._make_request(
        "GET", "http://test.com", timeout=config.API_REQUEST_TIMEOUT_SECONDS
    )

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=config.API_REQUEST_TIMEOUT_SECONDS,
    )
    mock_send.assert_awaited_once_with(mock_build_request.return_value)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_make_request_http_error(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request handling of HTTPStatusError."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found",
        request=httpx.Request("GET", "http://test.com"),
        response=mock_response,
    )
    mock_send.return_value = mock_response
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(HTTPXClientError):
        await https_helper_instance._make_request("GET", "http://test.com", timeout=config.API_REQUEST_TIMEOUT_SECONDS)

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=config.API_REQUEST_TIMEOUT_SECONDS,
    )
    mock_send.assert_awaited_once_with(mock_build_request.return_value)


@pytest.mark.asyncio
async def test_make_request_request_error(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request handling of RequestError."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_send.side_effect = httpx.RequestError(
        "Connection refused", request=httpx.Request("GET", "http://test.com")
    )
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(httpx.RequestError):
        await https_helper_instance._make_request("GET", "http://test.com",
        timeout=config.API_REQUEST_TIMEOUT_SECONDS)

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=config.API_REQUEST_TIMEOUT_SECONDS,
    )
    mock_send.assert_awaited_once_with(mock_build_request.return_value)


@pytest.mark.asyncio
async def test_get_method(https_helper_instance: HTTPSHelper) -> None:
    """Tests the get method."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_make_request.return_value = mock_response

        result = await https_helper_instance.get("http://test.com")

        mock_make_request.assert_awaited_once_with(
            "GET", "http://test.com", headers=None, params=None,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS
        )
        assert result == {"data": "test"}


@pytest.mark.asyncio
async def test_post_method(https_helper_instance: HTTPSHelper) -> None:
    """Tests the post method."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "123"}
        mock_make_request.return_value = mock_response

        result = await https_helper_instance.post(
            "http://test.com", json_data={"key": "value"}
        )

        mock_make_request.assert_awaited_once_with(
            "POST",
            "http://test.com",
            headers=None,
            json_data={"key": "value"},
            params=None,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS,
        )
        assert result == {"id": "123"}


@pytest.mark.asyncio
async def test_post_method_204_no_content(https_helper_instance: HTTPSHelper) -> None:
    """Tests the post method returns empty dict for 204 No Content."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 204
        mock_response.json.side_effect = httpx.DecodingError("No content to decode")
        mock_make_request.return_value = mock_response

        result = await https_helper_instance.post(
            "http://test.com", json_data={"key": "value"}
        )

        mock_make_request.assert_awaited_once_with(
            "POST",
            "http://test.com",
            headers=None,
            json_data={"key": "value"},
            params=None,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS,
        )
        assert result == {}


@pytest.mark.asyncio
async def test_put_method_204_no_content(https_helper_instance: HTTPSHelper) -> None:
    """Tests the put method returns empty dict for 204 No Content."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 204
        mock_response.json.side_effect = httpx.DecodingError("No content to decode")
        mock_make_request.return_value = mock_response

        result = await https_helper_instance.put(
            "http://test.com", json_data={"key": "value"}
        )

        mock_make_request.assert_awaited_once_with(
            "PUT",
            "http://test.com",
            headers=None,
            json_data={"key": "value"},
            params=None,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS,
        )
        assert result == {}


@pytest.mark.asyncio
async def test_delete_method_success(https_helper_instance: HTTPSHelper) -> None:
    """Tests the delete method for a successful response."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_make_request.return_value = mock_response

        response = await https_helper_instance.delete("http://test.com/123")

        mock_make_request.assert_awaited_once_with(
            "DELETE", "http://test.com/123", headers=None, params=None,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_make_request_with_redirects(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request with follow_redirects=True."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_send.return_value = mock_response

    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    response = await https_helper_instance._make_request(
        "GET", "http://test.com",
        timeout=config.API_REQUEST_TIMEOUT_SECONDS, follow_redirects=True
    )

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=None,
        json=None,
        params=None,
        timeout=config.API_REQUEST_TIMEOUT_SECONDS,
    )
    mock_send.assert_awaited_once_with(mock_build_request.return_value)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_make_request_with_headers_and_params(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request with headers and params."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_send.return_value = mock_response

    headers = {"Authorization": "Bearer token"}
    params = {"key": "value"}
    mock_build_request.return_value = httpx.Request(
        method="GET", url="http://test.com", headers=headers, params=params
    )

    response = await https_helper_instance._make_request(
        "GET", "http://test.com", headers=headers, params=params
    )

    mock_build_request.assert_called_once_with(
        method="GET",
        url="http://test.com",
        headers=headers,
        json=None,
        params=params,
        timeout=config.API_REQUEST_TIMEOUT_SECONDS,
    )
    mock_send.assert_awaited_once_with(mock_build_request.return_value)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_method_with_headers_and_params(
    https_helper_instance: HTTPSHelper,
) -> None:
    """Tests the get method with headers and params."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "more_test"}
        mock_make_request.return_value = mock_response

        headers = {"X-Custom-Header": "abc"}
        params = {"query": "xyz"}
        result = await https_helper_instance.get(
            "http://test.com/api", headers=headers, params=params
        )

        mock_make_request.assert_awaited_once_with(
            "GET", "http://test.com/api", headers=headers, params=params,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS
        )
        assert result == {"data": "more_test"}


@pytest.mark.asyncio
async def test_post_method_with_headers_and_params(
    https_helper_instance: HTTPSHelper,
) -> None:
    """Tests the post method with headers and params."""
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"status": "created"}
        mock_make_request.return_value = mock_response

        headers = {"Content-Type": "application/json"}
        params = {"action": "create"}
        json_data = {"name": "new_item"}
        result = await https_helper_instance.post(
            "http://test.com/items",
            headers=headers,
            params=params,
            json_data=json_data,
        )

        mock_make_request.assert_awaited_once_with(
            "POST",
            "http://test.com/items",
            headers=headers,
            json_data=json_data,
            params=params,
            timeout=config.API_REQUEST_TIMEOUT_SECONDS,
        )
        assert result == {"status": "created"}


@pytest.mark.asyncio
async def test_set_client_property(https_helper_instance: HTTPSHelper) -> None:
    """Tests setting the httpx.AsyncClient instance via the setter."""
    new_client = httpx.AsyncClient(verify=False)
    https_helper_instance.client = new_client
    assert https_helper_instance.client is new_client


@pytest.mark.asyncio
async def test_close_method(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests the close method and that it calls aclose on the client."""
    with patch("logging.Logger.info") as mock_log_info:
        await https_helper_instance.close()
        mock_httpx_client.aclose.assert_awaited_once()
        mock_log_info.assert_any_call("Closing httpx.AsyncClient.")
        mock_log_info.assert_any_call("httpx.AsyncClient closed successfully.")
        assert https_helper_instance._client is None


@pytest.mark.asyncio
async def test_close_method_no_client(https_helper_instance: HTTPSHelper) -> None:
    """Tests the close method when client is not initialized."""
    fresh_https_helper_instance = HTTPSHelper(verify_ssl=True)
    fresh_https_helper_instance._client = None

    with patch("src.api.https_helper.logger") as mock_logger:
        await fresh_https_helper_instance.close()
        mock_logger.info.assert_not_called()
        mock_logger.warning.assert_not_called()
        assert fresh_https_helper_instance._client is None


@pytest.mark.asyncio
async def test_make_request_unhandled_exception(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request handling of an unhandled exception."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_send.side_effect = Exception("An unexpected error occurred")
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(
        HTTPXCustomError,
        match=r"A critical unexpected error occurred for http://test\.com",
    ):
        await https_helper_instance._make_request("GET", "http://test.com")

    mock_build_request.assert_called_once()
    mock_send.assert_awaited_once()

@pytest.mark.asyncio
async def test_make_request_unhandled_exception(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request handling of an unhandled exception."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_send.side_effect = Exception("An unexpected error occurred")
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(
        HTTPXCustomError,
        match=r"A critical unexpected error occurred for http://test\.com",
    ):
        await https_helper_instance._make_request("GET", "http://test.com")

    mock_build_request.assert_called_once()
    mock_send.assert_awaited_once()

@pytest.mark.asyncio
async def test_make_request_server_error(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """Tests _make_request handling of HTTPStatusError for 5xx errors."""
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Service Unavailable",
        request=httpx.Request("GET", "http://test.com"),
        response=mock_response,
    )
    mock_send.return_value = mock_response
    mock_build_request.return_value = httpx.Request(method="GET", url="http://test.com")

    with pytest.raises(HTTPXServerError):
        await https_helper_instance._make_request("GET", "http://test.com", timeout=config.API_REQUEST_TIMEOUT_SECONDS)
    # Assert that the request was attempted mutiple time due to retry
    assert mock_build_request.call_count > 1
    assert mock_send.call_count > 1

@pytest.mark.asyncio
async def test_close_method_client_is_none(https_helper_instance: HTTPSHelper):
    """Tests the close method when _client is None."""
    https_helper_instance._client = None
    with patch("logging.Logger.info") as mock_log_info:
        await https_helper_instance.close()
        mock_log_info.assert_not_called()

@pytest.mark.asyncio
async def test_make_request_timeout_error(
    https_helper_instance: HTTPSHelper, mock_httpx_client: AsyncMock
) -> None:
    """
    Tests _make_request handling of TimeoutException to cover the timeout-specific except block.
    This covers lines 250-251 in https_helper.py.
    """
    mock_send = mock_httpx_client.send
    mock_build_request = mock_httpx_client.build_request
    request = httpx.Request("GET", "http://test.com")
    mock_build_request.return_value = request

    # Simulate a timeout exception
    mock_send.side_effect = httpx.TimeoutException("Timeout occurred", request=request)

    # The context manager should catch the TimeoutException and re-raise it as a custom error
    with pytest.raises(HTTPXCustomError, match="Request timed out"):
        await https_helper_instance._make_request("GET", "http://test.com")

    # Assert that the request was attempted exactly once
    assert mock_build_request.call_count == 1
    assert mock_send.call_count == 1


@pytest.mark.asyncio
async def test_put_method_with_200_ok_and_body(https_helper_instance: HTTPSHelper) -> None:
    """
    Tests the put method for a 200 OK response that includes a JSON body.
    This covers the `else` branch of `if response.status_code != 204:` in the put method.
    This covers the missed branch at line 424.
    """
    with patch.object(
        https_helper_instance, "_make_request", new_callable=AsyncMock
    ) as mock_make_request:
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200  # Not 204
        mock_response.json.return_value = {"status": "updated", "id": "123"}
        mock_make_request.return_value = mock_response

        result = await https_helper_instance.put("http://test.com/123", json_data={"key": "value"})

        # The result should be the JSON body, not an empty dict
        assert result == {"status": "updated", "id": "123"}
        mock_make_request.assert_awaited_once()
