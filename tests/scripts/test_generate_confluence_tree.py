import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
import uuid
import logging  # For caplog

# Import the class to be tested and its direct dependencies
from src.scripts.generate_confluence_tree import ConfluenceTreeGenerator
from src.services.adaptors.confluence_service import ConfluenceService
from src.services.adaptors.jira_service import JiraService
from src.services.business_logic.issue_finder_service import IssueFinderService

# We need to import config to patch its values for isolation
from src.config import config


@pytest_asyncio.fixture
async def mock_confluence_service():
    """Provides an AsyncMock for ConfluenceService."""
    service = AsyncMock(spec=ConfluenceService)
    # Default side_effect for create_page: generates dummy page info
    service.create_page.side_effect = lambda **kwargs: {
        "id": str(uuid.uuid4().int % 1000000000),  # Generate a unique-enough dummy ID
        "title": kwargs.get("title", "Mock Page"),
        "space": {"key": kwargs.get("space_key", "TESTSPACE")},
        "_links": {
            "webui": f"http://mock-confluence.com/display/{kwargs.get('space_key', 'TESTSPACE')}/{kwargs.get('title', 'Mock Page').replace(' ', '+')}"
        },
    }
    return service


@pytest_asyncio.fixture
async def mock_jira_service():
    """Provides an AsyncMock for JiraService."""
    service = AsyncMock(spec=JiraService)
    return service


@pytest_asyncio.fixture
async def mock_issue_finder_service():
    """Provides an AsyncMock for IssueFinderService."""
    service = AsyncMock(spec=IssueFinderService)
    return service


@pytest_asyncio.fixture
async def generator(
    mock_confluence_service: AsyncMock,
    mock_jira_service: AsyncMock,
    mock_issue_finder_service: AsyncMock,
):
    """Provides a ConfluenceTreeGenerator instance with mocked dependencies."""
    gen = ConfluenceTreeGenerator(
        confluence_service=mock_confluence_service,
        jira_service=mock_jira_service,
        issue_finder_service=mock_issue_finder_service,
        base_parent_page_id="test_base_parent_id",
        confluence_space_key="TESTSPACE",
        assignee_username="testuser",
        test_work_package_keys=["WP-ALPHA", "WP-BETA"],
        max_depth=2,
        tasks_per_page=1,
    )
    return gen


@pytest.mark.asyncio
async def test_initialize_assignee_success(generator: ConfluenceTreeGenerator):
    """Tests if _initialize_assignee correctly fetches and sets the account ID."""
    expected_account_id = "testAccountId123"
    generator.confluence.get_user_details_by_username.return_value = {
        "username": "testuser",
        "accountId": expected_account_id,
    }

    await generator._initialize_assignee()

    generator.confluence.get_user_details_by_username.assert_awaited_once_with(
        "testuser"
    )
    assert generator.assignee_account_id == expected_account_id


@pytest.mark.asyncio
async def test_initialize_assignee_not_found(
    generator: ConfluenceTreeGenerator, caplog
):
    """Tests if _initialize_assignee handles user not found scenario."""
    generator.confluence.get_user_details_by_username.return_value = None

    with caplog.at_level(logging.WARNING):
        await generator._initialize_assignee()

    generator.confluence.get_user_details_by_username.assert_awaited_once_with(
        "testuser"
    )
    assert generator.assignee_account_id is None
    assert "Could not find account ID for assignee" in caplog.text


@pytest.mark.asyncio
async def test_generate_page_hierarchy_single_page(generator: ConfluenceTreeGenerator):
    """Tests the creation of a single page (max_depth=1)."""
    generator.max_depth = 1
    generator.assignee_account_id = (
        "testAccountId123"  # Simulate successful initialization
    )

    parent_page_id = "root_parent_id"
    results = await generator.generate_page_hierarchy(parent_page_id)

    assert len(results) == 1
    assert "url" in results[0]
    assert "linked_work_package" in results[0]
    assert results[0]["linked_work_package"] == "WP-ALPHA"  # First WP key as i=0

    generator.confluence.create_page.assert_awaited_once()
    create_call_kwargs = generator.confluence.create_page.await_args.kwargs

    assert create_call_kwargs["space_key"] == generator.confluence_space_key
    assert create_call_kwargs["parent_id"] == parent_page_id
    assert "Test Page (Depth 0-0)" in create_call_kwargs["title"]

    # Verify key elements in the page body HTML
    page_body = create_call_kwargs["body"]
    assert '<ac:parameter ac:name="key">WP-ALPHA</ac:parameter>' in page_body
    assert (
        f'<ac:task-assignee ac:account-id="{generator.assignee_account_id}"></ac:task-assignee>'
        in page_body
    )
    # Check for the due date and task summary components
    assert config.DEFAULT_DUE_DATE_FOR_TREE_GENERATION.strftime("%Y-%m-%d") in page_body
    assert "Generated Task 0 for WP-ALPHA" in page_body


