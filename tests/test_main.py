import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, call # Import 'call' for specific call assertion
import os

# Import the main FastAPI app
from main import app
# Import the container and get_api_key from src/dependencies.py
from src.dependencies import get_api_key, container

# Import the Pydantic models from src/models/data_models.py
from src.models.data_models import AutomationResult, ConfluenceTask, UndoRequestItem, SyncRequest
from src.config import config # Import config for direct patching if needed elsewhere, though not for API_SECRET_KEY here
from src.exceptions import SyncError, MissingRequiredDataError, InvalidInputError, UndoError

# Mock API Key for testing
TEST_API_KEY = "test_secret_key"

# Removed autouse=True. Now, this fixture must be explicitly applied.
@pytest.fixture
def api_key_override():
    """
    Fixture to override the get_api_key dependency for tests that use it.
    Also temporarily sets config.API_SECRET_KEY for robustness.
    """
    def override_get_api_key_test():
        return TEST_API_KEY

    app.dependency_overrides[get_api_key] = override_get_api_key_test
    
    # Temporarily set config.API_SECRET_KEY to ensure get_api_key (if it accesses config) passes
    original_api_secret_key = config.API_SECRET_KEY
    config.API_SECRET_KEY = TEST_API_KEY
    yield
    # Clean up after tests
    app.dependency_overrides.clear()
    config.API_SECRET_KEY = original_api_secret_key


@pytest.fixture
def client():
    """Fixture to create a TestClient for the FastAPI app."""
    return TestClient(app)

@pytest.fixture
def mock_sync_orchestrator():
    """Fixture to create a mock SyncTaskOrchestrator."""
    mock = MagicMock()
    mock.results = []
    return mock

@pytest.fixture
def mock_undo_orchestrator():
    """Fixture to create a mock UndoSyncTaskOrchestrator."""
    return MagicMock()

