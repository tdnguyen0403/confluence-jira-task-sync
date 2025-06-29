# Jira Confluence Automator

This Python-based tool automates the creation of Jira issues from tasks on a Confluence page and its sub-pages, linking the new Jira issue back to the Confluence page. It also includes an administrative function to generate a tree of Confluence pages from Jira issues, which is useful for creating test data.

## Main Features

-   **Confluence Task Scanning**: Scans a Confluence page and all its sub-pages to find and extract tasks.
-   **Context-Aware Jira Issue Creation**: Creates Jira issues from Confluence tasks, placing them under the correct parent issue (e.g., Work Package, Risk, Deviation) and embedding the Confluence context.
-   **Two-Way Linking**: Replaces the original task text in Confluence with a link to the newly created Jira issue for seamless navigation and tracking.
-   **Hierarchical Page Generation**: Generates a tree of Confluence pages from Jira issues, which is useful for initial setup or for creating test data.
-   **Undo Functionality**: Includes a script to safely undo the creation of Confluence pages and the corresponding Jira tickets, which is useful for testing or correcting errors.
-   **Flexible Configuration**: Uses a simple JSON file (`input/user_input.json`) to define the scope of the automation.
-   **Detailed Logging**: Maintains comprehensive logs for each run, making it easy to troubleshoot issues.

## How It Works

The tool is designed with a clear separation of concerns, making it easy to understand and maintain.

### Core Components

-   **API Wrappers**: The tool uses low-level, resilient API wrappers for Jira and Confluence. These wrappers use the `atlassian-python-api` library but also include fallbacks to raw `requests` calls for increased reliability.
-   **Services**: High-level business logic is implemented in services for Confluence, Jira, and for finding issues on a page.
-   **Data Models**: The application uses `dataclasses` to represent the core entities, such as `ConfluenceTask` and `AutomationResult`.
-   **Utilities**: The tool includes utility functions for common tasks like logging and extracting the context of a task from a Confluence page.

### Execution Flow

1.  **Configuration**: The tool reads the configuration from `input/user_input.json`, which defines the scope of the automation.
2.  **Scanning**: The tool scans the specified Confluence page and all of its sub-pages for tasks.
3.  **Jira Issue Creation**: For each task found, the tool creates a new Jira issue under the appropriate parent issue.
4.  **Confluence Page Update**: The original task text in Confluence is replaced with a link to the newly created Jira issue.
5.  **Logging**: The results of each run are stored in a timestamped JSON file in the `output/` directory, which is crucial for the undo functionality.

## Project Structure

-   `input/`
    -   `user_input.json`
-   `output/`
    -   `<timestamp>_automation_result.json`
-   `src/`
    -   `api/`
        -   `confluence_api.py`
        -   `jira_api.py`
    -   `config/`
        -   `config.py`
    -   `interfaces/`
        -   `api_service_interface.py`
    -   `models/`
        -   `data_models.py`
    -   `services/`
        -   `confluence_service.py`
        -   `issue_finder_service.py`
        -   `jira_service.py`
    -   `utils/`
        -   `context_extractor.py`
        -   `logger.py`
    -   `generate_confluence_tree.py`
    -   `sync_task.py`
    -   `undo_sync_task.py`
-   `tests/`
    -   `integration/`
        -   `test_api.py`
    -   `unit/`
        -   `test_context_extractor.py`
        -   `test_services.py`
-   `.env.example`
-   `.gitignore`
-   `README.md`
-   `requirements.txt`

## Getting Started

### Prerequisites

-   Python 3.8+
-   Jira and Confluence instances

### Installation

1.  Clone the repository:
    ```bash
    git clone [https://github.com/confluence-jira-task-sync/confluence-jira-task-sync.git](https://github.com/confluence-jira-task-sync/confluence-jira-task-sync.git)
    cd confluence-jira-task-sync
    ```
2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Create a `.env` file from the `.env.example` and fill in your Jira and Confluence credentials.

### Configuration

The `input/user_input.json` file is used to configure the automation. The following parameters can be set:

-   **`confluence_page_id`**: The ID of the Confluence page to scan for tasks.
-   **`jira_project_key`**: The key of the Jira project where the new issues will be created.
-   **`parent_issue_key`**: The key of the parent issue under which the new issues will be created.

### Running the Tool

-   **To sync tasks**:
    ```bash
    python src/sync_task.py
    ```
-   **To generate a Confluence page tree from Jira issues**:
    ```bash
    python src/generate_confluence_tree.py
    ```
-   **To undo the last sync**:
    ```bash
    python src/undo_sync_task.py
    ```