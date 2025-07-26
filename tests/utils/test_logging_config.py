"""Test suite for logging configuration utilities.
This module tests the logging configuration, including custom filters and formatters."""

import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.config import config
from src.utils.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    SecretRedactingFilter,
    endpoint_var,
    request_id_var,
    setup_logging,
)


@pytest.fixture
def mock_log_record():
    """Creates a mock log record for testing."""

    def _mock_log_record(msg, level=logging.INFO, exc_info=None):
        record = logging.LogRecord(
            "test_logger", level, "/path/to/file.py", 123, msg, (), exc_info
        )
        record.funcName = "test_function"
        return record

    return _mock_log_record


def test_secret_redacting_filter(mock_log_record):
    """Verify the SecretRedactingFilter redacts sensitive strings."""
    sensitive_patterns = {"secret123", "api_key_456"}
    filtr = SecretRedactingFilter(sensitive_patterns)
    log_record = mock_log_record("A message with secret123.")

    filtr.filter(log_record)

    assert "secret123" not in log_record.getMessage()
    assert "[REDACTED]" in log_record.getMessage()


def test_json_formatter_structure_and_order(mock_log_record):
    """Verify the JsonFormatter creates a well-structured JSON log."""
    formatter = JsonFormatter()
    log_record = mock_log_record("This is a test message.")

    # Simulate filter adding attributes
    log_record.request_id = "req-123"
    log_record.endpoint = "/test"

    formatted_log = formatter.format(log_record)
    log_dict = json.loads(formatted_log)

    expected_keys = {
        "timestamp",
        "level",
        "request_id",
        "endpoint",
        "message",
        "source",
        "function",
    }
    # Corrected: Assert the set of keys to be independent of order
    assert set(log_dict.keys()) == expected_keys
    assert log_dict["level"] == "INFO"
    assert log_dict["message"] == "This is a test message."
    assert log_dict["source"] == "file.py:123"
    assert log_dict["function"] == "test_function"


def test_json_formatter_with_exception(mock_log_record):
    """Verify the JsonFormatter includes exception info when present."""
    formatter = JsonFormatter()
    try:
        raise ValueError("A test error")
    except ValueError:
        # Corrected: Pass the actual exception info tuple to the record
        log_record = mock_log_record(
            "An error occurred.", level=logging.ERROR, exc_info=sys.exc_info()
        )

    formatted_log = formatter.format(log_record)
    log_dict = json.loads(formatted_log)

    assert "exception" in log_dict
    assert "Traceback" in log_dict["exception"]
    assert "ValueError: A test error" in log_dict["exception"]


def test_request_id_filter_injects_context_vars(mock_log_record):
    """Verify the RequestIdFilter injects context variables into the log record."""
    filtr = RequestIdFilter()
    log_record = mock_log_record("A message.")

    # Set context variables
    request_id_var.set("req-abc")
    endpoint_var.set("/my-endpoint")

    filtr.filter(log_record)

    assert hasattr(log_record, "request_id")
    assert log_record.request_id == "req-abc"
    assert hasattr(log_record, "endpoint")
    assert log_record.endpoint == "/my-endpoint"


@patch("src.utils.logging_config.logging.handlers.RotatingFileHandler")
@patch("src.utils.logging_config.os.makedirs")
@patch("src.utils.logging_config.logging.getLogger")
def test_setup_logging_configures_root_logger(
    mock_get_logger, mock_makedirs, mock_rotating_handler
):
    """Verify setup_logging configures the root logger with correct handlers and formatters."""
    mock_root_logger = MagicMock()
    mock_get_logger.return_value = mock_root_logger

    setup_logging()

    # Verify directory creation
    mock_makedirs.assert_called_once_with(config.LOG_DIR, exist_ok=True)

    # Verify file handler setup
    expected_log_path = os.path.join(config.LOG_DIR, "application_log.json")
    mock_rotating_handler.assert_called_once_with(
        expected_log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )

    # Verify that handlers were added to the root logger
    assert mock_root_logger.addHandler.call_count == 3

    # Verify a filter was added to the root logger (for secrets)
    assert mock_root_logger.addFilter.call_count > 0
