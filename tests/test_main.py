import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Import components from your application
from main import app
from src.dependencies import get_api_key, container
from src.models.data_models import AutomationResult, ConfluenceTask, UndoRequestItem, SyncRequest
from src.config import config
from src.exceptions import SyncError, InvalidInputError, UndoError

# A constant API key for testing purposes
TEST_API_KEY = "test_secret_key"


# --- Fixtures ---
@pytest.fixture
def api_key_override():
    """Fixture to override the API key dependency for tests."""
    def override_get_api_key_test():
        return TEST_API_KEY
    
    app.dependency_overrides[get_api_key] = override_get_api_key_test
    original_api_secret_key = config.API_SECRET_KEY
    config.API_SECRET_KEY = TEST_API_KEY
    
    yield
    
    app.dependency_overrides.clear()
    config.API_SECRET_KEY = original_api_secret_key

@pytest.fixture
def client():
    """Fixture to provide a test client for the FastAPI app."""
    return TestClient(app)

@pytest.fixture
def mock_sync_orchestrator():
    """Fixture to create a mock for the SyncOrchestrator."""
    mock = MagicMock()
    mock.results = []
    return mock

@pytest.fixture
def mock_undo_orchestrator():
    """Fixture to create a mock for the UndoOrchestrator."""
    return MagicMock()

@pytest.fixture
def mock_confluence_updater_service():
    """Fixture to create a mock for the ConfluenceIssueUpdaterService."""
    return MagicMock()


# --- Test Class ---
class TestFastAPIDecoupledEndpoints:
    pytestmark = pytest.mark.usefixtures("api_key_override")

    # --- /sync_task Endpoint Tests ---
    @patch('main.setup_logging')
    @patch('main.config.get_output_path')
    @patch('main.config.get_input_path')
    @patch('main.config.generate_timestamped_filename')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_sync_confluence_tasks_success(
        self, mock_json_dump, mock_open, mock_generate_timestamped_filename,
        mock_get_input_path, mock_get_output_path, mock_setup_logging,
        client, mock_sync_orchestrator
    ):
        # --- Arrange ---
        mock_get_input_path.return_value = "/mock/input/sync_task_request.json"
        mock_get_output_path.return_value = "/mock/output/sync_task_result.json"
        mock_generate_timestamped_filename.side_effect = ["request.json", "result.json"]
        app.dependency_overrides[container.sync_orchestrator] = lambda: mock_sync_orchestrator

        task_data = ConfluenceTask(
            confluence_page_id="123",
            confluence_page_title="Test Page",
            confluence_page_url="http://test.confluence.com/page/123",
            confluence_task_id="task1",
            task_summary="Test Task",
            status="incomplete",
            assignee_name=None,
            due_date="2025-01-01",
            original_page_version=1,
            original_page_version_by="test_user",
            original_page_version_when="2025-07-06T12:00:00"
        )
        
        # main.py returns the results from the orchestrator directly
        # And the response_model for the endpoint is List[UndoRequestItem]
        # So we mock what the orchestrator result would be after being processed
        mock_sync_orchestrator.results = [
            AutomationResult(
                task_data=task_data,
                status="Success",
                new_jira_key="JIRA-1",
                request_user="test_user"
            )
        ]
        
        request_payload = SyncRequest(
            confluence_page_urls=["http://test.confluence.com/page/123"],
            request_user="test_user"
        )
        
        # --- Act ---
        response = client.post("/sync_task", json=request_payload.model_dump(), headers={"X-API-Key": TEST_API_KEY})

        # --- Assert ---
        assert response.status_code == 200
        # ** FIX for KeyError **: The response JSON uses the Pydantic model's alias.
        assert response.json()[0]["New Jira Task Key"] == "JIRA-1"
        
        app.dependency_overrides.clear()

    # --- /undo_sync_task Endpoint Tests ---
    @patch('main.setup_logging')
    @patch('main.config.get_input_path')
    @patch('main.config.generate_timestamped_filename')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_undo_sync_run_success(
        self, mock_json_dump, mock_open, mock_generate_timestamped_filename,
        mock_get_input_path, mock_setup_logging, client, mock_undo_orchestrator
    ):
        app.dependency_overrides[container.undo_orchestrator] = lambda: mock_undo_orchestrator
        undo_item = UndoRequestItem(
            Status="Success",
            New_Jira_Task_Key="JIRA-1",
            confluence_page_id="123",
            original_page_version=1
        )
        request_payload = [undo_item.model_dump(by_alias=True)]
        
        response = client.post("/undo_sync_task", json=request_payload, headers={"X-API-Key": TEST_API_KEY})
        
        assert response.status_code == 200
        assert response.json()["message"] == "Undo operation completed successfully."
        app.dependency_overrides.clear()

    # --- /sync_project Endpoint Tests ---
    @patch('main.setup_logging')
    @patch('main.config.get_output_path')
    @patch('main.config.get_input_path')
    @patch('main.config.generate_timestamped_filename')
    @patch('builtins.open')
    @patch('main.json.dump')
    def test_update_confluence_project_success(
        self, mock_json_dump, mock_open, mock_generate_timestamped_filename,
        mock_get_input_path, mock_get_output_path, mock_setup_logging,
        client, mock_confluence_updater_service
    ):
        app.dependency_overrides[container.confluence_issue_updater_service] = lambda: mock_confluence_updater_service
        mock_confluence_updater_service.update_confluence_hierarchy_with_new_jira_project.return_value = [{"page_id": "p1"}]
        
        request_payload = {
            "root_confluence_page_url": "http://mock.confluence.com/root",
            "root_project_issue_key": "PROJ-ROOT",
            "project_issue_type_id": "10200",
            "phase_issue_type_id": "11001"
        }
        
        response = client.post("/sync_project", json=request_payload, headers={"X-API-Key": TEST_API_KEY})
        
        assert response.status_code == 200
        app.dependency_overrides.clear()

    # --- Authentication Tests ---
    def test_api_key_unauthorized(self, client):
        """Tests that a request with a wrong API key is rejected."""
        # ** FIX for 500 Error **: Clear overrides to ensure no state leakage from other tests.
        app.dependency_overrides.clear()
        
        valid_payload = SyncRequest(
            confluence_page_urls=["http://test.confluence.com"],
            request_user="test"
        ).model_dump()

        with patch.object(config, 'API_SECRET_KEY', 'the_real_key'):
            response = client.post("/sync_task", json=valid_payload, headers={"X-API-Key": "wrong_key"})
            assert response.status_code == 401
            assert "Invalid API Key" in response.json()["detail"]

    def test_api_key_missing(self, client):
        """Tests that a request with a missing API key is rejected."""
        # ** FIX for 500 Error **: Clear overrides to ensure no state leakage.
        app.dependency_overrides.clear()
        
        valid_payload = SyncRequest(
            confluence_page_urls=["http://test.confluence.com"],
            request_user="test"
        ).model_dump()

        with patch.object(config, 'API_SECRET_KEY', 'the_real_key'):
            response = client.post("/sync_task", json=valid_payload) # No headers
            assert response.status_code == 403
            assert "Not authenticated" in response.json()["detail"]