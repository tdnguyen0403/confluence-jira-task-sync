import httpx
import logging
from typing import (
    Any,
    Dict,
    Optional,
)  # Keep List for general type hints if used elsewhere

logger = logging.getLogger(__name__)


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
        except httpx.HTTPStatusError as http_err:
            logger.error(
                f"HTTP Error during {method.upper()} to {url}: {http_err}. "
                f"Response text: {http_err.response.text if http_err.response else 'N/A'}"
            )
            raise
        except httpx.RequestError as req_err:
            logger.error(f"Request Error during {method.upper()} to {url}: {req_err}")
            raise
        except Exception as e:
            logger.critical(
                f"An unhandled error occurred during {method.upper()} to {url}: {e}",
                exc_info=True,
            )
            raise

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
