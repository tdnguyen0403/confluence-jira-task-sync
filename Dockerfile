# ==================================
# 1. Builder Stage
# Installs dependencies
# ==================================
FROM python:3.9-slim as builder

WORKDIR /app

# Install poetry
RUN pip install --upgrade pip
RUN pip install poetry==1.8.2

# Copy dependency definition files
COPY poetry.lock pyproject.toml ./

# Configure poetry and install production dependencies
# This creates a virtual env at /app/.venv
RUN poetry config virtualenvs.in-project true && poetry install --no-root --no-dev


# ==================================
# 2. Production Stage
# Final, optimized image
# ==================================
FROM python:3.9-slim as production

# Create a non-root user for better security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv ./.venv
# Add the venv to the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy your application source code
COPY . .

# Create data directories and give the new user ownership
RUN mkdir -p logs input output && chown -R appuser:appgroup logs input output

# Switch to the non-root user
USER appuser

# Expose the port the app will run on.
EXPOSE 8080

# Command to run the production application.
# The port can be overridden by the PORT environment variable.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${PORT:-8080}"]


# ==================================
# 3. Development Stage
# Used for local development with live-reloading
# ==================================
FROM builder as development

WORKDIR /app

# Install all dependencies, including development ones
RUN poetry install --no-root

# Copy the application source code
COPY . .

# Command to run the dev server with live-reloading
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
