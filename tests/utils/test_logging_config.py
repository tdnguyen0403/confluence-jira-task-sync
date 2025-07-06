import unittest
from unittest.mock import patch, mock_open
import os
import logging
from datetime import datetime

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils import logging_config
from src.config import config 

class TestLoggingConfig(unittest.TestCase):
    """Tests the logging configuration utility."""

    @patch('src.utils.logging_config.logging.FileHandler')
    @patch('src.utils.logging_config.logging.StreamHandler')
    @patch('src.utils.logging_config.logging.basicConfig')
    @patch('src.utils.logging_config.config.get_log_path') 
    def test_setup_logging_creates_file_and_logs(self, mock_get_log_path, mock_basic_config, mock_stream_handler, mock_file_handler):
        
        log_level = logging.INFO
        log_file_prefix = "test_run"
        endpoint_name = "test_endpoint"

        mock_log_filepath = "/mocked_log_directory/test_run_20250101_120000.log"
        mock_get_log_path.return_value = mock_log_filepath
        
        log_file_path = logging_config.setup_logging(
            log_level=log_level,
            log_file_prefix=log_file_prefix,
            endpoint_name=endpoint_name
        )

if __name__ == '__main__':
    unittest.main()