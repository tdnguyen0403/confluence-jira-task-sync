import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
import logging

from src.scripts.generate_confluence_tree import ConfluenceTreeGenerator, main_async
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business_logic.issue_finder_service import IssueFinderService


@pytest_asyncio.fixture
async def mock_confluence_service():
    """Provides an AsyncMock for ConfluenceService."""
    service = AsyncMock(spec=ConfluenceService)
    service.create_page.side_effect = lambda **kwargs: {
        "id": str(uuid.uuid4().int % 1000000000),
        "title": kwargs.get("title", "Mock Page"),
        "_links": {"webui": "http://mock-confluence.com/page"},
    }
    return service


@pytest_asyncio.fixture
async def mock_jira_service():
    """Provides an AsyncMock for JiraService."""
    return AsyncMock(spec=JiraService)


@pytest_asyncio.fixture
async def mock_issue_finder_service():
    """Provides an AsyncMock for IssueFinderService."""
    return AsyncMock(spec=IssueFinderService)


@pytest_asyncio.fixture
async def generator(
    mock_confluence_service, mock_jira_service, mock_issue_finder_service
):
    """Provides a ConfluenceTreeGenerator instance with mocked dependencies."""
    return ConfluenceTreeGenerator(
        confluence_service=mock_confluence_service,
        jira_service=mock_jira_service,
        issue_finder_service=mock_issue_finder_service,
        base_parent_page_id="test_base_parent_id",
        confluence_space_key="TESTSPACE",
        assignee_username="testuser",
        test_work_package_keys=["WP-ALPHA"],
        max_depth=2,
        tasks_per_page=1,
    )


# --- Unit tests for ConfluenceTreeGenerator class ---


@pytest.mark.asyncio
async def test_initialize_assignee_success(generator: ConfluenceTreeGenerator):
    """Tests if _initialize_assignee correctly fetches and sets the account ID."""
    generator.confluence.get_user_details_by_username.return_value = {
        "accountId": "test-id"
    }
    await generator._initialize_assignee()
    generator.confluence.get_user_details_by_username.assert_awaited_once_with(
        "testuser"
    )
    assert generator.assignee_account_id == "test-id"


@pytest.mark.asyncio
async def test_initialize_assignee_not_found(
    generator: ConfluenceTreeGenerator, caplog
):
    """Tests if _initialize_assignee handles user not found."""
    generator.confluence.get_user_details_by_username.return_value = None
    with caplog.at_level(logging.WARNING):
        await generator._initialize_assignee()
    assert generator.assignee_account_id is None
    assert "Could not find account ID for assignee" in caplog.text


@pytest.mark.asyncio
async def test_generate_page_hierarchy_single_page(generator: ConfluenceTreeGenerator):
    """Tests the creation of a single page (max_depth=1)."""
    generator.max_depth = 1
    generator.assignee_account_id = "test-id"
    results = await generator.generate_page_hierarchy("root_id")
    assert len(results) == 1
    generator.confluence.create_page.assert_awaited_once()
    call_kwargs = generator.confluence.create_page.await_args.kwargs
    assert "Test Page (Depth 0-0)" in call_kwargs["title"]
    assert '<ac:task-assignee ac:account-id="test-id">' in call_kwargs["body"]


# --- Integration test for the main_async script entrypoint ---


@pytest.mark.asyncio
@patch("src.scripts.generate_confluence_tree.ConfluenceTreeGenerator")
@patch("src.scripts.generate_confluence_tree.setup_logging")
@patch("src.scripts.generate_confluence_tree.resource_manager")
async def test_main_async_script_execution(
    mock_resource_manager,
    mock_setup_logging,
    MockGenerator,
):
    """
    Tests the main execution flow of the script, ensuring logging and generator are called.
    """
    # Arrange: Mock the context manager to yield a dummy value
    mock_https_helper = AsyncMock()
    mock_resource_manager.return_value.__aenter__.return_value = mock_https_helper

    # Configure the class mock's static method to return the desired args
    mock_args = MagicMock()
    mock_args.base_parent_page_id = "12345"
    MockGenerator._parse_args.return_value = mock_args

    # Mock the generator instance returned by the class mock
    mock_generator_instance = AsyncMock()
    MockGenerator.return_value = mock_generator_instance

    # Act: Run the main function of the script
    await main_async()

    # Assert
    mock_setup_logging.assert_called_once()
    MockGenerator._parse_args.assert_called_once()
    MockGenerator.assert_called_once()
    mock_generator_instance._initialize_assignee.assert_awaited_once()
    mock_generator_instance.generate_page_hierarchy.assert_awaited_once_with(
        parent_page_id="12345"
    )
