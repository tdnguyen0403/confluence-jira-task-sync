import logging
import os
import sys
from datetime import datetime

def setup_logging(log_directory: str, script_name: str) -> str:
    """
    Sets up logging to both a file and the console.

    Args:
        log_directory (str): The directory where the log file will be saved.
        script_name (str): The name of the script, used in the log filename.

    Returns:
        str: The full path to the log file.
    """
    os.makedirs(log_directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(log_directory, f"{script_name}_{timestamp}.log")

    root_logger = logging.getLogger()
    # Clear any existing handlers to prevent duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, 'w', 'utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info(f"Logging initialized. Output will be saved to '{log_file_path}'")
    return log_file_path