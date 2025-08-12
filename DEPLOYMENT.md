# Deployment Guide

This document provides detailed instructions for deploying the Jira Confluence Automator application using Docker and Docker Compose.

---

## Overview

The project is configured for easy deployment using Docker, which containerizes the application and its dependencies, ensuring a consistent environment from development to production. We use a multi-stage `Dockerfile` to create optimized and secure images.

- **`development` stage**: Installs all dependencies (including development tools) and runs the server with live-reloading for an efficient development workflow.
- **`production` stage**: Creates a minimal, lean image containing only the necessary production dependencies. The application runs as a non-root user for enhanced security.

---

## Prerequisites

Before you begin, ensure you have the following installed:

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Kubernette](https://kubernetes.io/)

---

## Configuration

Deployment configuration is managed through environment variables.

1. **Create a `.env.dev` and `.env.prod` file**: If you haven't already, copy the example file:

    ```bash
    cp .env.example .env.dev
    cp .env.example .env.prod
    ```

2. **Populate the `.env.dev` and `.env.prod` file**: Open the `.env` file and fill in all the required credentials and configuration values, such as your Jira/Confluence URLs, API tokens, and the `API_SECRET_KEY`.

---

## Development Environment with Docker

The `docker-compose.override.yml` file is configured for local development. It builds the `development` stage from the `Dockerfile`, maps your local source code into the container for live-reloading, and exposes the application on port 8000.

### Steps to Run

1. Make sure your `.env.dev` file is correctly filled out. Load them into your environment.
2. Build and run the containers in detached mode:

    ```bash
    docker compose build
    docker compose up
    ```

3. The application will be running at `http://localhost:8000`.
4. Any changes you make to the source code on your local machine will trigger an automatic reload of the server inside the container.
5. To view logs, you can run:

    ```bash
    docker compose logs -f
    ```

6. To stop the development environment, run:

    ```bash
    docker compose down
    ```

7. Run the official redis container for the cache service

    ```bash
    docker run --name jta-redis-local -p 6379:6379 -d redis:alpine    
    ```

---

## Production Environment with Docker

The `docker-compose.yml` file is configured for a production deployment. It builds the lean `production` stage from the `Dockerfile` and exposes the application on port 8080.

### Steps to Build & Test

1. Ensure all required environment variables are available in the shell where you run Docker Compose. You can source them from your `.env.prod` file or set them directly in your deployment environment (e.g., as secrets in a CI/CD system).

2. Build and run the container using the production compose file:

    ```bash
    docker compose -f docker-compose.yml build
    docker compose -f docker-compose.yml up
    ```

3. The application will now be running in a production-ready state at `http://localhost:8080`.
4. To stop the production containers, run:

    ```bash
    docker compose -f docker-compose.yml down
    ```

### Steps to Run on Virtual Machine

1. Save the Image to a .tar File

    ```bash
    docker save -o jta-prod.tar jta-prod:1.0.0
    ```

2. Copy environment file `.env.prod` and production docker-compose file `docker-compose.prod.yml`. For deployment, you need a simpler `docker-compose.prod.yml` that only specifies how to run the image, not how to build it.

3. Copy all the files (.evn*, *.yml) and image (*.tar) to the VM
4. Load the Docker Image

    ```bash
    cd /home/user/my-app/
    docker load -i jta-prod.tar
    ```

5. Run the Application: start your application using the production compose file.

    ```bash
    docker-compose -f docker-compose.prod.yml up -d
    ```

6. Your production container is now running on the new virtual machine, accessible at http://<your_vm_ip>:8080
7. Setup SSL through reverse proxy to hide the IP of VM.
8. Run the official redis container for the cache service

    ```bash
    docker run --name jta-redis-local -p 6379:6379 -d redis:alpine    
    ```

## Production Environment with Kubernetes

This section details how to deploy the application and its Redis dependency to a Kubernetes cluster.

### Create a Kubernetes Secret

First, you must create a Kubernetes secret to securely store your environment variables.

```bash
kubectl create secret generic jta-secret --from-env-file=./.env.prod
```

This command reads the variables from your .env.prod file and creates a secret named jta-secret in your cluster.

### Deploy Redis

The application uses Redis for caching and session management. Deploy Redis using the provided redis-k8s.yaml file, which creates both a Deployment and a Service for Redis.

```bash
kubectl apply -f redis-k8s.yaml
```

This sets up a Redis instance accessible within the cluster via the service name redis-service on port 6379.

### Build and Push the Docker Image

Before deploying the application, you need to build the production Docker image and push it to a container registry that your Kubernetes cluster can access (e.g., Docker Hub, Google Container Registry, Amazon ECR).

#### Build the production image

```bash
docker compose -f docker-compose.yml build
```

#### Tag the image for your registry

```bash
docker tag jta-prod:1.0.0 your-registry/jta-prod:1.0.0
```

#### Push the image to the registry

```bash
docker push your-registry/jta-prod:1.0.0
```

Note: Remember to update the image field in jta-deployment.yaml to point to your-registry/jta-prod:1.0.0.

### Deploy the Application

Deploy the application using the jta-deployment.yaml and jta-services.yaml files.

- jta-deployment.yaml: This file defines a Deployment that runs your application container. It references the jta-secret for environment variables and includes readiness and liveness probes to ensure the application is healthy.
- jta-services.yaml: This file defines a NodePort service, which exposes the application on a static port on each node in the cluster.

Apply the deployment and service configurations:

```bash
kubectl apply -f jta-deployment.yaml
kubectl apply -f jta-services.yaml
```

### Accessing the Application

The service is exposed via a NodePort. To find the port and access the application, run:

```bash
kubectl get svc jta-service
```

The output will show the port mapping. You can then access the application at http://<your_node_ip>:<node_port>. For this project, the nodePort is set to 32000.

### Scaling and Management

You can manage your deployment using standard kubectl commands:

Scale the application:

```bash
kubectl scale deployment jta-deployment --replicas=3
```

View pod logs:

```bash
kubectl logs -f <pod-name>
```

Delete the deployment:

```bash
kubectl delete -f jta-deployment.yaml -f jta-services.yaml -f redis-k8s.yaml
```
