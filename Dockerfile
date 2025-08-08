# ==================================
# 1. Builder Stage
# Pre-installs production dependencies into the system python
# ==================================
FROM python:3.12-slim as builder

WORKDIR /app

# Install poetry
RUN pip install --upgrade pip
RUN pip install poetry==1.8.2

# Copy dependency definition files
COPY poetry.lock pyproject.toml ./

# === KEY CHANGE ===
# Tell Poetry NOT to create a virtual env for this project
RUN poetry config virtualenvs.create false --local

# Install ONLY production dependencies into the system's site-packages
RUN poetry install --no-root --no-dev


# ==================================
# 2. Production Stage
# Final, optimized image
# ==================================
FROM python:3.12-slim as production

WORKDIR /app

# Create the user first, so we can assign ownership later
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy the globally installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy the application source code
COPY ./src ./src

# Create the directories that will be used by the app
RUN mkdir -p logs input output

# Change ownership of the entire app directory AFTER all files are copied.
# This ensures the user owns the mount point for the volume.
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose port 80 and run the application
EXPOSE 80
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "80"]


# ==================================
# 3. Development Stage
# Inherits from builder and adds development tools
# ==================================
FROM builder as development

WORKDIR /app

# Install ONLY the development-specific dependencies into the system
RUN poetry install --no-root --only dev

# Copy the application source code
COPY ./src ./src

# The command is simple because all packages are in the global path
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