class TestFastAPIDecoupledEndpoints:

    # Explicitly apply api_key_override to tests that need auth to pass
    @pytest.mark.usefixtures("api_key_override")
    @patch('main.os.makedirs')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_sync_confluence_tasks_success(self, mock_json_dump, mock_open, mock_os_makedirs,
                                           client, mock_sync_orchestrator):
        """
        Tests successful /sync endpoint behavior with a mocked orchestrator.
        """
        app.dependency_overrides[container.sync_orchestrator] = lambda: mock_sync_orchestrator

        mock_sync_orchestrator.run.return_value = None
        mock_sync_orchestrator.results = [
            AutomationResult(
                task_data=ConfluenceTask(
                    confluence_page_id="123",
                    confluence_page_title="Test Page",
                    confluence_page_url="http://test.confluence.com/page/123",
                    confluence_task_id="task1",
                    task_summary="Test Task 1",
                    status="incomplete",
                    assignee_name=None,
                    due_date="2025-01-01",
                    original_page_version=1,
                    original_page_version_by="user",
                    original_page_version_when="now"
                ),
                status="Success",
                new_jira_key="JIRA-1",
                linked_work_package="WP-1",
                request_user="test_user"
            )
        ]

        request_payload_model = SyncRequest(
            confluence_page_urls=["http://test.confluence.com/page/123"],
            request_user="test_user"
        )
        request_payload_dict = request_payload_model.model_dump()

        headers = {"X-API-Key": TEST_API_KEY}
        
        response = client.post("/sync", json=request_payload_dict, headers=headers)

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["New Jira Task Key"] == "JIRA-1"
        
        mock_sync_orchestrator.run.assert_called_once_with(request_payload_dict)
        
        mock_os_makedirs.assert_any_call('input', exist_ok=True)
        
        called_for_input_file = False
        for call_args in mock_open.call_args_list:
            if call_args.args and isinstance(call_args.args[0], str) and \
               call_args.args[0].startswith(os.path.join(config.INPUT_DIRECTORY, "sync_request_")):
                called_for_input_file = True
                assert 'w' in call_args.args
                assert 'utf-8' in call_args.kwargs.values()
                break
        assert called_for_input_file, "Expected open to be called for input file saving"

        mock_json_dump.assert_called_once()

        app.dependency_overrides.clear()

    # Explicitly apply api_key_override
    @pytest.mark.usefixtures("api_key_override")
    @patch('main.os.makedirs')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_sync_confluence_tasks_no_results(self, mock_json_dump, mock_open, mock_os_makedirs,
                                               client, mock_sync_orchestrator):
        """
        Tests /sync endpoint when no tasks are processed (empty results).
        """
        app.dependency_overrides[container.sync_orchestrator] = lambda: mock_sync_orchestrator
        mock_sync_orchestrator.run.return_value = None
        mock_sync_orchestrator.results = []

        request_payload_model = SyncRequest(
            confluence_page_urls=["http://test.confluence.com/page/456"],
            request_user="another_user"
        )
        request_payload_dict = request_payload_model.model_dump()

        headers = {"X-API-Key": TEST_API_KEY}

        response = client.post("/sync", json=request_payload_dict, headers=headers)

        assert response.status_code == 200
        assert response.json() == []
        mock_sync_orchestrator.run.assert_called_once_with(request_payload_dict)
        mock_os_makedirs.assert_any_call('input', exist_ok=True)
        
        called_for_input_file = False
        for call_args in mock_open.call_args_list:
            if call_args.args and isinstance(call_args.args[0], str) and \
               call_args.args[0].startswith(os.path.join(config.INPUT_DIRECTORY, "sync_request_")):
                called_for_input_file = True
                break
        assert called_for_input_file, "Expected open to be called for input file saving"

        app.dependency_overrides.clear()

    # Explicitly apply api_key_override
    @pytest.mark.usefixtures("api_key_override")
    @patch('main.os.makedirs')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_sync_confluence_tasks_invalid_input_error(self, mock_json_dump, mock_open, mock_os_makedirs,
                                                        client, mock_sync_orchestrator):
        """
        Tests /sync endpoint handling of InvalidInputError from orchestrator.
        """
        app.dependency_overrides[container.sync_orchestrator] = lambda: mock_sync_orchestrator
        mock_sync_orchestrator.run.side_effect = InvalidInputError("Test Invalid Input")

        request_payload_model = SyncRequest(
            confluence_page_urls=[],
            request_user="test_user"
        )
        request_payload_dict = request_payload_model.model_dump()

        headers = {"X-API-Key": TEST_API_KEY}
        
        response = client.post("/sync", json=request_payload_dict, headers=headers)

        assert response.status_code == 400
        assert "Invalid Request: Test Invalid Input" in response.json()["detail"]
        mock_os_makedirs.assert_any_call('input', exist_ok=True)
        
        called_for_input_file = False
        for call_args in mock_open.call_args_list:
            if call_args.args and isinstance(call_args.args[0], str) and \
               call_args.args[0].startswith(os.path.join(config.INPUT_DIRECTORY, "sync_request_")):
                called_for_input_file = True
                break
        assert called_for_input_file, "Expected open to be called for input file saving"

        app.dependency_overrides.clear()

    # Explicitly apply api_key_override
    @pytest.mark.usefixtures("api_key_override")
    @patch('main.os.makedirs')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_sync_confluence_tasks_sync_error(self, mock_json_dump, mock_open, mock_os_makedirs,
                                               client, mock_sync_orchestrator):
        """
        Tests /sync endpoint handling of SyncError from orchestrator.
        """
        app.dependency_overrides[container.sync_orchestrator] = lambda: mock_sync_orchestrator
        mock_sync_orchestrator.run.side_effect = SyncError("Test Sync Failure")

        request_payload_model = SyncRequest(
            confluence_page_urls=["http://test.confluence.com/page/123"],
            request_user="test_user"
        )
        request_payload_dict = request_payload_model.model_dump()

        headers = {"X-API-Key": TEST_API_KEY}
        
        response = client.post("/sync", json=request_payload_dict, headers=headers)

        assert response.status_code == 500
        assert "Synchronization failed due to an internal error: Test Sync Failure" in response.json()["detail"]
        mock_os_makedirs.assert_any_call('input', exist_ok=True)
        
        called_for_input_file = False
        for call_args in mock_open.call_args_list:
            if call_args.args and isinstance(call_args.args[0], str) and \
               call_args.args[0].startswith(os.path.join(config.INPUT_DIRECTORY, "sync_request_")):
                called_for_input_file = True
                break
        assert called_for_input_file, "Expected open to be called for input file saving"
        
        app.dependency_overrides.clear()

    # Explicitly apply api_key_override
    @pytest.mark.usefixtures("api_key_override")
    def test_undo_sync_run_success(self, client, mock_undo_orchestrator):
        """
        Tests successful /undo endpoint behavior with a mocked orchestrator.
        """
        app.dependency_overrides[container.undo_orchestrator] = lambda: mock_undo_orchestrator

        mock_undo_orchestrator.run.return_value = None

        request_payload = [
            UndoRequestItem(
                Status="Success",
                confluence_page_id="123",
                original_page_version=1,
                New_Jira_Task_Key="JIRA-1",
                Linked_Work_Package="WP-1",
                Request_User="test_user"
            ).model_dump(by_alias=True)
        ]
        headers = {"X-API-Key": TEST_API_KEY}

        response = client.post("/undo", json=request_payload, headers=headers)

        assert response.status_code == 200
        assert response.json()["message"] == "Undo operation completed successfully. Please check logs for details."
        
        mock_undo_orchestrator.run.assert_called_once_with(request_payload)

        app.dependency_overrides.clear()

    # Explicitly apply api_key_override
    @pytest.mark.usefixtures("api_key_override")
    def test_undo_sync_run_undo_error(self, client, mock_undo_orchestrator):
        """
        Tests /undo endpoint handling of UndoError from orchestrator.
        """
        app.dependency_overrides[container.undo_orchestrator] = lambda: mock_undo_orchestrator
        mock_undo_orchestrator.run.side_effect = UndoError("Test Undo Failure")

        request_payload = [
            UndoRequestItem(
                Status="Success",
                confluence_page_id="123",
                original_page_version=1,
                New_Jira_Task_Key="JIRA-1",
                Linked_Work_Package="WP-1",
                Request_User="test_user"
            ).model_dump(by_alias=True)
        ]
        headers = {"X-API-Key": TEST_API_KEY}
        
        response = client.post("/undo", json=request_payload, headers=headers)

        assert response.status_code == 500
        assert "Undo operation failed due to an internal error: Test Undo Failure" in response.json()["detail"]
        app.dependency_overrides.clear()

    # This test now correctly uses @patch.object to set API_SECRET_KEY for its scope
    # and expects a 401 for a wrong key.
    def test_api_key_unauthorized(self, client):
        """
        Tests API key authentication failure when the key is configured but wrong.
        This test ensures the authentication *actually* fails with a wrong key.
        """
        # Patch config.API_SECRET_KEY only for this test, to a value different from "wrong_key"
        with patch.object(config, 'API_SECRET_KEY', 'some_configured_secret_key'):
            request_payload_model = SyncRequest(
                confluence_page_urls=["http://test.confluence.com/page/123"],
                request_user="test_user"
            )
            request_payload_dict = request_payload_model.model_dump()
            headers = {"X-API-Key": "wrong_key"} # Incorrect API key to trigger 401
            
            response = client.post("/sync", json=request_payload_dict, headers=headers)

            assert response.status_code == 401 # Now expecting 401 because config.API_SECRET_KEY is set
            assert "Invalid API Key" in response.json()["detail"]
