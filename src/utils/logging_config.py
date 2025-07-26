import json
import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Optional, Set

from src.config import config

# Context variables to hold request-specific information
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
endpoint_var: ContextVar[Optional[str]] = ContextVar("endpoint", default=None)

# Mute noisy loggers
logging.getLogger("httpx").setLevel(os.getenv("HTTPX_LOG_LEVEL", "WARNING").upper())
logging.getLogger("asyncio").setLevel(os.getenv("ASYNCIO_LOG_LEVEL", "WARNING").upper())


class RequestIdFilter(logging.Filter):
    """
    A logging filter that injects the request_id and endpoint from context variables
    into the log record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.endpoint = endpoint_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """
    A custom formatter to output log records in JSON format, with variable-length
    fields at the end for better readability.
    """

    def format(self, record: logging.LogRecord) -> str:
        # The order of keys is intentional for better human readability
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", "N/A"),
            "endpoint": getattr(record, "endpoint", "N/A"),
            "message": record.getMessage(),  # Variable length message is last
            "source": f"{record.filename}:{record.lineno}",  # Combined file and line
            "function": record.funcName,
        }

        if record.exc_info:
            # Exception info is also variable length and comes after the main message
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, default=str)


class SecretRedactingFilter(logging.Filter):
    def __init__(self, sensitive_patterns: Set[str]):
        super().__init__()
        self.sensitive_patterns = sensitive_patterns

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.sensitive_patterns:
            if pattern and pattern in msg:
                msg = msg.replace(pattern, "[REDACTED]")
        record.msg = msg
        return True


def setup_logging() -> None:
    """
    Sets up centralized, rotating, JSON-formatted logging for the application.
    This function should be called once at application startup.
    """
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    effective_log_level = log_level_map.get(config.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(effective_log_level)

    # Create logs directory if it doesn't exist
    os.makedirs(config.LOG_DIR, exist_ok=True)
    log_file_path = os.path.join(config.LOG_DIR, "application_log.json")

    # Use RotatingFileHandler
    # 10MB per file, keeping 5 backup files
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )

    formatter = JsonFormatter()
    file_handler.setFormatter(formatter)

    # Console handler for INFO/WARNING to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(RequestIdFilter())
    stdout_handler.addFilter(
        lambda record: record.levelno <= logging.WARNING
    )  # Filter for INFO, DEBUG, WARNING

    # Console handler for ERROR/CRITICAL to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)
    stderr_handler.addFilter(RequestIdFilter())

    # Add the filter to both handlers
    request_filter = RequestIdFilter()
    file_handler.addFilter(request_filter)
    stdout_handler.addFilter(request_filter)
    stderr_handler.addFilter(request_filter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

    # Define and add secret redacting filter
    sensitive_patterns = set(
        filter(
            None,
            [
                config.JIRA_API_TOKEN,
                config.CONFLUENCE_API_TOKEN,
                config.API_SECRET_KEY,
            ],
        )
    )
    if sensitive_patterns:
        root_logger.addFilter(SecretRedactingFilter(sensitive_patterns))

    root_logger.info(
        f"Logging initialized at level {logging.getLevelName(effective_log_level)}. "
        f"Logs will be written to {log_file_path}"
    )
