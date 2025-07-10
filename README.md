# Jira Confluence Automator

This Python-based tool automates the creation of Jira issues from tasks on a Confluence page and its sub-pages, linking the new Jira issue back to the Confluence page. It also includes a function to sync project structure from Jira to Confluence. It also includes an administrative function to generate a tree of Confluence pages from Jira issues, which is useful for creating test data.

## Main Features

-   **Sync Confluence Tasks to Jira:**
    * Scans a Confluence page and all its sub-pages to find and extract tasks.
    * Creates Jira issues from Confluence tasks, embedding Confluence context.
    * Replaces the original task text in Confluence with a link to the newly created Jira issue for seamless navigation and tracking.

-   **Sync Project:**
    * Automates the synchronization of a Jira project's hierarchy into Confluence, creating or updating Confluence pages based on the project's structure.
    * Useful for maintaining a consistent project overview in Confluence linked to Jira.

-   **Undo Synchronization:**
    * Includes a script to safely undo the creation of Confluence pages and the corresponding Jira tickets.
    * This functionality is useful for testing or correcting errors.

-   **Generate Confluence Page Tree from Jira Issues (Admin Function)*:**
    * Generates a hierarchical tree of Confluence pages based on Jira issues.
    * Useful for initial setup or for creating test data.
    * *Note: This is an administrative function and is typically not used by normal users.*

## How It Works

The tool is designed with a clear separation of concerns, making it easy to understand and maintain.

### Core Components

-   **API Wrappers**: The tool uses low-level, resilient API wrappers for Jira and Confluence. These wrappers use the `atlassian-python-api` library but also include fallbacks to raw `requests` calls for increased reliability.
-   **Services**: High-level business logic is implemented in services for Confluence, Jira, and for finding issues on a page.
-   **Data Models**: The application uses `dataclasses` to represent the core entities, such as `ConfluenceTask` and `AutomationResult`.
-   **Utilities**: The tool includes utility functions for common tasks like logging and extracting the context of a task from a Confluence page.

### Execution Flow

1.  **Configuration**: The tool reads the configuration from environment variables and, for some operations, from JSON request bodies.
2.  **Scanning**: The tool scans the specified Confluence page and all of its sub-pages for tasks.
3.  **Jira Issue Creation**: For each task found, the tool creates a new Jira issue under the appropriate parent issue.
4.  **Confluence Page Update**: The original task text in Confluence is replaced with a link to the newly created Jira issue.
5.  **Logging**: The results of each run are stored in a timestamped JSON file in the `output/` directory, which is crucial for the undo functionality.

## Project Structure

-   `input/`: This directory stores input request JSON files for various API calls, primarily for auditing and debugging purposes.
    * `input_sync_task/`: Stores input data for `/sync_task` requests.
    * `input_sync_project/`: Stores input data for `/sync_project` requests.
    * `input_undo_sync_task/`: Stores input data for `/undo_sync_task` requests.
    * `input_generate/`: Stores input data for `generate_confluence_tree` (if API endpoint were exposed).
-   `output/`: This directory stores the results of successful automation runs in timestamped JSON files. These files are essential for the "Undo Synchronization" feature.
    * `output_sync_task/`: Stores results from `/sync_task` operations.
    * `output_sync_project/`: Stores results from `/sync_project` operations.
    * `output_undo_sync_task/`: (Not directly used for output files, but for input to the undo process).
    * `output_generate/`: Stores results from `generate_confluence_tree` operations.
-   `src/`: Contains the core Python source code.
    * `api/`: Low-level API wrappers for Confluence and Jira.
    * `config/`: Application-wide configuration settings.
    * `interfaces/`: Abstract base classes defining service contracts.
    * `models/`: Pydantic data models for API requests, responses, and internal data representation.
    * `services/`: High-level business logic and orchestration.
    * `utils/`: Utility functions like context extraction and logging.
    * `main.py`: The FastAPI application entry point.
    * `generate_confluence_tree.py`: Script for generating Confluence test data.
    * `sync_task.py`: Core logic for syncing Confluence tasks to Jira.
    * `undo_sync_task.py`: Core logic for undoing previous sync operations.
-   `tests/`: Contains unit and integration tests.
-   `.env.example`: Example environment variables file.
-   `.gitignore`: Git ignore file.
-   `README.md`: This documentation file.
-   `requirements.txt`: Python dependencies.

## Getting Started

### Prerequisites

-   Python 3.8+
-   Jira and Confluence instances with appropriate API access.

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

### API Authentication

This tool uses environment variables to store sensitive API credentials for Jira and Confluence, and an API Key for securing the FastAPI endpoints.

1.  **Create a `.env` file**: Copy the provided `.env.example` file and rename it to `.env` in the root directory of the project.
    ```bash
    cp .env.example .env
    ```
