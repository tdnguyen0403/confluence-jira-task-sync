import logging
import os
import re
import sys  # Import sys for setup_logging_local
from datetime import datetime
from typing import Optional, Set  # Ensure Set is imported

from src.config import config  # Import the config settings
from src.utils.dir_helpers import (
    generate_timestamped_filename,
    get_log_path,
)  # Import helper functions


# Define a custom logger class to store the log file path
class CustomLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)
        self.log_file_path = None  # This will be set during setup


class SecretRedactingFilter(logging.Filter):
    def __init__(self, sensitive_patterns: Set[str]):
        super().__init__()
        self.patterns = [
            re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE)
            for s in sensitive_patterns
            if s
        ]
        self.patterns.extend(
            [
                re.compile(
                    r'(api_key|token|password|secret)=[\'"]?([^\s\'"]+)[\'"]?',
                    re.IGNORECASE,
                ),
                re.compile(r"authorization: bearer\s+([^\s]+)", re.IGNORECASE),
                re.compile(r"authorization: basic\s+([^\s]+)", re.IGNORECASE),
            ]
        )

    def filter(self, record):
        # Ensure the message is formatted before filtering, so args are consumed
        # This prevents TypeError if the original message had %s and we remove them.
        if record.args:
            record.msg = record.getMessage()  # Formats message using record.args
            record.args = ()  # Clear args after formatting

        if hasattr(record, "msg"):  # Use record.msg which is now the formatted message
            for pattern in self.patterns:
                record.msg = pattern.sub("[REDACTED]", record.msg)
            record.message = record.msg  # Update record.message for consistency

        return True


def setup_logging(
    log_file_prefix: str,
    endpoint_name: str,
    user: Optional[str] = None,
):
    """
    Sets up logging for the application, creating a dedicated log file for each run.
    The log level is determined by config.LOG_LEVEL.
    """
    # Map string level from config to logging constants
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    # Use the log_level from config.LOG_LEVEL
    effective_log_level = log_level_map.get(config.LOG_LEVEL.upper(), logging.INFO)

    # Set the logger class before getting the logger instance
    logging.setLoggerClass(CustomLogger)
    root_logger = logging.getLogger()  # Get the root logger instance

    # Prevent adding duplicate handlers if setup_logging is called multiple times
    # and clear existing handlers to ensure a clean setup for each request.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.handlers = []  # Clear existing handlers list

    root_logger.setLevel(effective_log_level)  # Set the root logger level

    # Use the helper functions from dir_helpers to get the log file path
    log_filename = generate_timestamped_filename(
        log_file_prefix, suffix=".log", user=user
    )
    log_file_path = get_log_path(
        endpoint_name, log_filename
    )  # <--- Using get_log_path from dir_helpers

    # Store the log file path in the custom logger instance
    if isinstance(root_logger, CustomLogger):
        root_logger.log_file_path = log_file_path

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(effective_log_level)  # Use effective_log_level here
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(effective_log_level)  # Use effective_log_level here
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Define sensitive strings to redact
    sensitive_data = {
        config.JIRA_API_TOKEN,
        config.CONFLUENCE_API_TOKEN,
        config.API_SECRET_KEY,
    }
    sensitive_data = {s for s in sensitive_data if s}  # Filter out None values

    redacting_filter = SecretRedactingFilter(sensitive_data)
    for handler in root_logger.handlers:  # Apply filter to root_logger's handlers
        handler.addFilter(redacting_filter)

    # Use root_logger for the final info message to ensure it's logged
    root_logger.info(
        f"Logging initialized at level {logging.getLevelName(effective_log_level)}. Output will be saved to '{log_file_path}'"
    )


def setup_logging_local(log_directory: str, script_name: str):
    """
    Set up logging to a file and the console.

    The logging level is determined by the LOG_LEVEL environment variable.
    If the variable is not set, it defaults to "INFO".

    Args:
        log_directory (str): The directory where log files will be stored.
        script_name (str): The name of the script, used for the log filename.

    Returns:
        str: The full path to the newly created log file.
    """
    # Read the log level directly from the environment variable.
    # It defaults to "INFO" if LOG_LEVEL is not found.
    log_level = os.getenv("LOG_LEVEL", "INFO")

    os.makedirs(log_directory, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(log_directory, f"{script_name}_{timestamp}.log")

    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file_path, "w", "utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.info(
        f"Logging initialized at level {log_level}. "
        f"Output will be saved to '{log_file_path}'"
    )
    return log_file_path
