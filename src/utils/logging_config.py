"""
Provides a centralized function for configuring application-wide logging.

This module configures the root logger to output messages to both a
timestamped file and the console. The logging level is controlled by the
LOG_LEVEL environment variable.
"""

import logging
import os
import sys
from datetime import datetime

LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"


def setup_logging(log_directory: str, script_name: str):
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