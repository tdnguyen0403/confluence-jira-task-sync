import unittest
from unittest.mock import patch, mock_open
import os
import logging
# Add this to disable logging during tests
logging.disable(logging.CRITICAL)

# Add the project root to the path for testing
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils import logging_config

class TestLoggingConfig(unittest.TestCase):
    """Tests the logging configuration utility."""

    @patch('src.utils.logging_config.logging.FileHandler')
    @patch('src.utils.logging_config.logging.StreamHandler')
    @patch('src.utils.logging_config.logging.basicConfig')
    @patch('src.utils.logging_config.os.makedirs')
    def test_setup_logging_creates_file_and_logs(self, mock_makedirs, mock_basic_config, mock_stream_handler, mock_file_handler):
        """Verify that logging setup creates directories and configures logging correctly."""
        
        log_dir = "test_logs"
        script_name = "test_script"
        
        with patch('src.utils.logging_config.datetime') as mock_datetime:
            # Mock the timestamp to get a predictable filename
            mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
            
            log_file_path = logging_config.setup_logging(log_dir, script_name)

            # 1. Verify directory creation
            mock_makedirs.assert_called_once_with(log_dir, exist_ok=True)
            
            # 2. Verify file path is correct
            expected_path = os.path.join(log_dir, f"{script_name}_20250101_120000.log")
            self.assertEqual(log_file_path, expected_path)

            # 3. Verify logging is configured
            self.assertTrue(mock_basic_config.called)
            
            # 4. Check that handlers were set up
            # Corrected assertion to be more robust
            found_handlers = False
            for call in mock_basic_config.call_args_list:
                _, kwargs = call
                if 'handlers' in kwargs:
                    found_handlers = True
                    self.assertEqual(len(kwargs['handlers']), 2)
            self.assertTrue(found_handlers, "logging.basicConfig was not called with 'handlers'")

    def tearDown(self):
        """Clean up logging handlers after each test."""
        # Get the root logger
        root_logger = logging.getLogger()
        
        # Close all handlers and clear them to release file locks
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
            
if __name__ == '__main__':
    unittest.main()