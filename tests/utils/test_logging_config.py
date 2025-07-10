import unittest
from unittest.mock import patch
import os

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestLoggingConfig(unittest.TestCase):
    """Tests the logging configuration utility."""

    @patch("src.utils.logging_config.logging.FileHandler")
    @patch("src.utils.logging_config.logging.StreamHandler")
    @patch("src.utils.logging_config.logging.basicConfig")
    @patch("src.utils.logging_config.config.get_log_path")
    def test_setup_logging_creates_file_and_logs(
        self,
        mock_get_log_path,
        mock_basic_config,
        mock_stream_handler,
        mock_file_handler,
    ):
        mock_log_filepath = "/mocked_log_directory/test_run_20250101_120000.log"
        mock_get_log_path.return_value = mock_log_filepath


if __name__ == "__main__":
    unittest.main()
