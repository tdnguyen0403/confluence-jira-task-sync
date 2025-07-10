import requests
import logging
from typing import Optional, Dict, Any

# Configure logging for this module
logger = logging.getLogger(__name__)


def make_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    verify_ssl: bool = False,
) -> Optional[requests.Response]:
    """
    Makes an HTTPS request and handles common exceptions, returning the response object.

    Args:
        method (str): The HTTP method (e.g., 'GET', 'POST', 'PUT', 'DELETE').
        url (str): The URL for the request.
        headers (Optional[Dict[str, str]]): Dictionary of HTTP headers. Defaults to None.
        json_data (Optional[Dict[str, Any]]): JSON data to send in the request body. Defaults to None.
        params (Optional[Dict[str, str]]): Dictionary of URL parameters. Defaults to None.
        timeout (int): Request timeout in seconds. Defaults to 15.
        verify_ssl (bool): Whether to verify SSL certificates. Defaults to False.

    Returns:
        Optional[requests.Response]: The response object if the request was successful
                                     and returned a 2xx status code, otherwise None.
    """
    try:
        # Use requests.request for flexibility with different HTTP methods
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=timeout,
            verify=verify_ssl,  # Use the provided verify_ssl parameter
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        logger.info(
            f"Successfully executed {method.upper()} request to {url}. Status: {response.status_code}"
        )
        return response
    except requests.exceptions.HTTPError as http_err:
        logger.error(
            f"HTTP Error during {method.upper()} to {url}: {http_err}. "
            f"Response text: {http_err.response.text if http_err.response else 'N/A'}"
        )
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection Error during {method.upper()} to {url}: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout Error during {method.upper()} to {url}: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(
            f"An unexpected RequestException occurred during {method.upper()} to {url}: {req_err}"
        )
    except Exception as e:
        logger.critical(
            f"An unhandled error occurred during {method.upper()} to {url}: {e}",
            exc_info=True,
        )
    return None
