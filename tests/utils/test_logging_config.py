"""
Tests for the logging configuration utility.
"""

import logging
import pytest

# Assuming your project structure allows this import path
from src.utils.logging_config import (
    setup_logging,
    setup_logging_local,
    SecretRedactingFilter,
    CustomLogger,
)


@pytest.fixture
def mock_log_record():
    """Creates a mock log record for testing filters."""

    def _mock_log_record(msg, args=()):
        return logging.LogRecord("test", logging.INFO, "/path", 1, msg, args, None)

    return _mock_log_record


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


def test_secret_redacting_filter_redacts_sensitive_data(mock_log_record):
    """
    Verify that the SecretRedactingFilter correctly redacts sensitive data from log messages.
    """
    # Arrange
    sensitive_patterns = {"secret123", "api_key_456"}
    filter = SecretRedactingFilter(sensitive_patterns)
    log_record = mock_log_record(
        "This is a test message with secret123 and api_key_456."
    )

    # Act
    filter.filter(log_record)

    # Assert
    filtered_msg = log_record.getMessage()
    assert "[REDACTED]" in filtered_msg
    assert "secret123" not in filtered_msg
    assert "api_key_456" not in filtered_msg


def test_custom_logger_stores_log_file_path():
    """
    Verify that the CustomLogger correctly stores the log file path.
    """
    # Arrange
    logger = CustomLogger("test_logger")

    # Act
    logger.log_file_path = "/mocked_log_directory/test.log"

    # Assert
    assert logger.log_file_path == "/mocked_log_directory/test.log"


def test_setup_logging_local_creates_log_file(mocker):
    """
    Verify that setup_logging_local creates a log file and configures logging.
    """
    # Arrange
    mock_makedirs = mocker.patch("os.makedirs")
    mock_basic_config = mocker.patch("logging.basicConfig")

    log_directory = "/mocked_log_directory"
    script_name = "test_script"

    # Act
    log_file_path = setup_logging_local(log_directory, script_name)

    # Assert
    mock_makedirs.assert_called_once_with(log_directory, exist_ok=True)
    assert log_file_path.startswith(log_directory)
    assert script_name in log_file_path
    assert mock_basic_config.call_count >= 1


def test_setup_logging_handles_empty_sensitive_data(mocker):
    """
    Verify that setup_logging handles cases where sensitive data is empty.
    """
    # Arrange
    mock_get_log_path = mocker.patch("src.utils.logging_config.get_log_path")
    mock_file_handler = mocker.patch("src.utils.logging_config.logging.FileHandler")
    mock_stream_handler = mocker.patch("src.utils.logging_config.logging.StreamHandler")
    mock_logger = mocker.patch("src.utils.logging_config.logging.getLogger")
    mock_config = mocker.patch("src.utils.logging_config.config")

    mock_config.JIRA_API_TOKEN = None
    mock_config.CONFLUENCE_API_TOKEN = None
    mock_config.API_SECRET_KEY = None

    mock_log_filepath = "/mocked_log_directory/test_run.log"
    mock_get_log_path.return_value = mock_log_filepath

    # Act
    setup_logging(
        log_file_prefix="test_run",
        endpoint_name="test_endpoint",
    )

    # Assert
    mock_get_log_path.assert_called_once()
    mock_file_handler.assert_called_once_with(mock_log_filepath, encoding="utf-8")
    mock_stream_handler.assert_called_once()
    assert mock_logger.return_value.addHandler.call_count == 2


def test_setup_logging_local_logs_to_console_and_file(mocker):
    """
    Verify that setup_logging_local logs messages to both console and file.
    """
    # Arrange
    mock_file_handler = mocker.patch("logging.FileHandler")
    mock_stream_handler = mocker.patch("logging.StreamHandler")
    mock_basic_config = mocker.patch("logging.basicConfig")

    log_directory = "/mocked_log_directory"
    script_name = "test_script"

    # Act
    log_file_path = setup_logging_local(log_directory, script_name)

    # Assert
    mock_file_handler.assert_called_once()
    mock_stream_handler.assert_called_once()
    assert mock_basic_config.call_count >= 1
    assert log_file_path.startswith(log_directory)
    assert script_name in log_file_path
