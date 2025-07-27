# Jira Confluence Automator

This Python-based tool automates the creation of Jira issues from tasks on a Confluence page and its sub-pages, linking the new Jira issue back to the Confluence page. It includes a function to sync project structure from Jira to Confluence. It also includes an administrative function to generate a tree of Confluence pages from Jira issues, which is useful for creating test data.

---

## Main Features

-   **Sync Confluence Tasks to Jira:**
    * Scans a Confluence page and all its sub-pages to find and extract tasks.
    * Creates Jira issues from Confluence tasks, embedding Confluence context.
    * Converts task to plain text in Confluence with a link to the newly created Jira issue for seamless navigation and tracking.

-   **Sync Project:**
    * Automates the synchronization of a Jira project's hierarchy into Confluence, creating or updating Confluence pages based on the project's structure.
    * Useful for maintaining a consistent project structure link between Jira and Confluence.

-   **Undo Synchronization:**
    * Take the result of sync task to safely undo the update of Confluence pages by reverting it back to previosu version and the corresponding Jira tasks by transition them to Backlog status.
    * This functionality is useful for testing or correcting errors.

-   **Generate Confluence Page Tree from Jira Issues (Admin Function)\*:**
    * Generates a hierarchical tree of Confluence pages with attachef Jira work packages and dummy Confluence tasks.
    * Useful for initial setup or for creating test data.
    * This runs in the command line interface (CLI)
    * *\*Note: This is an administrative function and is typically not used by normal users.*

---

## How It Works

The tool is designed with a clear separation of concerns, making it easy to understand and maintain.

### Core Components

-   **API Wrappers**: The tool uses low-level, resilient API wrappers for Jira and Confluence around a helper function. The helper function uses asynchronous method from `httpx` library to directly communicate to Jira & Confluence server asynchronously to improve future ascalability.
-   **Services**: Low-level services include API wrapper & business logic is implemented in services for Confluence, Jira, and for finding issues on a page. There are also high-level orchestration services to coordinate all lower services.
-   **Interface**: The application uses interfaces to ensure high level services does not depend on lower level service implementation. It helps to achieve Dependency Inversion for better scalability in the future.
-   **Data Models**: The application uses `pydantic` to represent the core entities, such as `ConfluenceTask` and `SingleTaskResult`.
-   **Utilities**: The tool includes utility functions for common tasks like logging and extracting the context of a task from a Confluence page.

### Execution Flow

1.  **Configuration**: The tool reads the configuration from environment variables and, for some operations, from JSON request bodies.
2.  **Scanning**: The tool scans the specified Confluence page and all of its sub-pages for tasks.
3.  **Jira Issue Creation**: For each task found, the tool creates a new Jira issue under the appropriate parent issue.
4.  **Confluence Page Update**: The original task text in Confluence is converted to plain text with a link to the newly created Jira issue.
5.  **Logging**: The log results of each run are stored in a common log JSON file in the `logs/` directory, which is crucial for debugging.

---

## Project Structure

-   `src/`: Contains the core Python source code.
    * `api/`: Low-level API wrappers for Confluence and Jira.
    * `config/`: Application-wide configuration settings.
    * `interfaces/`: Abstract base classes defining service contracts.
    * `models/`: Pydantic data models for API requests, responses, and internal data representation.
    * `services/`: Low-level Jira and Confluence adaptors and high-level business logic and orchestration.
    * `utils/`: Utility functions like context extraction and logging.
    * `main.py`: The FastAPI application entry point.
    * `dependencies.py`: Decouple services from FastAPI application using built in Depend module for dependency injection.
    * `exceptions.py`: custom exception class to be used throughout applcation.
    * `scripts/`: Contains auxiliary script such as generate_confluence_tree.pu for generating Confluence test data, to be run in CLI.
-   `tests/`: Contains unit and integration tests.
-   `Dockerfile`: Defines the multi-stage build process for development and production containers.
-   `docker-compose.yml`: Defines the services for production deployment.
-   `docker-compose.override.yml`: Extends the production setup for local development.
-   `pyproject.toml`: Python dependencies managed by Poetry.
-   `README.md`: This documentation file.
-   `ARCHITECTURE.md`: Explain the architecture desgin of the application.
-   `DEPLOYMENT.me`: step by step guide for deployment as Dockers container
---

## Getting Started

You can run this application either locally with a Python environment or using Docker.

### Prerequisites

