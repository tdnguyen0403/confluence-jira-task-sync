import os
import logging
from datetime import datetime
from typing import Optional
from src.config.config import (
    LOGS_ROOT_DIR,
    INPUT_ROOT_DIR,
    OUTPUT_ROOT_DIR,
)

logger = logging.getLogger(__name__)

ENDPOINT_SUBFOLDERS = {
    # Log subfolders (retaining 'logs_' prefix)
    "log_api": "logs_api",
    "log_generate": "logs_generate",
    "log_sync_task": "logs_sync_task",
    "log_undo_sync_task": "logs_undo_sync_task",
    "log_sync_project": "logs_sync_project",
    # Input subfolders (now with 'input_' prefix)
    "input_sync_task": "input_sync_task",
    "input_generate": "input_generate",
    "input_undo_sync_task": "input_undo_sync_task",
    "input_sync_project": "input_sync_project",
    # Output subfolders (now with 'output_' prefix)
    "output_sync_task": "output_sync_task",
    "output_generate": "output_generate",
    "output_undo_sync_task": "output_undo_sync_task",
    "output_sync_project": "output_sync_project",
}


def get_log_path(endpoint_name: str, filename: str) -> str:
    """
    Constructs the full path for a log file.
    Args:
        endpoint_name: The name of the endpoint (e.g., "api", "sync").
        filename: The base name of the log file (e.g., "api_run_20250706_112455.json").
    Returns:
        The full path to the log file.
    """
    # Look up the specific log subfolder name using "log_" prefix
    subfolder = ENDPOINT_SUBFOLDERS.get(f"log_{endpoint_name}", f"logs_{endpoint_name}")
    folder_path = os.path.join(LOGS_ROOT_DIR, subfolder)
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as e:
        logger.error(
            f"Failed to create log directory {folder_path}: {e}", exc_info=True
        )
    return os.path.join(folder_path, filename)


def get_input_path(endpoint_name: str, filename: str) -> str:
    """
    Constructs the full path for an input file.
    Args:
        endpoint_name: The name of the endpoint (e.g., "sync", "generate").
        filename: The base name of the input file (e.g., "sync_request_20250706_115503_tdnguyen.json").
    Returns:
        The full path to the input file.
    """
    # Look up the specific input subfolder name using "input_" prefix
    subfolder = ENDPOINT_SUBFOLDERS.get(
        f"input_{endpoint_name}", f"input_{endpoint_name}"
    )
    folder_path = os.path.join(INPUT_ROOT_DIR, subfolder)
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as e:
        logger.error(
            f"Failed to create input directory {folder_path}: {e}", exc_info=True
        )
    return os.path.join(folder_path, filename)


def get_output_path(endpoint_name: str, filename: str) -> str:
    """
    Constructs the full path for an output file.
    Args:
        endpoint_name: The name of the endpoint (e.g., "sync", "generate").
        filename: The base name of the output file (e.g., "sync_result_20250706_094824_tdnguyen.json").
    Returns:
        The full path to the output file.
    """
    # Look up the specific output subfolder name using "output_" prefix
    subfolder = ENDPOINT_SUBFOLDERS.get(
        f"output_{endpoint_name}", f"output_{endpoint_name}"
    )
    folder_path = os.path.join(OUTPUT_ROOT_DIR, subfolder)
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as e:
        logging.error(
            f"Failed to create output directory {folder_path}: {e}", exc_info=True
        )
    return os.path.join(folder_path, filename)


def generate_timestamped_filename(
    prefix: str, suffix: str = ".json", user: Optional[str] = None
) -> str:
    """
    Generates a timestamped filename.
    Args:
        prefix: The prefix for the filename (e.g., "api_run", "sync_task_run").
        suffix: The file extension (e.g., ".log", ".json").
        request_user: Optional user identifier to append to the filename.
    Returns:
        The generated filename.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if user:
        return f"{prefix}_{timestamp}_{user}{suffix}"
    return f"{prefix}_{timestamp}{suffix}"
