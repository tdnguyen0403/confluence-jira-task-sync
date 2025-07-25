# Deployment Guide

This document provides detailed instructions for deploying the Jira Confluence Automator application using Docker and Docker Compose.

---

## Overview

The project is configured for easy deployment using Docker, which containerizes the application and its dependencies, ensuring a consistent environment from development to production. We use a multi-stage `Dockerfile` to create optimized and secure images.

-   **`development` stage**: Installs all dependencies (including development tools) and runs the server with live-reloading for an efficient development workflow.
-   **`production` stage**: Creates a minimal, lean image containing only the necessary production dependencies. The application runs as a non-root user for enhanced security.

---

## Prerequisites

Before you begin, ensure you have the following installed:

-   [Docker](https://www.docker.com/get-started)
-   [Docker Compose](https://docs.docker.com/compose/install/)

---

## Configuration

Deployment configuration is managed through environment variables.

1.  **Create a `.env` file**: If you haven't already, copy the example file:
    ```bash
    cp .env.example .env
    ```
2.  **Populate the `.env` file**: Open the `.env` file and fill in all the required credentials and configuration values, such as your Jira/Confluence URLs, API tokens, and the `API_SECRET_KEY`.

---

## Development Environment with Docker

The `docker-compose.override.yml` file is configured for local development. It builds the `development` stage from the `Dockerfile`, maps your local source code into the container for live-reloading, and exposes the application on port 8000.

### Steps to Run:

1.  Make sure your `.env` file is correctly filled out.
2.  Build and run the containers in detached mode:
    ```bash
    docker-compose up -d --build
    ```
3.  The application will be running at `http://localhost:8000`.
4.  Any changes you make to the source code on your local machine will trigger an automatic reload of the server inside the container.
5.  To view logs, you can run:
    ```bash
    docker-compose logs -f
    ```
6.  To stop the development environment, run:
    ```bash
    docker-compose down
    ```

---

## Production Environment with Docker

The `docker-compose.yml` file is configured for a production deployment. It builds the lean `production` stage from the `Dockerfile` and exposes the application on port 8080.

### Steps to Run:

1.  Ensure all required environment variables are available in the shell where you run Docker Compose. You can source them from your `.env` file or set them directly in your deployment environment (e.g., as secrets in a CI/CD system).
2.  Build and run the container using the production compose file:
    ```bash
    docker-compose -f docker-compose.yml up -d --build
    ```
3.  The application will now be running in a production-ready state at `http://localhost:8080`.
4.  To stop the production containers, run:
    ```bash
    docker-compose -f docker-compose.yml down
