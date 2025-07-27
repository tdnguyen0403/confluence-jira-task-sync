"""
Provides a reusable and resilient asynchronous HTTP client.

This module contains the HTTPSHelper class, which is a wrapper around the
`httpx` library. It is designed to facilitate efficient and robust
communication with web services. Key features include:

-   **Asynchronous Requests:** Leverages `httpx.AsyncClient` for high-performance,
    non-blocking HTTP calls.
-   **Connection Pooling:** Manages a single client instance to reuse connections,
    improving efficiency.
-   **Automatic Retries:** Implements an exponential backoff retry strategy for
    transient network errors and 5xx server responses using the `tenacity`
    library.
-   **Custom Exceptions:** Defines a hierarchy of custom exceptions to provide
    more specific and actionable error handling for different HTTP failure
    scenarios.
-   **Structured Logging:** Includes detailed logging for requests, responses,
    errors, and retries to aid in debugging and monitoring.

The HTTPSHelper is intended to be a foundational component for any part of an
application that needs to make external HTTP requests reliably.
"""

import asyncio
import logging
from typing import (
    Any,
    Dict,
    Optional,
    cast,
)

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import config

logger = logging.getLogger(__name__)


class HTTPXCustomError(httpx.RequestError):
    """Base custom exception for errors originating from httpx_helper."""

    def __init__(
        self,
        message: str,
        request: Optional[httpx.Request] = None,
        response: Optional[httpx.Response] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        """
        Initializes the HTTPXCustomError.

        Args:
            message (str): A descriptive error message.
            request (Optional[httpx.Request]): The httpx Request object that
                caused the error.
            response (Optional[httpx.Response]): The httpx Response object if
                one was received.
            original_exception (Optional[Exception]): The original exception that
                was caught.
        """
        super().__init__(message, request=request)
        self.response = response
        self.original_exception = original_exception
        self.status_code = response.status_code if response else None
        self.details = response.text if response else None


class HTTPXConnectionError(HTTPXCustomError):
    """Custom exception for network connection errors
    (e.g., DNS, refused connection)."""

    pass


class HTTPXTimeoutError(HTTPXCustomError):
    """Custom exception for HTTPX request timeouts."""

    pass


class HTTPXClientError(HTTPXCustomError):
    """Custom exception for 4xx client errors from the API."""

    pass


class HTTPXServerError(HTTPXCustomError):
    """Custom exception for 5xx server errors from the API."""

    pass


class HTTPSHelper:
    """
    A helper class for making asynchronous HTTPS requests using httpx.
    Manages a single httpx.AsyncClient instance for efficient connection pooling.
    """

    _client: Optional[httpx.AsyncClient] = None
    _semaphore: Optional[asyncio.Semaphore] = None

    def __init__(self, verify_ssl: bool = True):
        """
        Initializes the HTTPSHelper.

        The httpx.AsyncClient instance should be managed externally (e.g., by
        FastAPI's lifespan) to ensure proper connection pooling and graceful
        shutdown.

        Args:
            verify_ssl (bool): Whether to verify the SSL certificate. Defaults to True.
        """
        self._verify_ssl = verify_ssl
        if HTTPSHelper._semaphore is None:
            HTTPSHelper._semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_API_CALLS)  # noqa: E501

    @property
    def client(self) -> httpx.AsyncClient:
        """
        Provides access to the httpx.AsyncClient instance.

        This property ensures that an `httpx.AsyncClient` is initialized and
        available for use. If the client has not been set externally (e.g.,
        via the `client` setter), it will create a new default client instance.

        Returns:
            httpx.AsyncClient: The active asynchronous client instance.
        """
        if self._client is None:
            logger.warning(
                "httpx.AsyncClient not set. Initializing a new client. "
                "Consider using FastAPI lifespan for proper management."
            )
            self._client = httpx.AsyncClient(
                verify=self._verify_ssl, cookies=httpx.Cookies()
            )
        return self._client

    @client.setter
    def client(self, value: httpx.AsyncClient) -> None:
        """
        Allows setting the httpx.AsyncClient instance, typically from lifespan.

        This setter is used to inject an externally managed `httpx.AsyncClient`
        instance, which is a best practice for applications where the client's
        lifecycle should be tied to the application's lifespan (e.g., in a
        FastAPI application).

        Args:
            value (httpx.AsyncClient): The `httpx.AsyncClient` instance to use.
        """
        self._client = value

    RETRY_NETWORK_EXCEPTIONS = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ReadError,
        httpx.WriteError,
    )

    RETRY_SERVER_EXCEPTIONS = (HTTPXServerError,)

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        retry=(
            retry_if_exception_type(RETRY_NETWORK_EXCEPTIONS)
            | retry_if_exception_type(RETRY_SERVER_EXCEPTIONS)
        ),
        reraise=True,
    )
    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        """
        Makes an asynchronous HTTPS request and handles common exceptions.

        This is the core method for all HTTP requests made by the helper. It
        builds and sends a request, handles status code validation, and wraps
        potential `httpx` exceptions in custom, more specific exception types.
        The `tenacity` decorator provides retry logic for transient errors.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST', 'PUT', 'DELETE').
            url (str): The URL for the request.
            headers (Optional[Dict[str, str]]): Dictionary of HTTP headers.
                Defaults to None.
            json_data (Optional[Dict[str, Any]]):
                JSON data to send in the request body.
                Defaults to None.
            params (Optional[Dict[str, str]]): Dictionary of URL parameters.
                Defaults to None.
            timeout (int): Request timeout in seconds. Defaults to 5.
            follow_redirects (bool): Whether to automatically follow HTTP redirects.
                Defaults to False.

        Returns:
            httpx.Response: The httpx response object on success.

        Raises:
            HTTPXClientError: For 4xx HTTP status codes.
            HTTPXServerError: For 5xx HTTP status codes, which may trigger retries.
            HTTPXConnectionError: For DNS or connection-refused errors.
            HTTPXTimeoutError: For request timeouts.
            HTTPXCustomError: For other `httpx` request-related errors or unexpected
                HTTP status codes.
        """
        async with HTTPSHelper._semaphore:
            current_timeout = (
                timeout if timeout is not None else config.API_REQUEST_TIMEOUT_SECONDS  # noqa: E501
            )
            try:
                request_obj = self.client.build_request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=current_timeout,
                )

                response = await self.client.send(request_obj)

                if 400 <= response.status_code < 600:
                    response.raise_for_status()

                logger.info(
                    f"Successfully executed {method.upper()} request to {url}. "
                    f"Status: {response.status_code}"
                )
                return response
            except httpx.ConnectError as e:
                logger.error(f"Connection Error for {method} {url}: {e}")
                raise HTTPXConnectionError(
                    f"Network connection failed to {url}",
                    request=e.request,
                    original_exception=e,
                ) from e
            except httpx.TimeoutException as e:
                logger.error(f"Timeout Error for {method} {url}: {e}")
                raise HTTPXTimeoutError(
                    f"Request timed out for {url}",
                    request=e.request,
                    original_exception=e,
                ) from e
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                error_details = e.response.text
                log_message = (
                    f"HTTP Error for {method} {url} - "
                    f"Status: {status_code}, Details: {error_details}"
                )
                if 400 <= status_code < 500:
                    logger.warning(log_message)
                    raise HTTPXClientError(
                        f"Client error from API ({status_code}) for {url}",
                        request=e.request,
                        response=e.response,
                        original_exception=e,
                    ) from e
                elif 500 <= status_code < 600:
                    logger.error(log_message)
                    raise HTTPXServerError(
                        f"Server error from API ({status_code}) for {url}",
                        request=e.request,
                        response=e.response,
                        original_exception=e,
                    ) from e
                else:
                    logger.error(log_message)
                    raise HTTPXCustomError(
                        f"Unexpected HTTP error ({status_code}) from API for {url}",
                        request=e.request,
                        response=e.response,
                        original_exception=e,
                    ) from e
            except httpx.RequestError as e:
                logger.error(
                    "A general httpx.RequestError occurred while "
                    f"requesting {e.request.url!r}: {e}"
                )
                raise HTTPXCustomError(
                    f"A general request error occurred for {url}",
                    request=e.request,
                    original_exception=e,
                ) from e
            except Exception as e:
                logger.critical(
                    "An unexpected and critical error occurred during "
                    f"HTTP request to {url}: {e}",
                    exc_info=True,
                )
                raise HTTPXCustomError(
                    f"A critical unexpected error occurred for {url}",
                    original_exception=e,
                ) from e

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,
    ) -> Dict[str, Any]:
        """
        Performs an asynchronous GET request and returns the JSON response.

        This method is a convenient wrapper around `_make_request` for the
        common case of making a GET request and expecting a JSON object as the
        response.

        Args:
            url (str): The URL for the GET request.
            headers (Optional[Dict[str, str]]): HTTP headers. Defaults to None.
            params (Optional[Dict[str, str]]): URL parameters. Defaults to None.
            timeout (int): Request timeout in seconds. Defaults to 5.
            follow_redirects (bool): Whether to follow redirects. Defaults to False.

        Returns:
            Dict[str, Any]: A dictionary parsed from the JSON response body.
        """
        response = await self._make_request(
            "GET", url, headers=headers, params=params, timeout=timeout
        )
        return cast(Dict[str, Any], response.json())

    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,
    ) -> Any:
        """
        Performs an asynchronous POST request.

        This method handles POST requests and returns the JSON response body if
        one is provided. It correctly handles cases like a 204 No Content
        response by returning an empty dictionary.

        Args:
            url (str): The URL for the POST request.
            headers (Optional[Dict[str, str]]): HTTP headers. Defaults to None.
            params (Optional[Dict[str, str]]): URL parameters. Defaults to None.
            json_data (Optional[Dict[str, Any]]): The JSON payload. Defaults to None.
            timeout (int): Request timeout in seconds. Defaults to 5.
            follow_redirects (bool): Whether to follow redirects. Defaults to False.

        Returns:
            Any: The parsed JSON response, or an empty dictionary for 204 responses.
        """
        response = await self._make_request(
            "POST",
            url,
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
        )
        if response.status_code == 204:
            return {}
        return response.json()

    async def put(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,
    ) -> Any:
        """
        Performs an asynchronous PUT request.

        This method handles PUT requests and returns the JSON response body if
        one is provided. It correctly handles cases like a 204 No Content
        response by returning an empty dictionary.

        Args:
            url (str): The URL for the PUT request.
            headers (Optional[Dict[str, str]]): HTTP headers. Defaults to None.
            params (Optional[Dict[str, str]]): URL parameters. Defaults to None.
            json_data (Optional[Dict[str, Any]]): The JSON payload. Defaults to None.
            timeout (int): Request timeout in seconds. Defaults to 5.
            follow_redirects (bool): Whether to follow redirects. Defaults to False.

        Returns:
            Any: The parsed JSON response, or an empty dictionary for 204 responses.
        """
        response = await self._make_request(
            "PUT",
            url,
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
        )
        if response.status_code == 204:
            return {}
        return response.json()

    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 5,
        params: Optional[Dict[str, str]] = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        """
        Performs an asynchronous DELETE request and returns the response object.

        Args:
            url (str): The URL for the DELETE request.
            headers (Optional[Dict[str, str]]): HTTP headers. Defaults to None.
            timeout (int): Request timeout in seconds. Defaults to 5.
            params (Optional[Dict[str, str]]): URL parameters. Defaults to None.
            follow_redirects (bool): Whether to follow redirects. Defaults to False.

        Returns:
            httpx.Response: The raw `httpx.Response` object.
        """
        response = await self._make_request(
            "DELETE", url, headers=headers, params=params, timeout=timeout
        )
        return response

    async def close(self) -> None:
        """
        Closes the httpx.AsyncClient if it was initialized.

        This method should be called to gracefully shut down the client and
        release its resources and connections. It is typically called during
        application shutdown (e.g., in a FastAPI `lifespan` event).
        """
        if self._client:
            logger.info("Closing httpx.AsyncClient.")
            await self._client.aclose()
            self._client = None
            logger.info("httpx.AsyncClient closed successfully.")
