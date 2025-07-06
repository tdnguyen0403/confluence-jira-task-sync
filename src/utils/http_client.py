import requests
import logging
import time # Import the standard time module
from typing import Dict, Any, Optional
from requests.exceptions import RequestException, Timeout, HTTPError
from src.exceptions import JiraConfluenceError

# Configure logging for this module
logger = logging.getLogger(__name__)

def make_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    retries: int = 3,
    backoff_factor: float = 0.5,
) -> requests.Response:
    """
    Makes an HTTP request with retry logic and comprehensive error handling.

    Args:
        method (str): The HTTP method (e.g., 'GET', 'POST', 'PUT', 'DELETE').
        url (str): The URL for the request.
        headers (Dict[str, str]): The HTTP headers for the request.
        json_data (Optional[Dict[str, Any]]): JSON payload for POST/PUT requests.
        params (Optional[Dict[str, Any]]): Query parameters for the request.
        timeout (int): The request timeout in seconds.
        retries (int): The number of times to retry the request on failure.
        backoff_factor (float): Factor for exponential backoff between retries.

    Returns:
        requests.Response: The response object if the request is successful.

    Raises:
        JiraConfluenceError: If the request fails after all retries or due to a
                             non-recoverable error.
    """
    for attempt in range(retries):
        try:
            logger.debug(f"Attempt {attempt + 1}/{retries}: {method} {url}")
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            logger.info(f"Request successful: {method} {url} - Status: {response.status_code}")
            return response
        except Timeout as e:
            logger.warning(f"Request timed out for {url} (Attempt {attempt + 1}/{retries}): {e}")
        except HTTPError as e:
            status_code = e.response.status_code if e.response else 'N/A'
            logger.error(f"HTTP error for {url} (Attempt {attempt + 1}/{retries}): Status {status_code} - {e.response.text if e.response else e}")
            if 400 <= status_code < 500 and status_code not in [408, 429]: # Client errors (except timeout/too many requests) are generally not retriable
                raise JiraConfluenceError(f"Client error during request to {url}: Status {status_code} - {e.response.text}") from e
        except RequestException as e:
            logger.warning(f"Network or connection error for {url} (Attempt {attempt + 1}/{retries}): {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during request to {url}: {e}")
            raise JiraConfluenceError(f"Unexpected error during request to {url}: {e}") from e

        if attempt < retries - 1:
            wait_time = backoff_factor * (2 ** attempt)
            logger.info(f"Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time) # Use time.sleep directly

    logger.error(f"Request failed after {retries} attempts: {method} {url}")
    raise JiraConfluenceError(f"Failed to make request to {url} after {retries} attempts.")

