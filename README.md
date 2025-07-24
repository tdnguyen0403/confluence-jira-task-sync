# Jira Confluence Automator

This Python-based tool automates the creation of Jira issues from tasks on a Confluence page and its sub-pages, linking the new Jira issue back to the Confluence page. It includes a function to sync project structure from Jira to Confluence. It also includes an administrative function to generate a tree of Confluence pages from Jira issues, which is useful for creating test data.

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
    * This runs in the command line interface (CLI)
    * *Note: This is an administrative function and is typically not used by normal users.*

## How It Works

The tool is designed with a clear separation of concerns, making it easy to understand and maintain.

### Core Components

-   **API Wrappers**: The tool uses low-level, resilient API wrappers for Jira and Confluence around a helper function. The helper function uses asynchronous method from httpx library to directly communicate to Jira & Confluence server to improve scalability.
-   **Services**: Low-level services include API wrapper & business logic is implemented in services for Confluence, Jira, and for finding issues on a page. There are also high-level orchestration services to coordinate all lower services.
-   **Data Models**: The application uses `pydantic` to represent the core entities, such as `ConfluenceTask` and `AutomationResult`.
-   **Utilities**: The tool includes utility functions for common tasks like logging, creating directory and extracting the context of a task from a Confluence page.

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
    * `generate_confluence_tree.py`: Script for generating Confluence test data, to be run in CLI
-   `tests/`: Contains unit and integration tests.
-   `.gitignore`: Git ignore file.
    `.env.example`: Example environment file
-   `README.md`: This documentation file.
-   `pyproject.toml`: Python dependencies managed by Poetry.

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
2.  Install the required dependencies using Poetry:
    ```bash
    poetry install
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
    JIRA_URL=[https://your-jira-instance.atlassian.net](https://your-jira-instance.atlassian.net)
    JIRA_API_TOKEN=YOUR_JIRA_API_TOKEN

    CONFLUENCE_URL=[https://your-confluence-instance.atlassian.net](https://your-confluence-instance.atlassian.net)
    CONFLUENCE_API_TOKEN=YOUR_CONFLUENCE_API_TOKEN
    ```
    Jira API Token**: You can generate a Jira API token from your Atlassian account settings. Refer to the [Atlassian documentation](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/) for detailed instructions.

    Confluence API Token**: Similar to Jira, Confluence also uses API tokens. Generate one from your Atlassian account.

    For API key authentication for the FastAPI application
    ```
    API_SECRET_KEY=your_secure_api_key_for_fastapi
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

### Example: GET/health
Purpose: to verify if the server is running
```curl
curl -X GET "http://localhost:8000/health" \
-H "X-API-Key: YOUR_API_KEY" \
```

### Example: GET/ready
Purpose: to verify if the server can connect to the Jira & Confluence instances.
```curl
curl -X GET "http://localhost:8000/ready" \
-H "X-API-Key: YOUR_API_KEY" \
```

### Example: POST /sync_task
Note: This endpoint takes in one or multiple URL, an optional request user and days_to_due_date, then scan the pages (including all sub-page), creates tasks in Jira and update the page at the end. The endpoint also returns an response json which can be used for display or use in the /undo_sync_task.

```curl
curl -X POST "http://localhost:8000/sync_task" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "confluence_page_urls": [
        "https://sample-page-1.com",
        "https://sample-page-2.com"
    ],
    "context": {
        "request_user": "test_user",
        "days_to_due_date": 10
    }
}'
```

### Example: POST /undo_sync_task
Note: This endpoint reverses all the changes made by the /sync_task endpoint. The json response from /sync_task should be provided for the /undo_sync_task to run

```curl
curl -X POST "http://localhost:8000/undo_sync_task" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '[
    {
        "Status": "Success",
        "confluence_page_id": "some id",
        "original_page_version": 10,
        "New Jira Task Key": "JIRA-100",
        "Linked Work Package": "PARENT-100",
        "Request User": "test-user",
        "confluence_page_title": "test-page-name",
        "confluence_page_url": "https://test-page.com",
        "confluence_task_id": "1",
        "task_summary": "Test task",
        "status": "incomplete",
        "assignee_name": null,
        "due_date": "2025-01-01",
        "original_page_version_by": "Jone Doe",
        "original_page_version_when": "2025-01-01T12:44:46.000+02:00",
        "context": "Some context"
    }
]'
```

### Example: POST /sync_project
This endpoint automates the synchronization of a Jira project's hierarchy into Confluence page hierachy.

```curl
curl -X POST "http://localhost:8000/sync_project" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d {
    "root_confluence_page_url": "https://project-root-page-in-confluence.com",
    "root_project_issue_key": "PROJ-100",
    "request_user": "user"
}'
```

## Logging
The tool generates detailed logs for each run in the logs/ directory, organized by script type and timestamp. These logs are crucial for debugging and understanding the execution flow.

## Troubleshooting
**ResponseValidationError for API calls: This typically means there's a mismatch between the data format your API endpoint is returning and the Pydantic response_model defined for that endpoint.

- Check your src/models/data_models.py against the actual data returned by the underlying service.

- Authentication Errors (401/403): Double-check your Jira and Confluence API tokens and usernames in the .env file. Ensure they have the necessary permissions for the operations being performed. Also verify the JIRA_SERVER_URL and CONFLUENCE_SERVER_URL are correct.

- File Not Found errors: Ensure that the necessary input files (e.g., result files for undo_sync_task) are present at the expected paths.

- SSL Certificate Errors: If you encounter SSL certificate validation issues, ensure your Python environment's certificate store is up to date, or consider temporarily disabling SSL verification (though not recommended for production environments).
