import pytest

# Import the modules and objects we need to test
from src.config import config
import src.dependencies as dependencies_module
from src.api.safe_jira_api import SafeJiraApi
from src.api.safe_confluence_api import SafeConfluenceApi
from fastapi import HTTPException

# --- Fixture for a Clean Testing Environment ---


@pytest.fixture(autouse=True)
def clean_container_and_config():
    """
    This fixture automatically runs for every test. It resets the container's
    cached instances to ensure tests are isolated from each other.
    """
    dependencies_module.container._jira_client_instance = None
    dependencies_module.container._confluence_client_instance = None
    yield


# --- Tests for Dependency Injection Container ---


def test_safe_jira_api_provider_success(monkeypatch):
    """
    Verify that the container correctly provides a SafeJiraApi instance
    when the configuration is valid.
    """
    # Arrange: Directly patch the config attributes the provider will use
    monkeypatch.setattr(config, "JIRA_URL", "http://jira.test.com")
    monkeypatch.setattr(config, "JIRA_API_TOKEN", "token")

    # Act
    jira_api_instance = dependencies_module.container.safe_jira_api

    # Assert
    assert isinstance(jira_api_instance, SafeJiraApi)


def test_jira_client_provider_raises_error_on_missing_config(monkeypatch):
    """
    Verify that asking for a dependency raises a RuntimeError
    if a required configuration value is missing.
    """
    # Arrange: Directly set the config attribute to None to simulate a missing value
    monkeypatch.setattr(config, "JIRA_URL", None)

    # Act & Assert
    with pytest.raises(RuntimeError, match="Missing JIRA_URL or JIRA_API_TOKEN"):
        _ = dependencies_module.container.jira_client


def test_safe_confluence_api_provider_success(monkeypatch):
    """
    Verify that the container correctly provides a SafeConfluenceApi instance.
    """
    # Arrange
    monkeypatch.setattr(config, "CONFLUENCE_URL", "http://confluence.test.com")
    monkeypatch.setattr(config, "CONFLUENCE_API_TOKEN", "token")

    # Act
    confluence_api_instance = dependencies_module.container.safe_confluence_api

    # Assert
    assert isinstance(confluence_api_instance, SafeConfluenceApi)


def test_dependency_caching_returns_same_instance(monkeypatch):
    """
    Verify that the dependency container works as a singleton for clients.
    """
    # Arrange
    monkeypatch.setattr(config, "JIRA_URL", "http://jira.test.com")
    monkeypatch.setattr(config, "JIRA_API_TOKEN", "token")

    # Act
    instance1 = dependencies_module.container.jira_client
    instance2 = dependencies_module.container.jira_client

    # Assert
    assert instance1 is instance2


def test_get_api_key_dependency_valid_key(monkeypatch):
    """
    Verify the logic of get_api_key when a valid key is provided.
    """
    # Arrange
    monkeypatch.setattr(config, "API_SECRET_KEY", "my_super_secret_key")

    # Act
    result = dependencies_module.get_api_key(api_key="my_super_secret_key")

    # Assert
    assert result == "my_super_secret_key"


def test_get_api_key_dependency_invalid_key(monkeypatch):
    """
    Verify the logic of get_api_key when an invalid key is provided.
    """
    # Arrange
    monkeypatch.setattr(config, "API_SECRET_KEY", "my_super_secret_key")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        dependencies_module.get_api_key(api_key="wrong_key")

    assert exc_info.value.status_code == 401
    assert "Invalid API Key" in exc_info.value.detail