@pytest.mark.asyncio
async def test_generate_page_hierarchy_multi_level(generator: ConfluenceTreeGenerator):
    """Tests the recursive generation of a multi-level page hierarchy."""
    generator.max_depth = 2  # Creates a parent and one child for each parent
    generator.assignee_account_id = "testAccountId123"

    # Mock create_page to return specific predictable IDs for multi-level testing
    mock_page_id_d0 = "100000001"  # Dummy ID for depth 0 page
    mock_page_id_d1 = "100000002"  # Dummy ID for depth 1 page

    generator.confluence.create_page.side_effect = [
        # First call: creates depth 0 page
        {
            "id": mock_page_id_d0,
            "title": "D0 Page",
            "space": {"key": "TESTSPACE"},
            "_links": {"webui": "http://link.d0"},
        },
        # Second call: creates depth 1 page, parented by depth 0 page
        {
            "id": mock_page_id_d1,
            "title": "D1 Page",
            "space": {"key": "TESTSPACE"},
            "_links": {"webui": "http://link.d1"},
        },
    ]

    parent_page_id = "root_parent_id"
    results = await generator.generate_page_hierarchy(parent_page_id)

    assert len(results) == 2  # One page at depth 0, one at depth 1

    # Verify that create_page was called twice
    assert generator.confluence.create_page.call_count == 2

    # Check the first call (Depth 0 page)
    call0_kwargs = generator.confluence.create_page.call_args_list[0].kwargs
    assert call0_kwargs["parent_id"] == parent_page_id
    assert "Test Page (Depth 0-0)" in call0_kwargs["title"]
    assert "WP-ALPHA" in call0_kwargs["body"]  # Based on test_work_package_keys[0 % 2]

    # Check the second call (Depth 1 page)
    call1_kwargs = generator.confluence.create_page.call_args_list[1].kwargs
    assert (
        call1_kwargs["parent_id"] == mock_page_id_d0
    )  # The ID of the page created in the first call
    assert "Test Page (Depth 1-0)" in call1_kwargs["title"]
    # CORRECTED: Expecting WP-ALPHA here as 'i' resets per depth in the current script logic
    assert "WP-ALPHA" in call1_kwargs["body"]  # Based on test_work_package_keys[0 % 2]


@pytest.mark.asyncio
async def test_generate_page_hierarchy_create_page_fails(
    generator: ConfluenceTreeGenerator, caplog
):
    """Tests behavior when create_page fails (returns None)."""
    generator.max_depth = 2
    generator.assignee_account_id = "testAccountId123"

    # CORRECTED: Explicitly set side_effect to None before setting return_value
    generator.confluence.create_page.side_effect = None
    generator.confluence.create_page.return_value = (
        None  # Simulate failure to create page
    )

    parent_page_id = "root_parent"
    with caplog.at_level(logging.ERROR):
        results = await generator.generate_page_hierarchy(parent_page_id)

    # CORRECTED: Now expect 0 pages as create_page returns None on the first attempt
    assert len(results) == 0
    generator.confluence.create_page.assert_awaited_once()  # Should still attempt the first creation
    assert "Failed to create page" in caplog.text  # Verify error logging


@pytest.mark.asyncio
async def test_generate_page_hierarchy_zero_tasks_per_page(
    generator: ConfluenceTreeGenerator,
):
    """Tests that no tasks are generated if tasks_per_page is 0."""
    generator.max_depth = 1
    generator.tasks_per_page = 0
    generator.assignee_account_id = "testAccountId123"

    parent_page_id = "root_parent"
    results = await generator.generate_page_hierarchy(parent_page_id)

    assert len(results) == 1
    create_call_kwargs = generator.confluence.create_page.await_args.kwargs
    page_body = create_call_kwargs["body"]

    assert '<ac:parameter ac:name="key">WP-ALPHA</ac:parameter>' in page_body
    assert (
        "<ac:task-list>" not in page_body
    )  # No tasks should be present in the bodyimport pytest
