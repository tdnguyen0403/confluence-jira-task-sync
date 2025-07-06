import unittest
import requests
from unittest.mock import patch, MagicMock
from src.utils.http_client import make_request
from src.exceptions import JiraConfluenceError
import time # Import time for patching

class TestHttpClient(unittest.TestCase):

    @patch('requests.request')
    def test_successful_request(self, mock_request):
        """Test that a successful request returns the response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        response = make_request('GET', 'http://test.com', headers={})
        self.assertEqual(response, mock_response)
        mock_request.assert_called_once_with(
            'GET', 'http://test.com', headers={}, json=None, params=None, timeout=30
        )

    @patch('requests.request')
    def test_request_with_json_and_params(self, mock_request):
        """Test request with JSON data and parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        json_data = {"key": "value"}
        params = {"param": "value"}
        response = make_request('POST', 'http://test.com/api', headers={}, json_data=json_data, params=params)
        self.assertEqual(response, mock_response)
        mock_request.assert_called_once_with(
            'POST', 'http://test.com/api', headers={}, json=json_data, params=params, timeout=30
        )

    @patch('requests.request')
    @patch('time.sleep', return_value=None) # Patch time.sleep directly
    def test_retry_on_timeout(self, mock_sleep, mock_request):
        """Test that the request retries on Timeout and eventually succeeds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        # First two calls raise Timeout, third succeeds
        mock_request.side_effect = [
            requests.exceptions.Timeout("Timeout error"),
            requests.exceptions.Timeout("Timeout error"),
            mock_response
        ]

        response = make_request('GET', 'http://test.com', headers={}, retries=3)
        self.assertEqual(response, mock_response)
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2) # Sleep called after first two failures

    @patch('requests.request')
    @patch('time.sleep', return_value=None) # Patch time.sleep directly
    def test_retry_on_request_exception(self, mock_sleep, mock_request):
        """Test that the request retries on a generic RequestException and eventually succeeds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        mock_request.side_effect = [
            requests.exceptions.RequestException("Connection error"),
            mock_response
        ]

        response = make_request('GET', 'http://test.com', headers={}, retries=2)
        self.assertEqual(response, mock_response)
        self.assertEqual(mock_request.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch('requests.request')
    def test_http_error_404_no_retry(self, mock_request):
        """Test that a 404 HTTPError raises JiraConfluenceError immediately (no retry)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_request.return_value = mock_response
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)

        with self.assertRaisesRegex(JiraConfluenceError, "Client error during request to http://test.com: Status 404 - Not Found"):
            make_request('GET', 'http://test.com', headers={}, retries=3)
        mock_request.assert_called_once() # Should not retry for 4xx errors (except 408, 429)

    @patch('requests.request')
    @patch('time.sleep', return_value=None) # Patch time.sleep directly
    def test_http_error_500_with_retry(self, mock_sleep, mock_request):
        """Test that a 500 HTTPError retries and eventually fails."""
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"
        mock_request.return_value = mock_response_500
        mock_response_500.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response_500)

        with self.assertRaisesRegex(JiraConfluenceError, "Failed to make request to http://test.com after 3 attempts."):
            make_request('GET', 'http://test.com', headers={}, retries=3)
        self.assertEqual(mock_request.call_count, 3) # Retried 3 times
        self.assertEqual(mock_sleep.call_count, 2) # Slept twice

    @patch('requests.request')
    @patch('time.sleep', return_value=None) # Patch time.sleep directly
    def test_all_retries_fail(self, mock_sleep, mock_request):
        """Test that JiraConfluenceError is raised if all retries fail."""
        mock_request.side_effect = requests.exceptions.Timeout("Timeout error")

        with self.assertRaisesRegex(JiraConfluenceError, "Failed to make request to http://test.com after 3 attempts."):
            make_request('GET', 'http://test.com', headers={}, retries=3)
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('requests.request')
    def test_unexpected_exception(self, mock_request):
        """Test that an unexpected exception is caught and re-raised as JiraConfluenceError."""
        mock_request.side_effect = ValueError("Unexpected error")

        with self.assertRaisesRegex(JiraConfluenceError, "Unexpected error during request to http://test.com: Unexpected error"):
            make_request('GET', 'http://test.com', headers={})
        mock_request.assert_called_once() # Should not retry for unexpected errors

    @patch('requests.request')
    def test_timeout_parameter(self, mock_request):
        """Test that the timeout parameter is passed correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        make_request('GET', 'http://test.com', headers={}, timeout=5)
        mock_request.assert_called_once_with(
            'GET', 'http://test.com', headers={}, json=None, params=None, timeout=5
        )

if __name__ == '__main__':
    unittest.main()

