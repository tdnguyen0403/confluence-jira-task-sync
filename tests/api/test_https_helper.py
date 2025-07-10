"""
Unit tests for the https_helper module.

This module tests the make_request function, which provides a generic
HTTPS request mechanism with built-in error handling.
"""

import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests  # Import requests to use its exception types for mocking

# Add the project root to the path to allow for imports from `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.api.https_helper import make_request

# Disable logging during tests for cleaner output
logging.disable(logging.CRITICAL)


class TestHttpsHelper(unittest.TestCase):
    """Tests the make_request function in https_helper."""

    @patch("src.api.https_helper.requests.request")
    def test_make_request_get_success(self, mock_requests_request):
        """Test successful GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Success"}
        mock_requests_request.return_value = mock_response

        url = "http://example.com/api/data"
        result = make_request("GET", url)

        mock_requests_request.assert_called_once_with(
            method="GET",
            url=url,
            headers=None,
            json=None,
            params=None,
            timeout=15,
            verify=False,
        )
        self.assertEqual(result, mock_response)
        self.assertEqual(result.json(), {"message": "Success"})
        result.raise_for_status.assert_called_once()  # Ensure status check was called

    @patch("src.api.https_helper.requests.request")
    def test_make_request_post_success(self, mock_requests_request):
        """Test successful POST request with data and headers."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 1, "status": "created"}
        mock_requests_request.return_value = mock_response

        url = "http://example.com/api/resource"
        headers = {"Content-Type": "application/json"}
        json_data = {"name": "Test Item"}
        result = make_request("POST", url, headers=headers, json_data=json_data)

        mock_requests_request.assert_called_once_with(
            method="POST",
            url=url,
            headers=headers,
            json=json_data,
            params=None,
            timeout=15,
            verify=False,
        )
        self.assertEqual(result, mock_response)
        self.assertEqual(result.json(), {"id": 1, "status": "created"})

    @patch("src.api.https_helper.requests.request")
    def test_make_request_http_error_404(self, mock_requests_request):
        """Test handling of HTTP 404 error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404 Client Error: Not Found for url: http://example.com/404",
            response=mock_response,
        )
        mock_requests_request.return_value = mock_response

        url = "http://example.com/404"
        result = make_request("GET", url)

        self.assertIsNone(result)
        mock_requests_request.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @patch("src.api.https_helper.requests.request")
    def test_make_request_connection_error(self, mock_requests_request):
        """Test handling of ConnectionError."""
        mock_requests_request.side_effect = requests.exceptions.ConnectionError(
            "Connection failed"
        )

        url = "http://example.com/unreachable"
        result = make_request("GET", url)

        self.assertIsNone(result)
        mock_requests_request.assert_called_once()

    @patch("src.api.https_helper.requests.request")
    def test_make_request_timeout_error(self, mock_requests_request):
        """Test handling of Timeout error."""
        mock_requests_request.side_effect = requests.exceptions.Timeout(
            "Request timed out"
        )

        url = "http://example.com/slow"
        result = make_request("GET", url)

        self.assertIsNone(result)
        mock_requests_request.assert_called_once()

    @patch("src.api.https_helper.requests.request")
    def test_make_request_generic_request_exception(self, mock_requests_request):
        """Test handling of a generic RequestException."""
        mock_requests_request.side_effect = requests.exceptions.RequestException(
            "Generic error"
        )

        url = "http://example.com/error"
        result = make_request("GET", url)

        self.assertIsNone(result)
        mock_requests_request.assert_called_once()

    @patch("src.api.https_helper.requests.request")
    def test_make_request_unhandled_exception(self, mock_requests_request):
        """Test handling of an unexpected unhandled exception."""
        mock_requests_request.side_effect = ValueError("Unexpected error")

        url = "http://example.com/unhandled"
        result = make_request("GET", url)

        self.assertIsNone(result)
        mock_requests_request.assert_called_once()

    @patch("src.api.https_helper.requests.request")
    def test_make_request_with_custom_timeout_and_verify_ssl(
        self, mock_requests_request
    ):
        """Test request with custom timeout and SSL verification."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_request.return_value = mock_response

        url = "https://secure.example.com"
        timeout = 5
        verify_ssl = True
        result = make_request("GET", url, timeout=timeout, verify_ssl=verify_ssl)

        mock_requests_request.assert_called_once_with(
            method="GET",
            url=url,
            headers=None,
            json=None,
            params=None,
            timeout=timeout,
            verify=verify_ssl,
        )
        self.assertEqual(result, mock_response)


if __name__ == "__main__":
    unittest.main()