-   Python 3.9+
-   [Poetry](https://python-poetry.org/docs/#installation) for managing dependencies.
-   [Docker](https://www.docker.com/get-started) and Docker Compose.
-   Jira and Confluence instances with API access.

### API Authentication

This tool uses environment variables to store sensitive API credentials.

1.  **Create a `.env` file**: Copy the provided `.env.example` file to a new file named `.env` in the project's root directory.
    ```bash
    cp .env.example .env
    ```
2.  **Fill in your credentials**: Open the `.env` file and replace the placeholder values with your actual Jira and Confluence API details and a secure key for the API.

    ```dotenv
    # .env
    JIRA_URL="[https://your-jira-instance.atlassian.net](https://your-jira-instance.atlassian.net)"
    JIRA_API_TOKEN="YOUR_JIRA_API_TOKEN"
    CONFLUENCE_URL="[https://your-confluence-instance.atlassian.net](https://your-confluence-instance.atlassian.net)"
    CONFLUENCE_API_TOKEN="YOUR_CONFLUENCE_API_TOKEN"
    API_SECRET_KEY="your_secure_api_key_for_fastapi" #pragma: allowlist secret
    # ... fill in other variables as needed from .env.example
    ```

### Local Development (Python)

1.  **Clone the repository**:
    ```bash
    git clone [https://github.com/confluence-jira-task-sync/confluence-jira-task-sync.git](https://github.com/confluence-jira-task-sync/confluence-jira-task-sync.git)
    cd confluence-jira-task-sync
    ```
2.  **Install dependencies** using Poetry:
    ```bash
    poetry install
    ```
3.  **Run the FastAPI Application**:
    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```
The application will be available at `http://localhost:8000`.

## Testing

The project uses `pytest` for unit and integration testing.

1.  **Run all tests**:
    ```bash
    poetry run pytest
    ```
2.  **Run tests with coverage**:
    ```bash
    poetry run pytest --cov=src
    ```
This will run the tests and generate a coverage report. A `coverage.xml` file is also generated, which shows a line rate of over 92% and a branch rate of over 82%.

---

## Code Quality

This project uses `pre-commit` hooks to ensure code quality and consistency. The hooks automatically format code with `ruff-format` and lint with `ruff`.

1.  **Install pre-commit hooks**:
    ```bash
    pre-commit install
    ```
Now, the configured checks will run automatically on every commit.

---

## Detailed API Usage Examples
Once the FastAPI application is running (e.g., on `http://localhost:8000`), you can test the available endpoints using cURL.

### Example: GET /health

Purpose: To verify if the server is running.
```curl
curl -X GET "http://localhost:8000/health"
```

### Example: GET /ready

Purpose: To verify if the server can connect to the Jira & Confluence instances.
```curl
curl -X GET "http://localhost:8000/ready" \
-H "X-API-Key: YOUR_API_KEY"
```

### Example: POST /sync_task

This endpoint scans the provided Confluence pages (including all sub-pages), creates tasks in Jira, and updates the pages.
```curl
curl -X POST "http://localhost:8000/sync_task" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "confluence_page_urls": [
        "[https://sample-page-1.com](https://sample-page-1.com)"
    ],
    "context": {
        "request_user": "test_user",
        "days_to_due_date": 10
    }
}'
```

### Example: POST /undo_sync_task

This endpoint reverses the changes made by a `/sync_task` run. The JSON response from `/sync_task` should be provided as the request body.
```curl
curl -X POST "http://localhost:8000/undo_sync_task" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '[
    {
        "status_text": "Success",
        "new_jira_task_key": "JIRA-100",
        "linked_work_package": "PARENT-100",
        "request_user": "test-user",
        "confluence_page_id": "12345",
        "confluence_page_title": "test-page-name",
        "confluence_page_url": "[https://test-page.com](https://test-page.com)",
        "confluence_task_id": "1",
        "task_summary": "Test task",
        "status": "incomplete",
        "assignee_name": null,
        "due_date": "2025-01-01",
        "original_page_version": 10,
        "original_page_version_by": "John Doe",
        "original_page_version_when": "2025-01-01T12:44:46.000Z",
        "context": "Some context"
    }
]'
```

### Example: POST /sync_project

This endpoint automates the synchronization of a Jira project's hierarchy into a Confluence page hierarchy.
```curl
curl -X POST "http://localhost:8000/sync_project" \
-H "X-API-Key: YOUR_API_KEY" \
-H "Content-Type: application/json" \
-d '{
    "project_page_url": "[https://project-root-page-in-confluence.com](https://project-root-page-in-confluence.com)",
    "project_key": "PROJ-100",
    "request_user": "user"
}'
```

---

## Logging
The tool generates detailed logs for each run in the `logs/` directory. These logs are crucial for debugging and understanding the execution flow.

---

## Troubleshooting
-   **ResponseValidationError**: This typically means there's a mismatch between the data format your API endpoint is returning and the Pydantic `response_model` defined for that endpoint. Check `src/models/data_models.py` against the actual data returned by the service.
-   **Authentication Errors (401/403)**: Double-check your API tokens and URLs in the `.env` file. Ensure the credentials have the necessary
-   **SSL Certificate Errors**: If you encounter SSL certificate validation issues, ensure your environment's certificate store is up to date, or set `VERIFY_SSL=false` in your `.env` file for local development (not recommended for production).