2.  **Fill in your credentials**: Open the `.env` file and replace the placeholder values with your actual Jira and Confluence API details.

    .env example
    ```
    JIRA_SERVER_URL=[https://your-jira-instance.atlassian.net](https://your-jira-instance.atlassian.net)
    JIRA_USERNAME=your-jira-email@example.com
    JIRA_API_TOKEN=YOUR_JIRA_API_TOKEN

    CONFLUENCE_SERVER_URL=[https://your-confluence-instance.atlassian.net](https://your-confluence-instance.atlassian.net)
    CONFLUENCE_USERNAME=your-confluence-email@example.com
    CONFLUENCE_API_TOKEN=YOUR_CONFLUENCE_API_TOKEN
    ```
    Jira API Token**: You can generate a Jira API token from your Atlassian account settings. Refer to the [Atlassian documentation](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/) for detailed instructions.

    Confluence API Token**: Similar to Jira, Confluence also uses API tokens. Generate one from your Atlassian account.

    For API key authentication for the FastAPI application
    ```
    API_KEY=your_secure_api_key_for_fastapi
    ```

### Running the FastAPI Application

The project includes a FastAPI application (`main.py`) that exposes API endpoints for the tool's functionalities.
To run the FastAPI application:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You can then interact with the API endpoints (for example, /sync_project) using tools like cURL or Postman. Alternatively, you can use the web interface at http://localhost:8000/docs (Swagger UI). Remember to include the X-API-Key header for authenticated endpoints.

## Detailed API Usage Examples
Once the FastAPI application is running (e.g., on http://localhost:8000), you can test the available endpoints using cURL. Replace YOUR_API_KEY, http://mock.confluence.com/root, and Jira issue type IDs with your actual values.

### Example: POST /sync_project
This endpoint automates the synchronization of a Jira project's hierarchy into Confluence.

```curl
curl -X POST "http://localhost:8000/sync_project" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "root_confluence_page_url": "[http://mock.confluence.com/root](http://mock.confluence.com/root)",
    "root_project_issue_key": "PROJ-ROOT",
    "project_issue_type_id": "10200",
    "phase_issue_type_id": "11001",
    "request_user": "test_user"
}'
```

### Example: POST /sync_task
Note: This endpoint corresponds to the functionality of sync_task.py. The example below assumes main.py exposes this functionality via an API endpoint.

```curl
curl -X POST "http://localhost:8000/sync_task" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "confluence_page_urls": ["[https://your.confluence.com/x/ABCDEFG](https://your.confluence.com/x/ABCDEFG)"],
    "request_user": "api_user"
}'
```

### Example: POST /undo_sync_task
Note: This endpoint corresponds to the functionality of undo_sync_task.py. The example below assumes main.py exposes this functionality via an API endpoint.

```curl
curl -X POST "http://localhost:8000/undo_sync_task" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '[
    {
        "Status": "Success",
        "confluence_page_id": "435680347",
        "original_page_version": 90,
        "New Jira Task Key": "SFSEA-1733",
        "Linked Work Package": "SFSEA-1524",
        "Request User": "tdnguyen",
        "confluence_page_title": "Gen 20250629_122720 - Main Test Page Root",
        "confluence_page_url": "/spaces/EUDEMHTM0589/pages/435680347/Gen+20250629_122720+-+Main+Test+Page+Root",
        "confluence_task_id": "8",
        "task_summary": "Test task",
        "status": "incomplete",
        "assignee_name": null,
        "due_date": "2025-07-20",
        "original_page_version_by": "Nguyen Tuan Dat",
        "original_page_version_when": "2025-07-06T12:44:46.000+02:00",
        "context": "JIRA_KEY_CONTEXT::SFSEA-1524"
    }
]'
```

### Example: POST /generate_confluence_tree
Note: This endpoint corresponds to the functionality of generate_confluence_tree.py. The example below assumes main.py exposes this functionality via an API endpoint.

```Bash
curl -X POST "http://localhost:8000/generate_confluence_tree" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "base_parent_page_id": "422189655",
    "confluence_space_key": "EUDEMHTM0589",
    "assignee_username": "tdnguyen",
    "test_work_package_keys": ["SFSEA-1524", "SFSEA-1483"],
    "max_depth": 2,
    "tasks_per_page": 1
}'
```

## Logging
The tool generates detailed logs for each run in the logs/ directory, organized by script type and timestamp. These logs are crucial for debugging and understanding the execution flow.

## Troubleshooting
**ResponseValidationError for API calls: This typically means there's a mismatch between the data format your API endpoint is returning and the Pydantic response_model defined for that endpoint.

- Check your src/models/data_models.py against the actual data returned by the underlying service.

    - Common fix: Ensure List[str] is used where a list of strings is expected, and field names in the model match the exact field names in the returned data (e.g., root_project_key vs root_project_linked).

- Authentication Errors (401/403): Double-check your Jira and Confluence API tokens and usernames in the .env file. Ensure they have the necessary permissions for the operations being performed. Also verify the JIRA_SERVER_URL and CONFLUENCE_SERVER_URL are correct.

- File Not Found errors: Ensure that the necessary input files (e.g., result files for undo_sync_task) are present at the expected paths.

- SSL Certificate Errors: If you encounter SSL certificate validation issues, ensure your Python environment's certificate store is up to date, or consider temporarily disabling SSL verification (though not recommended for production environments).
