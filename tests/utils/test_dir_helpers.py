import pytest
from unittest.mock import patch
import os
from src.utils import dir_helpers
from src.utils.dir_helpers import get_log_path, get_input_path, get_output_path


@pytest.fixture(autouse=True)
def mock_filesystem(monkeypatch):
    # This ensures that dir_helpers uses the mocked values
    monkeypatch.setattr(dir_helpers, "LOGS_ROOT_DIR", "/mock_app/logs")
    monkeypatch.setattr(dir_helpers, "INPUT_ROOT_DIR", "/mock_app/input")
    monkeypatch.setattr(dir_helpers, "OUTPUT_ROOT_DIR", "/mock_app/output")
    with patch("src.utils.dir_helpers.os.makedirs") as mock_makedirs:
        yield mock_makedirs


def test_get_log_path_sync_task(mock_filesystem):
    filename = "sync_log.log"
    endpoint = "sync_task"
    expected_path = os.path.join("/mock_app/logs", "logs_sync_task", filename)
    result_path = get_log_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/logs", "logs_sync_task"), exist_ok=True
    )


def test_get_log_path_undo_sync_task(mock_filesystem):
    filename = "undo_sync_task.log"
    endpoint = "undo_sync_task"
    expected_path = os.path.join("/mock_app/logs", "logs_undo_sync_task", filename)
    result_path = get_log_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/logs", "logs_undo_sync_task"), exist_ok=True
    )


def test_get_log_path_sync_project(mock_filesystem):
    filename = "sync_project.log"
    endpoint = "sync_project"
    expected_path = os.path.join("/mock_app/logs", "logs_sync_project", filename)
    result_path = get_log_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/logs", "logs_sync_project"), exist_ok=True
    )


def test_get_log_path_api_endpoint(mock_filesystem):
    filename = "api_access.log"
    endpoint = "api"
    expected_path = os.path.join("/mock_app/logs", "logs_api", filename)
    result_path = get_log_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/logs", "logs_api"), exist_ok=True
    )


def test_get_input_path_sync_task(mock_filesystem):
    filename = "sync_request.json"
    endpoint = "sync_task"
    expected_path = os.path.join("/mock_app/input", "input_sync_task", filename)
    result_path = get_input_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/input", "input_sync_task"), exist_ok=True
    )


def test_get_input_path_undo_sync_task(mock_filesystem):
    filename = "undo_request.json"
    endpoint = "undo_sync_task"
    expected_path = os.path.join("/mock_app/input", "input_undo_sync_task", filename)
    result_path = get_input_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/input", "input_undo_sync_task"), exist_ok=True
    )


def test_get_input_path_sync_project_task(mock_filesystem):
    filename = "sync_project.json"
    endpoint = "sync_project"
    expected_path = os.path.join("/mock_app/input", "input_sync_project", filename)
    result_path = get_input_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/input", "input_sync_project"), exist_ok=True
    )


def test_get_output_path_sync_task(mock_filesystem):
    filename = "sync_task.json"
    endpoint = "sync_task"
    expected_path = os.path.join("/mock_app/output", "output_sync_task", filename)
    result_path = get_output_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/output", "output_sync_task"), exist_ok=True
    )


def test_get_output_path_sync_project(mock_filesystem):
    filename = "project_result.json"
    endpoint = "sync_project"
    expected_path = os.path.join("/mock_app/output", "output_sync_project", filename)
    result_path = get_output_path(endpoint, filename)
    assert result_path == expected_path
    mock_filesystem.assert_called_once_with(
        os.path.join("/mock_app/output", "output_sync_project"), exist_ok=True
    )
