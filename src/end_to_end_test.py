import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv

# Set up basic logging for the test script itself
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables for API key and URLs
# (replace with your actual .env path if different)


load_dotenv(
    dotenv_path="./.env"
)  # Adjust path if your .env is not in the current script's directory

BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("API_SECRET_KEY")
if not API_KEY:
    raise ValueError(
        """API_SECRET_KEY not found in environment variables.
        Please set it in your .env file."""
    )

# --- Test Data (Replace with your actual test data) ---
# Ensure these URLs and keys exist in your Confluence and Jira instances for the test
TEST_USER = "j2t-automator"


async def run_end_to_end_test():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
        sync_task_results_for_undo = []

        # 1. Health Check
        logger.info("\n--- Testing /health endpoint ---")
        try:
            response = await client.get("/health")
            response.raise_for_status()
            health_status = response.json()
            logger.info(f"Health Check Response: {health_status}")
            assert health_status["status"] == "ok"
            assert health_status["detail"] == "Application is alive."
            logger.info("Health check passed.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Health check failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Health check failed with request error: {e}")
            return

        # 2. Readiness Check
        logger.info("\n--- Testing /ready endpoint ---")
        try:
            response = await client.get("/ready", headers=headers)
            response.raise_for_status()
            ready_status = response.json()
            logger.info(f"Readiness Check Response: {ready_status}")
            assert ready_status["status"] == "ready"
            assert ready_status["detail"] == "Application and dependencies are ready."
            logger.info("Readiness check passed. Jira and Confluence are reachable.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Readiness check failed with HTTP error: {e.status_code} - {e.text}"
            )
            logger.error(
                """Ensure JIRA_URL, CONFLUENCE_URL, JIRA_API_TOKEN,
                CONFLUENCE_API_TOKEN are correct and have access."""
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Readiness check failed with request error: {e}")
            return

        # 3. Sync Project
        logger.info("\n--- Testing /sync_project endpoint ---")
        sync_project_payload = {
            "project_page_url": "https://pfteamspace.pepperl-fuchs.com/x/OTBhGg",
            "project_key": "SFSEA-1720",
            "request_user": TEST_USER,
        }
        try:
            response = await client.post(
                "/sync_project", headers=headers, json=sync_project_payload
            )
            response.raise_for_status()
            sync_project_response = response.json()
            logger.info(
                f"Sync Project Response: {json.dumps(sync_project_response, indent=2)}"
            )

            assert "request_id" in sync_project_response
            assert "results" in sync_project_response
            logger.info("Sync Project call successful. Verify pages manually.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Request failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request Headers: {e.request.headers}")
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request.content else 'N/A'}"
            )
            logger.error(f"Response Headers: {e.response.headers}")
            logger.error(
                f"Response Content (truncated if large): "
                f"{e.response.text[:500] if e.response.text else 'N/A'}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Request failed with network/request error: {e}")
            logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            logger.error(
                f"Request Headers: {e.request.headers if e.request else 'N/A'}"
            )
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request and e.request.content else 'N/A'}"  # noqa: E501
            )
            return

        # 4. Sync Task
        logger.info("\n--- Testing /sync_task endpoint ---")
        sync_task_payload = {
            "confluence_page_urls": ["https://pfteamspace.pepperl-fuchs.com/x/W-T3GQ"],
            "context": {"request_user": TEST_USER, "days_to_due_date": 7},
        }
        try:
            response = await client.post(
                "/sync_task", headers=headers, json=sync_task_payload
            )
            response.raise_for_status()
            sync_task_response = response.json()
            logger.info(
                f"Sync Task Response: {json.dumps(sync_task_response, indent=2)}"
            )

            assert "request_id" in sync_task_response
            assert "results" in sync_task_response
            assert isinstance(sync_task_response["results"], list)

            if not sync_task_response["results"]:
                logger.warning(
                    """No tasks were processed by /sync_task.
                    Cannot proceed with undo test."""
                )
                return

            sync_task_results_for_undo = sync_task_response["results"]

            for result in sync_task_results_for_undo:
                assert result["status_text"].startswith("Success")
                assert (
                    "new_jira_task_key" in result
                    and result["new_jira_task_key"] is not None
                )
                assert "confluence_page_id" in result["task_data"]
                assert "original_page_version" in result["task_data"]
                logger.info(
                    f"Successfully processed task: {result.get('task_summary', 'N/A')} "
                    f"-> {result.get('new_jira_task_key', 'N/A')}"
                )

            logger.info("""Sync Task call successful. Verifying Jira issues "
                        and Confluence page content manually or via API.""")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Request failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request Headers: {e.request.headers}")
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request.content else 'N/A'}"
            )
            logger.error(f"Response Headers: {e.response.headers}")
            logger.error(
                f"Response Content (truncated if large): "
                f"{e.response.text[:500] if e.response.text else 'N/A'}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Request failed with network/request error: {e}")
            logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            logger.error(
                f"Request Headers: {e.request.headers if e.request else 'N/A'}"
            )
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request and e.request.content else 'N/A'}"  # noqa: E501
            )
            return

        # 5. Undo Sync Task
        logger.info("\n--- Testing /undo_sync_task endpoint ---")
        if not sync_task_results_for_undo:
            logger.info(
                "Skipping /undo_sync_task as no tasks were synced successfully."
            )
            return

        # The API expects a list of UndoSyncTaskRequest,
        # which is a flattened version of SyncTaskResult
        undo_payload = []
        for result_item in sync_task_results_for_undo:
            flattened_item = {
                "status_text": result_item["status_text"],
                "new_jira_task_key": result_item["new_jira_task_key"],
                "linked_work_package": result_item["linked_work_package"],
                "request_user": result_item["request_user"],
                # Flatten task_data fields
                "confluence_page_id": result_item["task_data"]["confluence_page_id"],  # noqa: E501
                "confluence_page_title": result_item["task_data"][
                    "confluence_page_title"
                ],
                "confluence_page_url": result_item["task_data"]["confluence_page_url"],  # noqa: E501
                "confluence_task_id": result_item["task_data"]["confluence_task_id"],  # noqa: E501
                "task_summary": result_item["task_data"]["task_summary"],
                "status": result_item["task_data"]["status"],
                "assignee_name": result_item["task_data"]["assignee_name"],  # noqa: E501
                "due_date": result_item["task_data"]["due_date"],
                "original_page_version": result_item["task_data"][
                    "original_page_version"
                ],
                "original_page_version_by": result_item["task_data"][
                    "original_page_version_by"
                ],
                "original_page_version_when": result_item["task_data"][
                    "original_page_version_when"
                ],
                "context": result_item["task_data"]["context"],
            }
            undo_payload.append(flattened_item)

        try:
            response = await client.post(
                "/undo_sync_task", headers=headers, json=undo_payload
            )
            response.raise_for_status()
            undo_sync_response = response.json()
            logger.info(
                f"Undo Sync Task Response: {json.dumps(undo_sync_response, indent=2)}"
            )

            assert "request_id" in undo_sync_response
            assert (
                undo_sync_response["detail"] == "Undo operation completed successfully."
            )

            logger.info("""Undo Sync Task call successful. Verifying Jira issues and
            Confluence page content manually or via API.""")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Request failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request Headers: {e.request.headers}")
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request.content else 'N/A'}"
            )
            logger.error(f"Response Headers: {e.response.headers}")
            logger.error(
                f"Response Content (truncated if large): "
                f"{e.response.text[:500] if e.response.text else 'N/A'}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Request failed with network/request error: {e}")
            logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            logger.error(
                f"Request Headers: {e.request.headers if e.request else 'N/A'}"
            )
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request and e.request.content else 'N/A'}"  # noqa: E501
            )
            return

    logger.info("\n--- End-to-End Test Sequence Completed ---")


if __name__ == "__main__":
    asyncio.run(run_end_to_end_test())
