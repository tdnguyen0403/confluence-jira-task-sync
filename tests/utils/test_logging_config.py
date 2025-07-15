"""
Tests for the logging configuration utility.
"""

import logging

# Assuming your project structure allows this import path
from src.utils.logging_config import setup_logging

# --- Pytest Test Function ---


def test_setup_logging_creates_file_and_logs(mocker):
    """
    Verify that setup_logging correctly configures file and stream handlers
    based on the provided config.
    """
    # Arrange: Use the mocker fixture to patch dependencies
    # This is the modern pytest equivalent of using @patch decorators
    mock_get_log_path = mocker.patch("src.utils.logging_config.get_log_path")
    mock_file_handler = mocker.patch("src.utils.logging_config.logging.FileHandler")
    mock_stream_handler = mocker.patch("src.utils.logging_config.logging.StreamHandler")
    mock_logger = mocker.patch("src.utils.logging_config.logging.getLogger")

    # Set up a return value for our patched function
    mock_log_filepath = "/mocked_log_directory/test_run.log"
    mock_get_log_path.return_value = mock_log_filepath

    # Act
    setup_logging(
        log_level=logging.INFO,
        log_file_prefix="test_run",
        endpoint_name="test_endpoint",
    )

    # Assert
    # Verify that our mocked functions and classes were called as expected
    mock_get_log_path.assert_called_once()
    mock_file_handler.assert_called_once_with(mock_log_filepath, encoding="utf-8")
    mock_stream_handler.assert_called_once()

    # Check that the root logger was retrieved and handlers were added
    assert mock_logger.return_value.addHandler.call_count == 2
