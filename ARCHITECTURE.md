# Application Architecture

This document provides a high-level overview of the architecture for the Jira Confluence Automator. The application is built using a layered architecture pattern, which promotes separation of concerns, modularity, and maintainability.

---

## Architectural Philosophy

The core philosophy is to create a system that is:

- **Scalable**: Capable of handling a large number of requests and processing many Confluence pages and Jira issues efficiently.
- **Maintainable**: Easy to understand, modify, and extend without introducing bugs.
- **Testable**: Components are designed to be tested in isolation.
- **Resilient**: Robust against external service failures and provides clear error handling.

---

## Layered Architecture

The application is divided into several logical layers, with each layer having a specific responsibility.

```markdown
+---------------------------------------+
|           API Layer (FastAPI)         |
| (main.py, dependencies.py)            |
+---------------------------------------+
|     Orchestration Services Layer      |
| (services/orchestration/*)            |
+---------------------------------------+
|      Interfaces (Contracts) Layer     |
| (interfaces/*)                        |
+---------------------------------------+
| Business Logic & Adaptor Services Layer|
| (services/business_logic/*, services/adaptors/*) |
+---------------------------------------+
|          API Wrapper Layer            |
| (api/safe_*.py, api/https_helper.py)   |
+---------------------------------------+
|      Configuration & Models           |
| (config/config.py, models/data_models.py) |
+---------------------------------------+
```

### 1. API Layer (Presentation)

- **Components**: `main.py`, `dependencies.py`
- **Responsibility**: This is the entry point for all external requests. It's built using **FastAPI**. Its primary roles are:
  - Defining the API endpoints (`/sync_task`, `/sync_project`, etc.).
  - Handling HTTP request and response validation using Pydantic models.
  - Managing API-level concerns like authentication (`X-API-Key`).
  - Injecting dependencies into the lower layers.

### 2. Orchestration Services Layer

- **Components**: `services/orchestration/*`
- **Responsibility**: This layer coordinates the high-level business workflows. It doesn't contain complex business logic itself but rather delegates tasks to the appropriate services in the layers below by depending on their interfaces.
- **Example**: The `SyncTaskOrchestrator` takes a request to sync tasks, calls the `IssueFinderService` to find tasks, the `JiraService` to create tickets, and the `ConfluenceIssueUpdaterService` to update the Confluence page.

### 3. Business Logic & Adaptor Services Layer

This layer contains the core business logic and adaptors for external services.

- **Business Logic Services**:
  - **Components**: `services/business_logic/*`
  - **Responsibility**: Implements the core business rules of the application. For example, the `IssueFinderService` is responsible for parsing Confluence page content and identifying tasks that need to be synced. It is independent of the external services (Jira/Confluence).

- **Adaptor Services**:
  - **Components**: `services/adaptors/*`
  - **Responsibility**: Acts as a bridge between the application's business logic and the low-level API wrappers. It translates the application's internal data models into the format required by the external APIs (Jira and Confluence) and vice-versa. For instance, `JiraService` knows how to construct the payload to create a Jira issue.

### 4. API Wrapper Layer

- **Components**: `api/safe_confluence_api.py`, `api/safe_jira_api.py`, `api/https_helper.py`
- **Responsibility**: This layer contains the lowest-level code for interacting with the external Jira and Confluence APIs.
  - It uses the `https_helper.py` which leverages the `httpx` library for making asynchronous HTTP requests, improving performance and scalability.
  - The wrappers are "safe," meaning they include robust error handling, retries, and logging for all external communication.

### 5. Configuration and Models

- **Components**: `config/config.py`, `models/data_models.py`
- **Responsibility**:
  - `config.py`: Manages all application configuration, loading settings from environment variables. This centralizes configuration and makes it easy to manage different environments.
  - `data_models.py`: Defines the data structures used throughout the application using `pydantic`. These models ensure data consistency and validation at different layers, from API requests to internal service communication.

---

## Use of Interfaces (Contracts)

A key aspect of this architecture is the use of service interfaces, defined in the `src/interfaces/` directory. These interfaces are implemented as Python's Abstract Base Classes (ABCs).

- **What they are**: An interface defines a "contract" for a service. It specifies the methods that a service must implement, without defining how those methods work. For example, `JiraServiceInterface` dictates that any class implementing it must have methods like `create_issue` and `get_issue`.

- **Why they are used**:
  - **Decoupling**: Higher-level services (like the orchestrators) depend on the abstract interface, not the concrete implementation. This means you can swap out the implementation (e.g., use a different Jira library) without changing the orchestrator code, as long as the new implementation respects the interface's contract.
  - **Dependency Injection**: Interfaces are crucial for effective dependency injection. They provide a clear contract for the dependencies that are being injected.
  - **Testability**: When testing, you can create a simple stubs object that implements the interface. This allows you to test services in isolation without needing to connect to external systems like Jira or Confluence.

---

## Dependency Injection

The application heavily utilizes **FastAPI's dependency injection** system (`dependencies.py`). This pattern decouples the components from their dependencies.

- **How it works**: Instead of creating instances of services directly, the application declares the dependencies it needs (usually by type-hinting with the service *interface*). FastAPI's framework takes care of providing the concrete implementations of these services.

- **Benefits**:
  - **Improved Testability**: During testing, real dependencies can be easily replaced with mock objects that adhere to the same interface.
  - **Loose Coupling**: Components are not tightly bound to specific implementations, making the system more flexible and easier to maintain.
  - **Centralized Management**: Dependencies are managed in a single place (`dependencies.py`), making it easy to see how services are constructed and wired together.

---

## Asynchronous Operations

To ensure high performance, the application uses `async` and `await` throughout the stack, from the API endpoints down to the `httpx` calls in the `https_helper`. This allows the application to handle multiple I/O-bound operations (like API calls to Jira and Confluence) concurrently, without blocking the main thread.
