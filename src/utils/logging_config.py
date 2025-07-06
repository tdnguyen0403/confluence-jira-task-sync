# jira_confluence_automator_/src/logging_config.py

import logging
import os, sys
from datetime import datetime
from src.config import config # Ensure this import path is correct for your setup
from typing import Optional

# Define a custom logger class to store the log file path
class CustomLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)
        self.log_file_path = None # This will be set during setup

def setup_logging(log_level=logging.INFO, log_file_prefix="app_run", endpoint_name="api", user: Optional[str] = None):
    """
    Sets up logging configuration for api endpoints
    Args:
        log_level: The minimum logging level to capture (e.g., logging.INFO, logging.DEBUG).
        log_file_prefix: The prefix for the log file name (e.g., "sync_task_run", "api_run").
        endpoint_name: The name of the endpoint to determine the log subfolder (e.g., "sync", "api").
    """
    logging.setLoggerClass(CustomLogger)
    logger = logging.getLogger('') # Root logger

    # Ensure logger is not re-configured if already set up
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
        logger.handlers = [] # Clear existing handlers

    logger.setLevel(log_level)

    # Use the new config.py to get the log file path
    log_filename = config.generate_timestamped_filename(log_file_prefix, suffix=".log", user=user)
    log_file_path = config.get_log_path(endpoint_name, log_filename)

    # Store the log file path in the custom logger instance
    if isinstance(logger, CustomLogger):
        logger.log_file_path = log_file_path

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(f"Logging initialized at level {logging.getLevelName(log_level)}. Output will be saved to '{log_file_path}'")


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
    log_file_path = os.path.join(
        log_directory, f"{script_name}_{timestamp}.log"
    )

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