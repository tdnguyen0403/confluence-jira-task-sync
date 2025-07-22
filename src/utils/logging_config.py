import logging
import os
import json
from datetime import datetime
from typing import Optional, Set  # Ensure Set is imported

from src.config import config  # Import the config settings
from src.utils.dir_helpers import (
    generate_timestamped_filename,
    get_log_path,
)  # Import helper functions

logging.getLogger("httpx").setLevel(os.getenv("HTTPX_LOG_LEVEL", "WARNING").upper())
logging.getLogger("asyncio").setLevel(os.getenv("ASYNCIO_LOG_LEVEL", "WARNING").upper())


# --- Structured JSON Formatter ---
class JsonFormatter(logging.Formatter):
    """
    A custom formatter to output log records in JSON format.
    It includes standard log record attributes and custom context
    passed via the 'extra' dictionary.
    """

    def format(self, record):
        # Base log record fields
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger_name": record.name,
            "process_id": record.process,
            "thread_id": record.thread,
            "file": f"{record.filename}:{record.lineno}",
            "function": record.funcName,
            "message": record.getMessage(),  # The actual log message
        }

        # Add any custom attributes passed via `extra={'my_custom_field': 'value'}`
        # We iterate over the record's dict to find non-standard attributes
        for key, value in record.__dict__.items():
            if (
                not key.startswith("_")
                and key not in log_record
                and not isinstance(value, logging.Logger)
            ):
                # Exclude standard attributes already handled or internal attributes
                log_record[key] = value

        # Add exception information
        if record.exc_info:
            # formatException returns string of traceback
            log_record["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            # formatStack returns string of stack info
            log_record["stack_trace"] = self.formatStack(record.stack_info)

        # Convert the dictionary to a JSON string
        return json.dumps(
            log_record, default=str
        )  # Use default=str for non-serializable objects


# Define a custom logger class to store the log file path
class CustomLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)
        self.log_file_path = None  # This will be set during setup


class SecretRedactingFilter(logging.Filter):
    def __init__(self, sensitive_patterns: Set[str]):
        super().__init__()
        self.sensitive_patterns = sensitive_patterns

    def filter(self, record):
        msg = record.getMessage()
        for pattern in self.sensitive_patterns:
            if pattern in msg:
                msg = msg.replace(pattern, "[REDACTED]")
        record.msg = msg
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

    try:
        # Use the helper functions from dir_helpers to get the log file path
        log_filename = generate_timestamped_filename(
            log_file_prefix, suffix=".json", user=user
        )
        log_file_path = get_log_path(
            endpoint_name, log_filename
        )  # <--- Using get_log_path from dir_helpers

        # File handler
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setLevel(effective_log_level)  # Use effective_log_level here
        file_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(file_handler)

        # Store the log file path in the custom logger instance
        if isinstance(root_logger, CustomLogger):
            root_logger.log_file_path = log_file_path
    except (OSError, PermissionError) as e:
        logging.error(f"Failed to create log file: {e}", exc_info=True)

    # Console handler
    try:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(effective_log_level)  # Use effective_log_level here
        console_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(console_handler)
    except Exception as e:
        logging.critical(f"Failed to set up console logging: {e}", exc_info=True)

    # Define sensitive strings to redact
    sensitive_patterns = set(
        filter(
            None,
            [
                getattr(config, "JIRA_API_TOKEN", None),
                getattr(config, "CONFLUENCE_API_TOKEN", None),
                getattr(config, "API_SECRET_KEY", None),
            ],
        )
    )
    if sensitive_patterns:
        root_logger.addFilter(SecretRedactingFilter(sensitive_patterns))

    # Use root_logger for the final info message to ensure it's logged
    root_logger.info(
        f"Logging initialized at level {logging.getLevelName(effective_log_level)}."
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
    try:
        os.makedirs(log_directory, exist_ok=True)
    except OSError as e:
        logging.error(
            f"Failed to create log directory {log_directory}: {e}", exc_info=True
        )
        # Fallback: use current directory
        log_directory = "."

    log_file_path = os.path.join(
        log_directory, f"{script_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file_path, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
    except Exception as e:
        logging.error(f"Failed to set up local logging: {e}", exc_info=True)
    return log_file_path
