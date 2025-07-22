import httpx
import logging
from typing import (
    Any,
    Dict,
    Optional,
)  # Keep List for general type hints if used elsewhere
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


# Custom HTTPX Exceptions
# These exceptions are used to provide more context and control over error handling
class HTTPXCustomError(httpx.RequestError):
    """Base custom exception for errors originating from httpx_helper."""

    def __init__(self, message, request=None, response=None, original_exception=None):
        super().__init__(message, request=request)
        self.response = response
        self.original_exception = original_exception
        self.status_code = response.status_code if response else None
        self.details = response.text if response else None


class HTTPXConnectionError(HTTPXCustomError):
    """Custom exception for network connection errors (e.g., DNS, refused connection)."""

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


# Main HTTPS Helper Class
# This class provides methods for making asynchronous HTTPS requests with error handling and logging.
class HTTPSHelper:
    """
    A helper class for making asynchronous HTTPS requests using httpx.
    Manages a single httpx.AsyncClient instance for efficient connection pooling.
    """

    _client: Optional[httpx.AsyncClient] = None

    def __init__(self, verify_ssl: bool = True):
        """
        Initializes the HTTPSHelper.
        The httpx.AsyncClient instance should be managed externally (e.g., by FastAPI's lifespan)
        to ensure proper connection pooling and graceful shutdown.
        """
        self._verify_ssl = verify_ssl

    @property
    def client(self) -> httpx.AsyncClient:
        """
        Provides access to the httpx.AsyncClient instance.
        Ensures the client is initialized.
        """
        if self._client is None:
            logger.warning(
                "httpx.AsyncClient not set. Initializing a new client. Consider using FastAPI lifespan for proper management."
            )
            self._client = httpx.AsyncClient(
                verify=self._verify_ssl, cookies=httpx.Cookies()
            )
        return self._client

    @client.setter
    def client(self, value: httpx.AsyncClient):
        """Allows setting the httpx.AsyncClient instance, typically from lifespan."""
        self._client = value

    # --- Main HTTPS Request Helper (with tenacity decorator applied) ---
    # Define retry conditions
    # Retry on specific httpx network/timeout errors
    RETRY_NETWORK_EXCEPTIONS = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ReadError,
        httpx.WriteError,
    )

    # Retry on specific custom server errors (propagated from httpx.HTTPStatusError 5xx)
    RETRY_SERVER_EXCEPTIONS = (HTTPXServerError,)

    @retry(
        wait=wait_exponential(
            multiplier=1, min=1, max=10
        ),  # Exponential backoff: 1s, 2s, 4s, 8s, 10s, 10s...
        stop=stop_after_attempt(5),  # Total 5 attempts (1 initial + 4 retries)
        retry=(
            retry_if_exception_type(
                RETRY_NETWORK_EXCEPTIONS
            )  # Retry if it's a network/timeout error
            | retry_if_exception_type(
                RETRY_SERVER_EXCEPTIONS
            )  # Retry if it's a 5xx server error
        ),
        reraise=True,  # Re-raise the last exception if all retries fail
    )
    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,  # Parameter to control redirect following
    ) -> httpx.Response:
        """
        Makes an asynchronous HTTPS request and handles common exceptions.

        Args:
            method (str): The HTTP method (e.g., 'GET', 'POST', 'PUT', 'DELETE').
            url (str): The URL for the request.
            headers (Optional[Dict[str, str]]): Dictionary of HTTP headers. Defaults to None.
            json_data (Optional[Dict[str, Any]]): JSON data to send in the request body. Defaults to None.
            params (Optional[Dict[str, str]]): Dictionary of URL parameters. Defaults to None.
            timeout (int): Request timeout in seconds. Defaults to 15.
            follow_redirects (bool): Whether to automatically follow HTTP redirects. Defaults to False.

        Returns:
            httpx.Response: The httpx response object.

        Raises:
            httpx.HTTPStatusError: For 4xx or 5xx responses.
            httpx.RequestError: For network-related errors (connection, timeout).
            Exception: For any other unexpected errors.
        """
        try:
            request_obj = self.client.build_request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=timeout,
            )

            response = await self.client.send(request_obj)

            # Explicitly check status code and only raise for 4xx or 5xx
            if 400 <= response.status_code < 600:
                # Re-raise the HTTPStatusError that httpx would normally create
                response.raise_for_status()

            logger.info(
                f"Successfully executed {method.upper()} request to {url}. Status: {response.status_code}"
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
                f"Request timed out for {url}", request=e.request, original_exception=e
            ) from e
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_details = e.response.text  # This is where redaction would ideally happen if sensitive data is logged
            log_message = f"HTTP Error for {method} {url} - Status: {status_code}, Details: {error_details}"
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
            # Catch any other httpx.RequestError not specifically handled above (e.g., ReadError, WriteError)
            logger.error(
                f"A general httpx.RequestError occurred while requesting {e.request.url!r}: {e}"
            )
            raise HTTPXCustomError(
                f"A general request error occurred for {url}",
                request=e.request,
                original_exception=e,
            ) from e
        except Exception as e:
            logger.critical(
                f"An unexpected and critical error occurred during HTTP request to {url}: {e}",
                exc_info=True,
            )
            raise HTTPXCustomError(
                f"A critical unexpected error occurred for {url}", original_exception=e
            ) from e

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,
    ) -> Dict[str, Any]:
        """Performs an asynchronous GET request and returns JSON response."""
        response = await self._make_request(
            "GET", url, headers=headers, params=params, timeout=timeout
        )
        return response.json()

    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 5,
        follow_redirects: bool = False,
    ) -> Any:  # Changed return type to Any
        """Performs an asynchronous POST request and returns JSON response if available, else None/empty dict for 204."""
        response = await self._make_request(
            "POST",
            url,
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
        )
        if response.status_code == 204:  # If No Content, return empty dict or None
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
    ) -> Any:  # Changed return type to Any
        """Performs an asynchronous PUT request and returns JSON response if available, else None/empty dict for 204."""
        response = await self._make_request(
            "PUT",
            url,
            headers=headers,
            params=params,
            json_data=json_data,
            timeout=timeout,
        )
        if response.status_code == 204:  # If No Content, return empty dict or None
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
        """Performs an asynchronous DELETE request and returns the response object."""
        response = await self._make_request(
            "DELETE", url, headers=headers, params=params, timeout=timeout
        )
        return response

    async def close(self):
        """Closes the httpx.AsyncClient if it was initialized."""
        if self._client:
            logger.info("Closing httpx.AsyncClient.")
            await self._client.aclose()  # Use aclose for AsyncClient
            self._client = None
            logger.info("httpx.AsyncClient closed successfully.")
