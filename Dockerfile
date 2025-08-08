# ==================================
# 1. Builder Stage
# Creates an isolated virtual environment
# ==================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv globally so we can use it to create our venv and install packages
RUN pip install uv

# Copy dependency definition files
COPY pyproject.toml uv.lock* ./

# Create a virtual environment and install production dependencies into it
# uv will automatically create a '.venv' directory for us
RUN uv venv

# install all dependencies
RUN uv sync

# ==================================
# 2. Production Stage
# Final, optimized image with the isolated venv
# ==================================
FROM python:3.12-slim AS production

WORKDIR /app

# Create the user first, so we can assign ownership later
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy the application source code
COPY ./src ./src

# Copy the entire virtual environment from the builder stage
# This directory contains the Python interpreter and all dependencies
COPY --from=builder /app/.venv /app/.venv

# Create the directories that will be used by the app
RUN mkdir -p logs

# Change ownership of the entire app directory to the non-root user
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose port 80
EXPOSE 80

# The CMD now uses the python interpreter from the virtual environment
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "80"]


# ==================================
# 3. Development Stage
# Can remain the same, but you could also adapt it
# ==================================
FROM builder AS development

WORKDIR /app

# Copy the application source code
COPY ./src ./src

# The command is simple because all packages are in the venv's global path
# The CMD now uses the python interpreter from the virtual environment
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
