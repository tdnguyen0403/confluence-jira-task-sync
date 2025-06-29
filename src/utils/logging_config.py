"""
Provides a centralized function for configuring application-wide logging.

This module contains the `setup_logging` function, which initializes the
root logger to output messages to both a timestamped file and the console.
This ensures that all events are captured for debugging and auditing
purposes, providing a consistent logging format across the entire application.
"""

import logging
import os
import sys
from datetime import datetime


def setup_logging(log_directory: str, script_name: str) -> str:
    """
    Sets up logging to both a file and the console.

    This function configures the root logger with a standard format and adds
    two handlers:
    1.  A `FileHandler` to write all log messages to a uniquely named log file
        in the specified directory. The file is encoded in UTF-8.
    2.  A `StreamHandler` to print log messages to the standard output
        (the console).

    It also ensures that any previously configured handlers are cleared to
    prevent duplicate log output.

    Args:
        log_directory (str): The directory where the log file will be saved.
        script_name (str): The name of the script, used to create a unique
                           and descriptive log filename.

    Returns:
        str: The full path to the newly created log file.
    """
    # Ensure the target directory for logs exists.
    os.makedirs(log_directory, exist_ok=True)

    # Create a unique, timestamped filename for the log file.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(log_directory, f"{script_name}_{timestamp}.log")

    # Get the root logger instance.
    root_logger = logging.getLogger()

    # Clear any existing handlers to prevent duplicate logging, which can
    # occur if this function is called multiple times.
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Configure the basic logging settings, including the level, format,
    # and handlers.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, "w", "utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.info(
        f"Logging initialized. Output will be saved to '{log_file_path}'"
    )
    return log_file_path
