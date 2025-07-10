import pytest
from unittest.mock import MagicMock
from src.services.orchestration.undo_sync_task_orchestrator import (
    UndoSyncTaskOrchestrator,
)
from src.exceptions import InvalidInputError, MissingRequiredDataError
from src.config import config
import logging

# Configure logger for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_confluence_service():
    mock = MagicMock()
    mock.get_page_by_id.side_effect = [
        {
            "id": "page1",
            "body": {"storage": {"value": "old content"}},
        },  # For historical_page
        {
            "id": "page1",
            "title": "Test Page",
            "version": {"number": 2},
        },  # For current_page
    ]
    mock.update_page_content.return_value = True
    return mock


@pytest.fixture
def mock_jira_service():
    mock = MagicMock()
    mock.transition_issue.return_value = True
    return mock


@pytest.fixture
def undo_orchestrator(mock_confluence_service, mock_jira_service):
    return UndoSyncTaskOrchestrator(
        confluence_service=mock_confluence_service, jira_service=mock_jira_service
    )


def test_undo_orchestrator_run_success(
    undo_orchestrator, mock_jira_service, mock_confluence_service
):
    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-100",
            "confluence_page_id": "1",
            "original_page_version": 1,
        },
        {
            "Status": "Success - Completed Task Created",
            "New Jira Task Key": "JIRA-101",
            "confluence_page_id": "2",
            "original_page_version": 2,
        },
        # A failed one should not trigger undo for Jira/Confluence
        {
            "Status": "Failed - Jira task creation",
            "New Jira Task Key": None,
            "confluence_page_id": "3",
            "original_page_version": 3,
        },
    ]

    undo_orchestrator.run(results_data)

    mock_jira_service.transition_issue.assert_any_call(
        "JIRA-100", config.JIRA_TARGET_STATUSES["undo"]
    )
    mock_jira_service.transition_issue.assert_any_call(
        "JIRA-101", config.JIRA_TARGET_STATUSES["undo"]
    )
    assert mock_jira_service.transition_issue.call_count == 2

    mock_confluence_service.get_page_by_id.assert_any_call(
        "1", version=1, expand="body.storage"
    )
    mock_confluence_service.get_page_by_id.assert_any_call(
        "2", version=2, expand="body.storage"
    )
    mock_confluence_service.update_page_content.assert_called()


def test_undo_orchestrator_run_no_input(undo_orchestrator):
    with pytest.raises(InvalidInputError, match="No results JSON data provided"):
        undo_orchestrator.run([])


def test_undo_orchestrator_run_empty_data(undo_orchestrator):
    with pytest.raises(
        InvalidInputError, match="Provided JSON data is empty or could not be processed"
    ):
        undo_orchestrator.run([{}])


def test_undo_orchestrator_missing_required_columns(undo_orchestrator):
    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-100",
            # Missing confluence_page_id and original_page_version
        }
    ]
    with pytest.raises(
        MissingRequiredDataError, match="Results data is missing required columns"
    ):
        undo_orchestrator.run(results_data)


def test_undo_orchestrator_transition_jira_tasks_failure(
    undo_orchestrator, mock_jira_service
):
    mock_jira_service.transition_issue.side_effect = Exception("Jira API Error")

    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-100",
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]

    # The run method should not raise for individual transition failures, but log them
    undo_orchestrator.run(results_data)
    mock_jira_service.transition_issue.assert_called_once()
    # Check if a log error was generated, rather than an exception being raised


def test_undo_orchestrator_rollback_confluence_failure(
    undo_orchestrator, mock_confluence_service
):
    mock_confluence_service.get_page_by_id.side_effect = [
        None,  # simulate failure to get historical page
        {
            "id": "page1",
            "title": "Test Page",
            "version": {"number": 2},
        },  # For current_page
    ]

    results_data = [
        {
            "Status": "Success",
            "New Jira Task Key": "JIRA-100",
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]

    undo_orchestrator.run(results_data)
    mock_confluence_service.get_page_by_id.call_count == 2  # Called for historical and current
    mock_confluence_service.update_page_content.assert_not_called()


def test_undo_orchestrator_no_jira_keys_or_pages(
    undo_orchestrator, mock_jira_service, mock_confluence_service
):
    # Data where no sync actions were successful (e.g., all skipped or failed)
    results_data = [
        {
            "Status": "Skipped - No Work Package found",
            "New Jira Task Key": None,
            "confluence_page_id": "1",
            "original_page_version": 1,
        }
    ]
    undo_orchestrator.run(results_data)

    mock_jira_service.transition_issue.assert_not_called()
    mock_confluence_service.update_page_content.assert_not_called()
    mock_confluence_service.get_page_by_id.assert_not_called()
